"""
File: session.py
Description: One sandboxed run of a player program. Starts the program
    through the launcher in a borrowed slot and plays it like a person at
    a terminal: everything it prints until it asks for input (or exits)
    is one screen, and each input line is sent only when it asks. Enforces
    the turn and run deadlines and the output cap, and kills everything
    when the run ends.
Author(s): Richard Hall, Tyler Black
"""

import logging
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import TracebackType

from src.runner.launcher import clear_directory
from src.runner.limits import SandboxLimits
from src.runner.slots import (
    FIRST_REAPER_UID,
    FIRST_SLOT_UID,
    Slot,
    SlotCompromisedError,
)

LAUNCHER_PATH = Path(__file__).with_name("launcher.py")
READ_CHUNK_BYTES = 65536
EXIT_WAIT_SECONDS = 1.0
# How often to check whether the program exited while a child it left
# behind still holds its stdout open.
EXIT_POLL_SECONDS = 0.05
REAP_TIMEOUT_SECONDS = 5.0

logger = logging.getLogger(__name__)


class SandboxError(Exception):
    """Base class for everything that can end a sandboxed run early."""


class LaunchError(SandboxError):
    """The sandbox itself failed. Never the player's fault."""


class ProgramError(SandboxError):
    """The player's program crashed, ended too soon, or broke a limit."""

    status = "failed"


class ProgramCrashedError(ProgramError):
    """The program exited with an error or was killed by a limit."""

    status = "crashed"


class ProgramExitedError(ProgramError):
    """The program had already exited when it was sent more input."""

    status = "exited"


class TurnTimeoutError(ProgramError):
    """The program took too long to ask for input or exit."""

    status = "turn_timeout"


class RunTimeoutError(ProgramError):
    """The whole run took longer than the run limit."""

    status = "run_timeout"


class OutputLimitError(ProgramError):
    """The program printed more than the output limit."""

    status = "output_limit"


