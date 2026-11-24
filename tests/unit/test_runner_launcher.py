"""
File: test_runner_launcher.py
Description: Unit tests for the sandbox launcher: privilege dropping,
    resource limits, the code handoff on stdin, the exec call, and the
    reap guard. OS calls are patched, so nothing switches users here.
Author(s): Richard Hall
"""

import os
import resource
from pathlib import Path
from unittest import mock

import pytest

from src.runner import launcher
from src.runner.launcher import LauncherError
from src.runner.limits import SandboxLimits

LIMITS = SandboxLimits()


def pipe_with(data: bytes) -> int:
    read_end, write_end = os.pipe()
    os.write(write_end, data)
    os.close(write_end)
    return read_end


def test_parse_uid():
    assert launcher.parse_uid("-") is None
    assert launcher.parse_uid("10001") == 10001


def test_drop_privileges_refuses_root():
    with pytest.raises(LauncherError, match="root"):
        launcher.drop_privileges(0)


@mock.patch.object(launcher.os, "setuid")
@mock.patch.object(launcher.os, "setgid")
@mock.patch.object(launcher.os, "setgroups")
def test_drop_privileges_clears_groups_then_switches(
    setgroups, setgid, setuid
):
    setuid.side_effect = [None, PermissionError]
    with (
        mock.patch.object(launcher.os, "getuid", return_value=10001),
        mock.patch.object(launcher.os, "geteuid", return_value=10001),
    ):
        launcher.drop_privileges(10001)
    setgroups.assert_called_once_with([])
    setgid.assert_called_once_with(10001)
    assert setuid.call_args_list == [mock.call(10001), mock.call(0)]


@mock.patch.object(launcher.os, "setuid")
@mock.patch.object(launcher.os, "setgid")
@mock.patch.object(launcher.os, "setgroups")
def test_drop_privileges_detects_failed_switch(setgroups, setgid, setuid):
    with mock.patch.object(launcher.os, "getuid", return_value=0):
        with pytest.raises(LauncherError, match="could not switch"):
            launcher.drop_privileges(10001)


@mock.patch.object(launcher.os, "setuid")
@mock.patch.object(launcher.os, "setgid")
@mock.patch.object(launcher.os, "setgroups")
def test_drop_privileges_detects_reachable_root(setgroups, setgid, setuid):
    with (
        mock.patch.object(launcher.os, "getuid", return_value=10001),
        mock.patch.object(launcher.os, "geteuid", return_value=10001),
    ):
        with pytest.raises(LauncherError, match="still reachable"):
            launcher.drop_privileges(10001)


def test_apply_limits_sets_every_cap():
    limits = {
        "cpu_seconds": 10,
        "file_size_bytes": 100,
        "process_count": 16,
        "memory_bytes": 2048,
    }
    with mock.patch.object(launcher.resource, "setrlimit") as setrlimit:
        launcher.apply_limits(limits)
    assert dict(call.args for call in setrlimit.call_args_list) == {
        resource.RLIMIT_CPU: (10, 10),
        resource.RLIMIT_FSIZE: (100, 100),
        resource.RLIMIT_NPROC: (16, 16),
        resource.RLIMIT_CORE: (0, 0),
        resource.RLIMIT_AS: (2048, 2048),
    }


def test_apply_limits_can_leave_memory_unset():
    limits = {
        "cpu_seconds": 1,
        "file_size_bytes": 1,
        "process_count": 1,
        "memory_bytes": None,
    }
    with mock.patch.object(launcher.resource, "setrlimit") as setrlimit:
        launcher.apply_limits(limits)
    set_limits = [call.args[0] for call in setrlimit.call_args_list]
    assert resource.RLIMIT_AS not in set_limits


