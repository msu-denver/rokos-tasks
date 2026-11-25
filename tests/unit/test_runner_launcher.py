"""
File: test_runner_launcher.py
Description: Unit tests for the sandbox launcher: privilege dropping,
    resource limits, the code handoff on stdin, the exec call, and the
    reap guard. OS calls are patched, so nothing switches users here.
Author(s): Richard Hall, Tyler Black
"""

import os
import stat
import sys
from pathlib import Path
from unittest import mock

import pytest

from src.runner import launcher
from src.runner.launcher import LauncherError
from src.runner.limits import SandboxLimits

LIMITS = SandboxLimits()
POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="Linux only; CI runs it (POSIX APIs)"
)


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


@POSIX_ONLY
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


@POSIX_ONLY
@mock.patch.object(launcher.os, "setuid")
@mock.patch.object(launcher.os, "setgid")
@mock.patch.object(launcher.os, "setgroups")
def test_drop_privileges_detects_failed_switch(setgroups, setgid, setuid):
    with mock.patch.object(launcher.os, "getuid", return_value=0):
        with pytest.raises(LauncherError, match="could not switch"):
            launcher.drop_privileges(10001)


@POSIX_ONLY
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


@POSIX_ONLY
def test_apply_limits_sets_every_cap():
    import resource

    limits = {
        "cpu_seconds": 10,
        "file_size_bytes": 100,
        "process_count": 16,
        "open_files": 64,
        "memory_bytes": 2048,
    }
    with mock.patch.object(resource, "setrlimit") as setrlimit:
        launcher.apply_limits(limits)
    expected = {
        resource.RLIMIT_CPU: (10, 10),
        resource.RLIMIT_FSIZE: (100, 100),
        resource.RLIMIT_NPROC: (16, 16),
        resource.RLIMIT_NOFILE: (64, 64),
        resource.RLIMIT_CORE: (0, 0),
        resource.RLIMIT_AS: (2048, 2048),
    }
    if sys.platform == "linux":
        expected[resource.RLIMIT_MSGQUEUE] = (0, 0)
    assert dict(call.args for call in setrlimit.call_args_list) == expected


@POSIX_ONLY
def test_apply_limits_can_leave_memory_unset():
    import resource

    limits = {
        "cpu_seconds": 1,
        "file_size_bytes": 1,
        "process_count": 1,
        "open_files": 64,
        "memory_bytes": None,
    }
    with mock.patch.object(resource, "setrlimit") as setrlimit:
        launcher.apply_limits(limits)
    set_limits = [call.args[0] for call in setrlimit.call_args_list]
    assert resource.RLIMIT_AS not in set_limits


@POSIX_ONLY
def test_linux_message_queue_limit_is_zero() -> None:
    import resource

    with (
        mock.patch.object(launcher.sys, "platform", "linux"),
        mock.patch.object(resource, "RLIMIT_MSGQUEUE", 12, create=True),
        mock.patch.object(resource, "setrlimit") as setrlimit,
    ):
        launcher.apply_limits(
            {
                "cpu_seconds": 1,
                "file_size_bytes": 1,
                "process_count": 1,
                "open_files": 64,
                "memory_bytes": None,
            }
        )
    setrlimit.assert_any_call(12, (0, 0))


def test_read_code_leaves_the_first_input_in_the_pipe():
    fd = pipe_with(b"11\nprint('hi')first input\n")
    try:
        assert launcher.read_code(fd, 100) == b"print('hi')"
        assert os.read(fd, 100) == b"first input\n"
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


def test_prefer_oom_victim_writes_the_score(tmp_path: Path) -> None:
    score = tmp_path / "oom_score_adj"
    launcher.prefer_oom_victim(score)
    assert score.read_text() == "1000\n"
    launcher.prefer_oom_victim(tmp_path / "missing" / "oom_score_adj")


@pytest.mark.parametrize("uid", ["10001", "-"])
def test_start_program_execs_python_isolated(tmp_path: Path, uid: str):
    status_read, status_write = os.pipe()
    waiting_read, waiting_write = os.pipe()
    stdin = pipe_with(b"5\nx = 1")
    argv = [
        uid,
        str(tmp_path),
        LIMITS.to_json(),
        str(status_write),
        str(waiting_write),
    ]
    setup = mock.Mock()
    with (
        mock.patch.object(launcher, "drop_privileges", setup.drop),
        mock.patch.object(launcher, "prefer_oom_victim", setup.prefer_oom),
        mock.patch.object(launcher, "apply_limits"),
        mock.patch.object(launcher.os, "chdir"),
        mock.patch.object(launcher.os, "execve") as execve,
        mock.patch.object(
            launcher, "read_code", side_effect=lambda fd, size: b"x = 1"
        ),
    ):
        launcher.start_program(argv)
    assert not os.get_inheritable(status_write)
    assert os.get_inheritable(waiting_write)
    for fd in (stdin, status_write, status_read, waiting_read, waiting_write):
        os.close(fd)
    if uid == "10001":
        assert setup.mock_calls == [
            mock.call.prefer_oom(),
            mock.call.drop(10001),
        ]
    else:
        assert setup.mock_calls == []
    assert (tmp_path / "main.py").read_bytes() == b"x = 1"
    executable, args, env = execve.call_args.args
    assert args[1:] == [
        "-I",
        "-u",
        "-c",
        launcher.BOOTSTRAP,
        str(waiting_write),
    ]
    assert env["HOME"] == str(tmp_path)