class ProgramSession:
    """Runs one player program in one slot, one screen at a time.

    Use as a context manager: ``start`` the program, read its
    ``first_screen``, then ``send`` each input line, which returns the
    next screen. ``finished`` turns true once the program has exited
    cleanly. Leaving the block kills the program and empties the slot;
    ``stderr`` and ``exit_code`` are filled in by then.
    """

    def __init__(self, slot: Slot, limits: SandboxLimits) -> None:
        """Prepare a session in ``slot`` under ``limits``."""
        self._slot = slot
        self._limits = limits
        self._process: subprocess.Popen[bytes] | None = None
        self._selector = selectors.DefaultSelector()
        self._stdin_selector = selectors.DefaultSelector()
        self._waiting_read: int | None = None
        self._stdout = b""
        self._stderr = b""
        self._stdout_open = False
        self._asked_for_input = False
        self._run_deadline = 0.0
        self._turn_deadline = 0.0
        self.finished = False
        self.exit_code: int | None = None

    @property
    def stderr(self) -> str:
        """Return what the program wrote to stderr, up to the limit."""
        return self._stderr.decode("utf-8", "replace")

    def __enter__(self) -> "ProgramSession":
        """Return the session for use in a ``with`` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Kill the program and empty the slot, whatever happened."""
        self.close()

    def start(self, code: str) -> None:
        """Launch the program and hand it ``code``.

        Raises:
            LaunchError: If the sandbox couldn't start the program.
        """
        try:
            self._waiting_read, waiting_write = os.pipe()
        except OSError as error:
            raise LaunchError(f"could not make a pipe: {error}") from error
        # From here on, ``close`` closes the waiting pipe's read end.
        try:
            status_read, status_write = os.pipe()
        except OSError as error:
            os.close(waiting_write)
            raise LaunchError(f"could not make a pipe: {error}") from error
        try:
            self._process = self._spawn_launcher(status_write, waiting_write)
        except OSError as error:
            os.close(status_read)
            raise LaunchError(
                f"could not start the launcher: {error}"
            ) from error
        finally:
            os.close(status_write)
            os.close(waiting_write)
        try:
            self._send_code(code)
        except BaseException:
            os.close(status_read)
            raise
        self._wait_for_launch(status_read)
        # Non-blocking, so a spurious wakeup can never stall a read.
        for stream in (self._process.stdout, self._process.stderr):
            os.set_blocking(stream.fileno(), False)
            self._selector.register(stream, selectors.EVENT_READ)
        os.set_blocking(self._waiting_read, False)
        self._selector.register(self._waiting_read, selectors.EVENT_READ)
        self._stdout_open = True
        self._turn_deadline = self._deadline_from_now()

    def _send_code(self, code: str) -> None:
        """Send the launcher the code's length line, then the code.

        Raises:
            LaunchError: If the launcher didn't take it before the run
                deadline.
        """
        self._run_deadline = time.monotonic() + self._limits.run_seconds
        os.set_blocking(self._process.stdin.fileno(), False)
        self._stdin_selector.register(
            self._process.stdin, selectors.EVENT_WRITE
        )
        source = code.encode()
        try:
            self._write(
                f"{len(source)}\n".encode() + source, self._run_deadline
            )
        except ProgramError as error:
            raise LaunchError("the launcher did not take the code") from error

    def _spawn_launcher(
        self, status_write: int, waiting_write: int
    ) -> subprocess.Popen[bytes]:
        """Start the launcher in run mode, in its own session."""
        uid = "-" if self._slot.uid is None else str(self._slot.uid)
        return subprocess.Popen(
            [
                sys.executable,
                "-I",
                str(LAUNCHER_PATH),
                "run",
                uid,
                str(self._slot.directory),
                self._limits.to_json(),
                str(status_write),
                str(waiting_write),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(status_write, waiting_write),
            start_new_session=True,
            env={},
        )

    def _wait_for_launch(self, status_read: int) -> None:
        """Wait until exec closes the status pipe, or report why it didn't.

        Raises:
            LaunchError: If the launcher reported a failure or hung.
        """
        try:
            with selectors.DefaultSelector() as status_selector:
                status_selector.register(status_read, selectors.EVENT_READ)
                ready = status_selector.select(self._remaining())
            message = os.read(status_read, 500) if ready else None
        except OSError as error:
            raise LaunchError(
                f"could not wait for the launch: {error}"
            ) from error
        finally:
            os.close(status_read)
        if message is None:
            raise LaunchError("the launcher did not start in time")
        if message:
            raise LaunchError(message.decode("utf-8", "replace"))

    def first_screen(self) -> str:
        """Return what the program prints before it first asks for input.

        Raises:
            ProgramError: If the program crashed, timed out, or printed
                too much.
        """
        return self._next_screen(self._turn_deadline)

    def send(self, line: str) -> str:
        """Type ``line`` as the program's input and return the next screen.

        Args:
            line: One input line, without a newline.

        Returns:
            Everything the program printed until it asked for input
            again or exited, without its final newline.

        Raises:
            ProgramError: If the program had already exited, or crashed,
                timed out, or printed too much on this turn.
        """
        if self.finished:
            raise ProgramExitedError("the program exited before this input")
        deadline = self._deadline_from_now()
        self._write(line.encode() + b"\n", deadline)
        return self._next_screen(deadline)

    def _deadline_from_now(self) -> float:
        """Return when the turn starting now must end."""
        turn_deadline = time.monotonic() + self._limits.turn_seconds
        return min(turn_deadline, self._run_deadline)

    def _next_screen(self, deadline: float) -> str:
        """Wait until the program asks for input or exits; return its screen.

        Raises:
            ProgramError: If the program crashed, timed out, or printed
                too much.
        """
        while True:
            if self._asked_for_input:
                self._asked_for_input = False
                # The program printed before it asked, so the rest of
                # its screen is already in the pipe.
                self._drain_stdout()
                if self._process.poll() is not None:
                    # Something else wrote the signal, then it exited.
                    self._finish(deadline)
                break
            if not self._stdout_open or self._process.poll() is not None:
                self._finish(deadline)
                break
            late = time.monotonic() >= deadline
            # Even when late, read once: the program may have asked in time.
            remaining = max(0.0, deadline - time.monotonic())
            self._pump(min(remaining, EXIT_POLL_SECONDS))
            still_working = (
                self._stdout_open
                and not self._asked_for_input
                and self._process.poll() is None
            )
            if late and still_working:
                raise self._timeout_error(deadline)
        screen, self._stdout = self._stdout, b""
        return screen.decode("utf-8", "replace").removesuffix("\n")

    def _timeout_error(self, deadline: float) -> ProgramError:
        """Return the timeout matching whichever deadline just passed."""
        if deadline == self._run_deadline:
            return RunTimeoutError("the run took too long")
        return TurnTimeoutError("the turn took too long")

    def _remaining(self) -> float:
        """Return the seconds left in the run, never below zero."""
        return max(0.0, self._run_deadline - time.monotonic())

    def _write(self, data: bytes, deadline: float) -> None:
        """Write all of ``data`` to stdin before ``deadline``.

        Stdin is non-blocking, so a program that never reads its input
        can't stall the runner past the deadline. A program that already
        quit is ignored here; the read side reports how it ended.

        Raises:
            TurnTimeoutError: If the pipe stays full past a turn deadline.
            RunTimeoutError: If it stays full past the run deadline.
        """
        pending = memoryview(data)
        fd = self._process.stdin.fileno()
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._timeout_error(deadline)
            if not self._stdin_selector.select(remaining):
                continue
            try:
                pending = pending[os.write(fd, pending) :]
            except BlockingIOError:
                continue
            except BrokenPipeError:
                return

    def _pump(self, timeout: float) -> bool:
        """Read whatever the program's pipes have, waiting up to ``timeout``.

        Returns:
            True if anything was read from stdout.

        Raises:
            OutputLimitError: If either stream goes over the output limit.
        """
        printed = False
        if not self._selector.get_map():
            # Some selectors return at once with nothing to watch.
            time.sleep(timeout)
            return printed
        for key, _events in self._selector.select(timeout):
            try:
                chunk = os.read(key.fd, READ_CHUNK_BYTES)
            except BlockingIOError:
                continue  # A spurious wakeup: nothing to read after all.
            if not chunk:
                self._selector.unregister(key.fileobj)
                if key.fileobj is self._process.stdout:
                    self._stdout_open = False
            elif key.fileobj is self._process.stdout:
                self._stdout += chunk
                printed = True
            elif key.fileobj is self._process.stderr:
                self._stderr += chunk
            else:
                # Any bytes on the waiting pipe mean "asking for input".
                self._asked_for_input = True
        limit = self._limits.output_bytes
        if len(self._stdout) > limit or len(self._stderr) > limit:
            self._stderr = self._stderr[:limit]
            raise OutputLimitError("the program printed too much")
        return printed

    def _drain_stdout(self) -> None:
        """Read the stdout already waiting in the pipe, without blocking."""
        while self._stdout_open and self._pump(0):
            pass

    def _finish(self, deadline: float) -> None:
        """Handle an exit or a closed stdout: a clean exit finishes.

        Raises:
            ProgramCrashedError: If the program exited with an error.
            TurnTimeoutError: If it closed stdout but kept running.
            RunTimeoutError: The same, past the run deadline.
            OutputLimitError: If it printed too much while exiting.
        """
        while self._process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._timeout_error(deadline)
            # Keep reading, so a full stderr pipe can't block the exit.
            self._pump(min(remaining, EXIT_POLL_SECONDS))
        returncode = self._process.returncode
        self._drain_stdout()
        if self._stdout_open:
            # A child left behind holds stdout; its later output isn't
            # part of this screen.
            self._selector.unregister(self._process.stdout)
            self._stdout_open = False
        self._drain_stderr()
        if returncode != 0:
            raise ProgramCrashedError(f"the program exited with {returncode}")
        self.finished = True

    def _drain_stderr(self) -> None:
        """Collect the rest of stderr (the traceback) after an exit."""
        deadline = time.monotonic() + EXIT_WAIT_SECONDS
        while self._selector.get_map() and time.monotonic() < deadline:
            try:
                self._pump(deadline - time.monotonic())
            except OutputLimitError:
                return

    def close(self) -> None:
        """Kill everything the program started and empty the slot.

        Raises:
            SlotCompromisedError: If the slot couldn't be cleaned, so the
                pool must not lend it out again.
        """
        process, self._process = self._process, None
        try:
            if process is not None:
                self._reap(process)
                self._collect(process)
        finally:
            self._selector.close()
            self._stdin_selector.close()
            if self._waiting_read is not None:
                os.close(self._waiting_read)
                self._waiting_read = None
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()

    def _collect(self, process: subprocess.Popen[bytes]) -> None:
        """Wait for the killed program and record its exit code."""
        try:
            self.exit_code = process.wait(timeout=EXIT_WAIT_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise SlotCompromisedError(
                f"{self._slot}: the program survived reaping"
            ) from error

    def _reap(self, process: subprocess.Popen[bytes]) -> None:
        """Kill the slot's processes, then clear its folder.

        Raises:
            SlotCompromisedError: If killing or clearing failed.
        """
        if self._slot.uid is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                # macOS answers EPERM, not ESRCH, once only zombies remain.
                pass
            try:
                clear_directory(Path(self._slot.directory))
            except OSError as error:
                raise SlotCompromisedError(str(error)) from error
            return
        try:
            reaper = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    str(LAUNCHER_PATH),
                    "reap",
                    str(self._slot.uid),
                    str(self._slot.directory),
                    str(FIRST_REAPER_UID + self._slot.uid - FIRST_SLOT_UID),
                ],
                stdin=subprocess.DEVNULL,
                env={},
            )
        except OSError as error:
            raise SlotCompromisedError(f"{self._slot}: {error}") from error
        try:
            exit_code = reaper.wait(timeout=REAP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            try:
                reaper.kill()
            except OSError:
                logger.warning("could not kill the timed-out reaper")
            # Collect it whenever it ends, without blocking this request.
            threading.Thread(target=reaper.wait, daemon=True).start()
            raise SlotCompromisedError(f"{self._slot}: {error}") from error
        if exit_code != 0:
            raise SlotCompromisedError(
                f"{self._slot}: reaping failed with exit code {exit_code}"
            )