def test_read_code_leaves_tick_input_in_the_pipe():
    fd = pipe_with(b"11\nprint('hi')first tick\n")
    try:
        assert launcher.read_code(fd, 100) == b"print('hi')"
        assert os.read(fd, 100) == b"first tick\n"
    finally:
        os.close(fd)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "stdin closed"),
        (b"5\nab", "stdin closed"),
        (b"999\n", "larger than the limit"),
        (b"1" * 30, "header is too long"),
    ],
)
def test_read_code_rejects_bad_messages(data: bytes, message: str):
    fd = pipe_with(data)
    try:
        with pytest.raises(LauncherError, match=message):
            launcher.read_code(fd, 100)
    finally:
        os.close(fd)


def test_child_environment_is_bare(tmp_path: Path):
    assert launcher.child_environment(tmp_path) == {
        "PATH": launcher.CHILD_PATH,
        "HOME": str(tmp_path),
        "LANG": "C.UTF-8",
    }


def test_start_program_execs_python_isolated(tmp_path: Path):
    status_read, status_write = os.pipe()
    stdin = pipe_with(b"5\nx = 1")
    argv = ["10001", str(tmp_path), LIMITS.to_json(), str(status_write)]
    with (
        mock.patch.object(launcher, "drop_privileges") as drop,
        mock.patch.object(launcher, "apply_limits"),
        mock.patch.object(launcher.os, "chdir"),
        mock.patch.object(launcher.os, "execve") as execve,
        mock.patch.object(
            launcher, "read_code", side_effect=lambda fd, size: b"x = 1"
        ),
    ):
        launcher.start_program(argv)
    os.close(stdin)
    os.close(status_write)
    os.close(status_read)
    drop.assert_called_once_with(10001)
    assert (tmp_path / "main.py").read_bytes() == b"x = 1"
    executable, args, env = execve.call_args.args
    assert args[1:] == ["-I", "-u", "main.py"]
    assert env["HOME"] == str(tmp_path)


def test_start_program_reports_setup_failure(tmp_path: Path):
    status_read, status_write = os.pipe()
    argv = ["0", str(tmp_path), LIMITS.to_json(), str(status_write)]
    result = launcher.start_program(argv)
    os.close(status_write)
    message = os.read(status_read, 500)
    os.close(status_read)
    assert result == launcher.LAUNCH_FAILED_EXIT
    assert message.startswith(b"LauncherError: refusing")


def test_clear_directory_removes_locked_folders(tmp_path: Path):
    locked = tmp_path / "locked"
    (locked / "inner").mkdir(parents=True)
    (locked / "inner" / "file.txt").write_text("x")
    (tmp_path / "file.txt").write_text("x")
    (tmp_path / "link").symlink_to("/etc")
    os.chmod(locked / "inner", 0)
    os.chmod(locked, 0)
    launcher.clear_directory(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_reap_refuses_host_mode():
    with pytest.raises(LauncherError, match="needs a sandbox uid"):
        launcher.reap_slot(["-", "/tmp"])


def test_reap_kills_as_the_slot_user(tmp_path: Path):
    (tmp_path / "left.txt").write_text("x")
    with (
        mock.patch.object(launcher, "drop_privileges") as drop,
        mock.patch.object(
            launcher.os, "kill", side_effect=ProcessLookupError
        ) as kill,
    ):
        assert launcher.reap_slot(["10002", str(tmp_path)]) == 0
    drop.assert_called_once_with(10002)
    kill.assert_called_once_with(-1, launcher.signal.SIGKILL)
    assert list(tmp_path.iterdir()) == []


def test_main_dispatches_and_rejects_bad_usage(capsys):
    with mock.patch.object(launcher, "start_program", return_value=7):
        assert launcher.main(["l", "run", "1", "d", "{}", "3"]) == 7
    with mock.patch.object(launcher, "reap_slot", return_value=0):
        assert launcher.main(["l", "reap", "1", "d"]) == 0
    assert launcher.main(["l", "nope"]) == launcher.USAGE_EXIT
    assert "usage" in capsys.readouterr().err
