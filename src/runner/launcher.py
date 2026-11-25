"""
File: launcher.py
Description: Runs inside each sandbox child. In "run" mode it switches to
    the slot's unprivileged user, applies resource limits, receives the
    player's code on stdin, saves it as main.py, and execs Python with a
    bare environment to run it like `python main.py`. A small bootstrap
    announces each read of stdin on an extra pipe, so the server knows
    when the program is waiting for input. In "reap" mode it kills every
    process the slot user owns and empties the slot folder. Started as
    `python -I launcher.py`, so it imports only the standard library,
    never `src`.
Author(s): Richard Hall, Tyler Black
"""

import json
import os
import shutil
import signal
import sys
import time
from pathlib import Path

LAUNCH_FAILED_EXIT = 70
USAGE_EXIT = 64
MAX_HEADER_BYTES = 20
MAX_STATUS_BYTES = 500
CHILD_PATH = "/usr/local/bin:/usr/bin:/bin"
HOST_MODE_UID = "-"
REAP_ROUNDS = 50
REAP_POLL_SECONDS = 0.01
# Runs main.py as `__main__`, like `python main.py`. Every read of stdin
# (input() included) first writes one byte to the "waiting" pipe whose fd
# is argv[1], so the server knows the screen so far is complete. A crash
# prints the traceback without the bootstrap's or runpy's frames.
BOOTSTRAP = """\
import os
import runpy
import sys
import traceback

WAITING_FD = int(sys.argv.pop(1))
READS = {"read", "read1", "readinto", "readinto1", "readline", "readlines"}


def announce():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    try:
        os.write(WAITING_FD, b"?")
    except OSError:
        pass


class Stdin:
    def __init__(self, stream):
        self._stream = stream

    def __getattr__(self, name):
        value = getattr(self._stream, name)
        if name == "buffer":
            return Stdin(value)
        if name not in READS:
            return value

        def read(*args, **kwargs):
            announce()
            return value(*args, **kwargs)

        return read

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line


def hide_plumbing(error, seen):
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        kept = []
        trace = error.__traceback__
        while trace is not None:
            if not any(trace.tb_frame.f_globals is g for g in HIDDEN):
                kept.append(trace)
            trace = trace.tb_next
        for trace, after in zip(kept, kept[1:] + [None]):
            trace.tb_next = after
        error.__traceback__ = kept[0] if kept else None
        if isinstance(error, BaseExceptionGroup):
            for member in error.exceptions:
                hide_plumbing(member, seen)
        hide_plumbing(error.__cause__, seen)
        error = error.__context__


HIDDEN = (globals(), runpy.__dict__)
sys.stdin = Stdin(sys.stdin)
try:
    runpy.run_path("main.py", run_name="__main__")
except SystemExit:
    raise
except BaseException as error:
    try:
        hide_plumbing(error, set())
    except Exception:
        pass  # Never lose the player's traceback over a cosmetic step.
    traceback.print_exception(error)
    sys.exit(1)
"""


class LauncherError(Exception):
    """Raised when the sandbox can't be set up safely."""


def parse_uid(text: str) -> int | None:
    """Return the slot uid, or None for host mode (unit tests only)."""
    return None if text == HOST_MODE_UID else int(text)


def drop_privileges(uid: int) -> None:
    """Switch the process to ``uid`` for good, with no extra groups.

    Args:
        uid: The slot user. Its group id has the same number.

    Raises:
        LauncherError: If ``uid`` is root or root could be regained.
    """
    if uid == 0:
        raise LauncherError("refusing to run player code as root")
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)
    if os.getuid() != uid or os.geteuid() != uid:
        raise LauncherError("could not switch to the sandbox user")
    try:
        os.setuid(0)
    except PermissionError:
        return
    raise LauncherError("root was still reachable after dropping it")


def apply_limits(limits: dict) -> None:
    """Set the kernel resource limits for this process and its children.

    Args:
        limits: The fields of ``SandboxLimits`` as a dict.
    """
    import resource

    caps = [
        (resource.RLIMIT_CPU, limits["cpu_seconds"]),
        (resource.RLIMIT_FSIZE, limits["file_size_bytes"]),
        (resource.RLIMIT_NPROC, limits["process_count"]),
        (resource.RLIMIT_NOFILE, limits["open_files"]),
        (resource.RLIMIT_CORE, 0),
    ]
    if limits["memory_bytes"] is not None:
        caps.append((resource.RLIMIT_AS, limits["memory_bytes"]))
    if sys.platform == "linux":
        caps.append((resource.RLIMIT_MSGQUEUE, 0))
    for limit, value in caps:
        resource.setrlimit(limit, (value, value))


def prefer_oom_victim(path: Path = Path("/proc/self/oom_score_adj")) -> None:
    """Ask Linux to prefer this program and its children as OOM victims."""
    try:
        path.write_text("1000\n", encoding="ascii")
    except OSError:
        pass  # Best effort on kernels that don't expose a writable score.


def read_exact(fd: int, count: int) -> bytes:
    """Read exactly ``count`` bytes, so later stdin input is untouched."""
    data = bytearray()
    while len(data) < count:
        chunk = os.read(fd, count - len(data))
        if not chunk:
            raise LauncherError("stdin closed before the code arrived")
        data += chunk
    return bytes(data)


