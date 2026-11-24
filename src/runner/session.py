"""
File: session.py
Description: One sandboxed run of a player program. Starts the program
    through the launcher in a borrowed slot, sends one input line per
    tick, reads back one frame (ending with a line of only `---`) under
    the tick and run deadlines, and kills everything when the run ends.
Author(s): Richard Hall
"""

import logging
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import TracebackType

from src.runner.launcher import clear_directory
from src.runner.limits import SandboxLimits
from src.runner.slots import Slot, SlotCompromisedError

LAUNCHER_PATH = Path(__file__).with_name("launcher.py")
FRAME_END = b"---\n"
READ_CHUNK_BYTES = 65536
EXIT_WAIT_SECONDS = 1.0
REAP_TIMEOUT_SECONDS = 5.0

logger = logging.getLogger(__name__)


class SandboxError(Exception):
    """Base class for everything that can end a sandboxed run early."""


class LaunchError(SandboxError):
    """The sandbox itself failed. Never the player's fault."""


class ProgramError(SandboxError):
    """The player's program broke the tick contract or a limit."""

    status = "failed"


class ProgramCrashedError(ProgramError):
    """The program exited with an error or was killed by a limit."""

    status = "crashed"


class ProgramExitedError(ProgramError):
    """The program exited cleanly before the run was over."""

    status = "exited"


class TickTimeoutError(ProgramError):
    """The program took longer than one tick to print its frame."""

    status = "tick_timeout"


class RunTimeoutError(ProgramError):
    """The whole run took longer than the run limit."""

    status = "run_timeout"


class OutputLimitError(ProgramError):
    """The program printed more than the output limit."""

    status = "output_limit"


class ProgramSession:
    """Runs one player program in one slot, one tick at a time.

    Use as a context manager: ``start`` the program, call ``tick`` for
    each input line, and leaving the block kills the program and empties
    the slot. ``stderr`` and ``exit_code`` are filled in by then.
    """

    def __init__(self, slot: Slot, limits: SandboxLimits) -> None:
        """Prepare a session in ``slot`` under ``limits``."""
        self._slot = slot
        self._limits = limits
        self._process: subprocess.Popen[bytes] | None = None
        self._selector = selectors.DefaultSelector()
        self._stdin_selector = selectors.DefaultSelector()
        self._stdout = b""
        self._stderr = b""
        self._stdout_open = False
        self._run_deadline = 0.0
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
        status_read, status_write = os.pipe()
        try:
            self._process = self._spawn_launcher(status_write)
        except OSError as error:
            os.close(status_read)
            raise LaunchError(
                f"could not start the launcher: {error}"
            ) from error
        finally:
            os.close(status_write)
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
            os.close(status_read)
            raise LaunchError("the launcher did not take the code") from error
        self._wait_for_launch(status_read)
        self._selector.register(self._process.stdout, selectors.EVENT_READ)
        self._selector.register(self._process.stderr, selectors.EVENT_READ)
        self._stdout_open = True

    def _spawn_launcher(self, status_write: int) -> subprocess.Popen[bytes]:
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
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(status_write,),
            start_new_session=True,
            env={},
        )

    def _wait_for_launch(self, status_read: int) -> None:
        """Wait until exec closes the status pipe, or report why it didn't.

        Raises:
            LaunchError: If the launcher reported a failure or hung.
        """
        with selectors.DefaultSelector() as status_selector:
            status_selector.register(status_read, selectors.EVENT_READ)
            ready = status_selector.select(self._remaining())
        try:
            message = os.read(status_read, 500) if ready else None
        finally:
            os.close(status_read)
        if message is None:
            raise LaunchError("the launcher did not start in time")
        if message:
            raise LaunchError(message.decode("utf-8", "replace"))

    def tick(self, line: str) -> str:
        """Send one input line and return the frame the program prints.

        Args:
            line: The tick's input, without a newline.

        Returns:
            The frame text, without the closing ``---`` line.

        Raises:
            ProgramError: If the program crashed, exited, timed out, or
                printed too much.
        """
        tick_deadline = time.monotonic() + self._limits.tick_seconds
        deadline = min(tick_deadline, self._run_deadline)
        self._write(line.encode() + b"\n", deadline)
        while True:
            frame = self._pop_frame()
            if frame is not None:
                return frame
            if not self._stdout_open:
                raise self._ended_error(deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._timeout_error(deadline)
            self._pump(remaining)

    def _timeout_error(self, deadline: float) -> ProgramError:
        """Return the timeout matching whichever deadline just passed."""
        if deadline == self._run_deadline:
            return RunTimeoutError("the run took too long")
        return TickTimeoutError("the tick took too long")

    def _remaining(self) -> float:
        """Return the seconds left in the run, never below zero."""
        return max(0.0, self._run_deadline - time.monotonic())

    def _write(self, data: bytes, deadline: float) -> None:
        """Write all of ``data`` to stdin before ``deadline``.

        Stdin is non-blocking, so a program that never reads its input
        can't stall the runner past the deadline. A program that already
        quit is ignored here; the read side reports how it ended.

        Raises:
            TickTimeoutError: If the pipe stays full past a tick deadline.
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

    def _pop_frame(self) -> str | None:
        """Remove and return the next whole frame, if one has arrived."""
        if self._stdout.startswith(FRAME_END):
            end = 0
        else:
            marker = self._stdout.find(b"\n" + FRAME_END)
            if marker < 0:
                return None
            end = marker + 1
        frame = self._stdout[:end]
        self._stdout = self._stdout[end + len(FRAME_END) :]
        return frame.decode("utf-8", "replace").removesuffix("\n")

    def _pump(self, timeout: float) -> None:
        """Read whatever stdout and stderr have, waiting up to ``timeout``.

        Raises:
            OutputLimitError: If either stream goes over the output limit.
        """
        for key, _events in self._selector.select(timeout):
            chunk = os.read(key.fd, READ_CHUNK_BYTES)
            is_stdout = key.fileobj is self._process.stdout
            if not chunk:
                self._selector.unregister(key.fileobj)
                if is_stdout:
                    self._stdout_open = False
            elif is_stdout:
                self._stdout += chunk
            else:
                self._stderr += chunk
        limit = self._limits.output_bytes
        if len(self._stdout) > limit or len(self._stderr) > limit:
            self._stderr = self._stderr[:limit]
            raise OutputLimitError("the program printed too much")

    def _ended_error(self, deadline: float) -> ProgramError:
        """Return the error for a program whose stdout closed mid-tick."""
        try:
            wait = max(0.0, deadline - time.monotonic())
            returncode = self._process.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            return TickTimeoutError("the program closed its output")
        self._drain_stderr()
        if returncode == 0:
            return ProgramExitedError("the program exited early")
        return ProgramCrashedError(f"the program exited with {returncode}")

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
            except ProcessLookupError:
                pass
            try:
                clear_directory(self._slot.directory)
            except OSError as error:
                raise SlotCompromisedError(str(error)) from error
            return
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(LAUNCHER_PATH),
                    "reap",
                    str(self._slot.uid),
                    str(self._slot.directory),
                ],
                capture_output=True,
                timeout=REAP_TIMEOUT_SECONDS,
                env={},
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SlotCompromisedError(f"{self._slot}: {error}") from error
        if result.returncode != 0:
            raise SlotCompromisedError(
                f"{self._slot}: reaping failed: {result.stderr.decode()}"
            )