def test_start_program_reports_setup_failure(tmp_path: Path):
    status_read, status_write = os.pipe()
    argv = ["0", str(tmp_path), LIMITS.to_json(), str(status_write), "9"]
    result = launcher.start_program(argv)
    os.close(status_write)
    message = os.read(status_read, 500)
    os.close(status_read)
    assert result == launcher.LAUNCH_FAILED_EXIT
    assert message.startswith(b"LauncherError: refusing")


@POSIX_ONLY
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
        launcher.reap_slot(["-", "/tmp", "20001"])


@pytest.mark.parametrize(
    ("uid", "reaper_uid"), [("0", "20001"), ("10001", "0"), ("10001", "10001")]
)
def test_reap_refuses_unsafe_uid_pairs(uid: str, reaper_uid: str) -> None:
    with pytest.raises(LauncherError, match="distinct non-root"):
        launcher.reap_slot([uid, "/tmp", reaper_uid])


@pytest.mark.parametrize("mode", [0o000, 0o777])
@POSIX_ONLY
def test_reap_kills_as_the_slot_user(tmp_path: Path, mode: int):
    (tmp_path / "left.txt").write_text("x")
    tmp_path.chmod(mode)
    with (
        mock.patch.object(launcher.os, "setgroups") as setgroups,
        mock.patch.object(launcher.os, "setresgid", create=True) as setresgid,
        mock.patch.object(launcher.os, "setresuid", create=True) as setresuid,
        mock.patch.object(
            launcher, "slot_has_processes", side_effect=[True, False]
        ),
        mock.patch.object(
            launcher.os, "kill", side_effect=[None, ProcessLookupError]
        ) as kill,
    ):
        assert launcher.reap_slot(["10002", str(tmp_path), "20002"]) == 0
    setgroups.assert_called_once_with([])
    setresgid.assert_called_once_with(20002, 10002, 20002)
    setresuid.assert_called_once_with(20002, 10002, 20002)
    assert kill.call_args_list == [mock.call(-1, launcher.signal.SIGKILL)] * 2
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
    assert list(tmp_path.iterdir()) == []


def test_reap_fails_when_processes_survive(tmp_path: Path) -> None:
    with (
        mock.patch.object(launcher.os, "setgroups", create=True),
        mock.patch.object(launcher.os, "setresgid", create=True),
        mock.patch.object(launcher.os, "setresuid", create=True),
        mock.patch.object(launcher.os, "kill") as kill,
        mock.patch.object(launcher.signal, "SIGKILL", 9, create=True),
        mock.patch.object(launcher, "slot_has_processes", return_value=True),
        mock.patch.object(launcher.time, "sleep"),
        pytest.raises(LauncherError, match="survived reaping"),
    ):
        launcher.reap_slot(["10002", str(tmp_path), "20002"])
    assert kill.call_count == launcher.REAP_ROUNDS


def test_slot_process_scan_checks_real_and_saved_uids(tmp_path: Path) -> None:
    for pid, state, uids in [
        (1, "S", "0 0 0 0"),
        (2, "Z", "10002 10002 10002 10002"),
        (3, "S", "20002 10002 20002 10002"),
        (4, "S", "10002 10002 10002 10002"),
    ]:
        folder = tmp_path / str(pid)
        folder.mkdir()
        (folder / "status").write_text(f"State:\t{state}\nUid:\t{uids}\n")
    (tmp_path / "5").mkdir()  # Exited before its status could be read.
    (tmp_path / "self").mkdir()
    assert not launcher.slot_has_processes(tmp_path, 10002, reaper_pid=4)
    for uids in ("10002 10003 10003 10003", "10003 10003 10002 10003"):
        (tmp_path / "5" / "status").write_text(f"State:\tT\nUid:\t{uids}\n")
        assert launcher.slot_has_processes(tmp_path, 10002, reaper_pid=4)


def test_main_dispatches_and_rejects_bad_usage(capsys):
    with mock.patch.object(launcher, "start_program", return_value=7):
        assert launcher.main(["l", "run", "1", "d", "{}", "3", "4"]) == 7
    with mock.patch.object(launcher, "reap_slot", return_value=0):
        assert launcher.main(["l", "reap", "1", "d", "2"]) == 0
    assert launcher.main(["l", "nope"]) == launcher.USAGE_EXIT
    assert "usage" in capsys.readouterr().err
