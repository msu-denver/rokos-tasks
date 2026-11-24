"""
File: launcher.py
Description: Runs inside each sandbox child. In "run" mode it switches to
    the slot's unprivileged user, applies resource limits, receives the
    player's code on stdin, and execs `python -I -u main.py` with a bare
    environment. In "reap" mode it kills every process the slot user owns
    and empties the slot folder. Started as `python -I launcher.py`, so it
    imports only the standard library, never `src`.
Author(s): Tyler Black
"""

import json
import os
import resource
import shutil
import signal
import sys
from pathlib import Path

LAUNCH_FAILED_EXIT = 70
USAGE_EXIT = 64
MAX_HEADER_BYTES = 20
MAX_STATUS_BYTES = 500
CHILD_PATH = "/usr/local/bin:/usr/bin:/bin"
HOST_MODE_UID = "-"


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
    caps = [
        (resource.RLIMIT_CPU, limits["cpu_seconds"]),
        (resource.RLIMIT_FSIZE, limits["file_size_bytes"]),
        (resource.RLIMIT_NPROC, limits["process_count"]),
        (resource.RLIMIT_CORE, 0),
    ]
    if limits["memory_bytes"] is not None:
        caps.append((resource.RLIMIT_AS, limits["memory_bytes"]))
    for limit, value in caps:
        resource.setrlimit(limit, (value, value))


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
        argv: ``[uid, directory, limits_json, status_fd]``.

    Returns:
        ``LAUNCH_FAILED_EXIT`` if setup failed. On success, exec replaces
        this process and nothing returns.
    """
    status_fd = int(argv[3])
    try:
        uid = parse_uid(argv[0])
        directory = Path(argv[1])
        limits = json.loads(argv[2])
        if uid is not None:
            drop_privileges(uid)
        apply_limits(limits)
        os.chdir(directory)
        code = read_code(0, limits["code_bytes"])
        (directory / "main.py").write_bytes(code)
        # Closed by exec, which is how the server knows the launch worked.
        os.set_inheritable(status_fd, False)
        os.execve(
            sys.executable,
            [sys.executable, "-I", "-u", "main.py"],
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


def reap_slot(argv: list[str]) -> int:
    """Kill every process of the slot user, then empty its folder.

    Args:
        argv: ``[uid, directory]``. Host mode is refused, because
            ``kill(-1)`` as the developer would kill their own session.

    Returns:
        0 on success.
    """
    uid = parse_uid(argv[0])
    if uid is None:
        raise LauncherError("reap needs a sandbox uid")
    drop_privileges(uid)
    try:
        os.kill(-1, signal.SIGKILL)
    except ProcessLookupError:
        pass
    clear_directory(Path(argv[1]))
    return 0


def main(argv: list[str]) -> int:
    """Dispatch to run or reap mode.

    Args:
        argv: The full ``sys.argv``.

    Returns:
        The process exit code.
    """
    if len(argv) == 6 and argv[1] == "run":
        return start_program(argv[2:])
    if len(argv) == 4 and argv[1] == "reap":
        return reap_slot(argv[2:])
    sys.stderr.write("usage: launcher.py run|reap ...\n")
    return USAGE_EXIT


if __name__ == "__main__":  # pragma: no cover - runs only as a script
    sys.exit(main(sys.argv))