def read_code(fd: int, max_bytes: int) -> bytes:
    """Read the length line, then the code, that the server sends first.

    Args:
        fd: The stdin file descriptor.
        max_bytes: The largest code size allowed.

    Returns:
        The player's source code.

    Raises:
        LauncherError: If the message is malformed or too large.
    """
    header = b""
    while not header.endswith(b"\n"):
        if len(header) > MAX_HEADER_BYTES:
            raise LauncherError("code length header is too long")
        header += read_exact(fd, 1)
    length = int(header)
    if not 0 <= length <= max_bytes:
        raise LauncherError("code is larger than the limit")
    return read_exact(fd, length)


def child_environment(directory: Path) -> dict[str, str]:
    """Return the only environment variables the player program sees."""
    return {"PATH": CHILD_PATH, "HOME": str(directory), "LANG": "C.UTF-8"}


def start_program(argv: list[str]) -> int:
    """Set up the sandbox and exec the player's program.

    Args:
        argv: ``[uid, directory, limits_json, status_fd, waiting_fd]``.

    Returns:
        ``LAUNCH_FAILED_EXIT`` if setup failed. On success, exec replaces
        this process and nothing returns.
    """
    status_fd = int(argv[3])
    waiting_fd = int(argv[4])
    try:
        uid = parse_uid(argv[0])
        directory = Path(argv[1])
        limits = json.loads(argv[2])
        if uid is not None:
            if uid > 0:
                prefer_oom_victim()
            drop_privileges(uid)
        apply_limits(limits)
        os.chdir(directory)
        code = read_code(0, limits["code_bytes"])
        (directory / "main.py").write_bytes(code)
        # Closed by exec, which is how the server knows the launch worked.
        os.set_inheritable(status_fd, False)
        os.set_inheritable(waiting_fd, True)
        os.execve(
            sys.executable,
            [sys.executable, "-I", "-u", "-c", BOOTSTRAP, str(waiting_fd)],
            child_environment(directory),
        )
    except (OSError, ValueError, KeyError, LauncherError) as error:
        message = f"{type(error).__name__}: {error}"
        os.write(status_fd, message.encode()[:MAX_STATUS_BYTES])
    return LAUNCH_FAILED_EXIT


def clear_directory(directory: Path) -> None:
    """Delete everything inside ``directory`` but keep the folder itself.

    Folders a player locked with ``chmod 000`` are unlocked first, since
    the slot user owns them.
    """
    for entry in directory.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            unlock_tree(entry)
            shutil.rmtree(entry)
        else:
            entry.unlink()


def unlock_tree(root: Path) -> None:
    """Give the owner full access to ``root`` and every folder inside it.

    Walks top-down and unlocks each folder before ``os.walk`` lists it.
    Symlinks are never followed.
    """
    os.chmod(root, 0o700)
    for folder, subfolders, _files in os.walk(root):
        for name in subfolders:
            path = os.path.join(folder, name)
            if not os.path.islink(path):
                os.chmod(path, 0o700)


def slot_has_processes(proc_root: Path, uid: int, reaper_pid: int) -> bool:
    """Find any live process whose real or saved UID matches the slot."""
    for entry in proc_root.iterdir():
        if not entry.name.isdecimal() or entry.name == str(reaper_pid):
            continue
        try:
            status = (entry / "status").read_bytes()
        except (FileNotFoundError, ProcessLookupError):
            continue  # The process exited during the scan.
        fields = dict(
            line.split(b":", 1) for line in status.split(b"\n") if b":" in line
        )
        if fields[b"State"].split()[0] == b"Z":
            continue
        real, _effective, saved, _filesystem = map(int, fields[b"Uid"].split())
        if uid in (real, saved):
            return True
    return False


def reap_slot(argv: list[str]) -> int:
    """Kill every process of the slot user, then empty its folder.

    Args:
        argv: ``[uid, directory, reaper_uid]``. Host mode is refused, because
            ``kill(-1)`` as the developer would kill their own session.

    Returns:
        0 on success.
    """
    uid = parse_uid(argv[0])
    if uid is None:
        raise LauncherError("reap needs a sandbox uid")
    reaper_uid = int(argv[2])
    if min(uid, reaper_uid) <= 0 or uid == reaper_uid:
        raise LauncherError("reaping needs two distinct non-root uids")
    os.setgroups([])
    # The effective UID lets us signal slot processes. Linux checks the
    # target's real and saved UIDs, which shield us from their signals.
    os.setresgid(reaper_uid, uid, reaper_uid)
    os.setresuid(reaper_uid, uid, reaper_uid)
    for _ in range(REAP_ROUNDS):
        try:
            os.kill(-1, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if not slot_has_processes(Path("/proc"), uid, os.getpid()):
            directory = Path(argv[1])
            directory.chmod(0o700)
            clear_directory(directory)
            return 0
        time.sleep(REAP_POLL_SECONDS)
    raise LauncherError("slot processes survived reaping")


def main(argv: list[str]) -> int:
    """Dispatch to run or reap mode.

    Args:
        argv: The full ``sys.argv``.

    Returns:
        The process exit code.
    """
    if len(argv) == 7 and argv[1] == "run":
        return start_program(argv[2:])
    if len(argv) == 5 and argv[1] == "reap":
        return reap_slot(argv[2:])
    sys.stderr.write("usage: launcher.py run|reap ...\n")
    return USAGE_EXIT


if __name__ == "__main__":  # pragma: no cover - runs only as a script
    sys.exit(main(sys.argv))
