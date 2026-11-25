"""
File: test_runner_session.py
Description: Unit tests for ProgramSession in host mode: real player
    subprocesses (benign ones only) driven tick by tick, with the frame
    parser, deadlines, output limit, and launch-failure path.
Author(s): Richard Hall, Tyler Black
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from textwrap import dedent
from unittest import mock

import pytest

from src.runner.limits import SandboxLimits
from src.runner.session import (
    REAP_TIMEOUT_SECONDS,
    LaunchError,
    OutputLimitError,
    ProgramCrashedError,
    ProgramExitedError,
    ProgramSession,
    RunTimeoutError,
    TickTimeoutError,
)
from src.runner.slots import Slot, SlotCompromisedError

# macOS rejects RLIMIT_AS, so host-mode tests leave memory unset.
POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="Linux only; CI runs it (POSIX APIs)"
)
HOST_LIMITS = SandboxLimits(memory_bytes=None, tick_seconds=2.0)

ECHO = dedent(
    """
    while True:
        line = input()
        print(f"row one {line}")
        print("row two")
        print("---")
    """
)


@pytest.fixture
def slot(tmp_path: Path) -> Slot:
    return Slot(uid=None, directory=tmp_path)


def play(
    slot: Slot,
    code: str,
    inputs: list[str],
    limits: SandboxLimits = HOST_LIMITS,
) -> tuple[list[str], ProgramSession]:
    frames: list[str] = []
    with ProgramSession(slot, limits) as session:
        session.start(code)
        for line in inputs:
            frames.append(session.tick(line))
    return frames, session


@POSIX_ONLY
def test_frames_come_back_one_per_tick(slot: Slot):
    frames, _ = play(slot, ECHO, ["q", "a"])
    assert frames == ["row one q\nrow two", "row one a\nrow two"]


@POSIX_ONLY
def test_empty_frame_is_allowed(slot: Slot):
    frames, _ = play(
        slot, "while True:\n    input()\n    print('---')\n", [""]
    )
    assert frames == [""]


@POSIX_ONLY
def test_frames_printed_together_are_split(slot: Slot):
    code = "input()\nprint('a\\n---\\nb\\n---')\ninput()\n"
    assert play(slot, code, ["", ""])[0] == ["a", "b"]


@POSIX_ONLY
def test_dash_line_must_be_exact(slot: Slot):
    code = "input()\nprint('a ---')\nprint('----')\nprint('---')\n"
    assert play(slot, code, [""])[0] == ["a ---\n----"]


@POSIX_ONLY
def test_crash_reports_traceback_without_launcher(slot: Slot):
    code = "input()\nraise ValueError('boom')\n"
    with pytest.raises(ProgramCrashedError):
        play(slot, code, [""])
    with ProgramSession(slot, HOST_LIMITS) as session:
        session.start(code)
        with pytest.raises(ProgramCrashedError):
            session.tick("")
    assert "ValueError: boom" in session.stderr
    assert 'main.py", line 2' in session.stderr
    assert "launcher" not in session.stderr
    assert session.exit_code == 1


@POSIX_ONLY
def test_clean_early_exit_is_reported(slot: Slot):
    with pytest.raises(ProgramExitedError):
        play(slot, "input()\n", [""])


@POSIX_ONLY
def test_program_that_quit_before_reading(slot: Slot):
    with pytest.raises(ProgramExitedError):
        play(slot, "", ["", ""])


@POSIX_ONLY
def test_tick_timeout(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, tick_seconds=0.3)
    with pytest.raises(TickTimeoutError):
        play(slot, "input()\nwhile True:\n    pass\n", [""], limits)


@POSIX_ONLY
def test_run_timeout(slot: Slot):
    limits = SandboxLimits(
        memory_bytes=None, tick_seconds=2.0, run_seconds=0.5
    )
    with pytest.raises(RunTimeoutError):
        play(slot, "import time\ninput()\ntime.sleep(5)\n", [""], limits)


@POSIX_ONLY
def test_stdout_output_limit(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, output_bytes=1000)
    with pytest.raises(OutputLimitError):
        play(slot, "input()\nprint('x' * 5000)\n", [""], limits)


@POSIX_ONLY
def test_stderr_output_limit_keeps_the_start(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, output_bytes=1000)
    code = "import sys\ninput()\nsys.stderr.write('e' * 5000)\n"
    code += "import time\ntime.sleep(5)\n"
    with ProgramSession(slot, limits) as session:
        session.start(code)
        with pytest.raises(OutputLimitError):
            session.tick("")
    assert session.stderr == "e" * 1000


@POSIX_ONLY
def test_closed_stdout_on_live_program_is_a_timeout(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, tick_seconds=0.5)
    code = "import os, time\ninput()\nos.close(1)\ntime.sleep(5)\n"
    with pytest.raises(TickTimeoutError):
        play(slot, code, [""], limits)


@POSIX_ONLY
def test_slot_folder_is_emptied(slot: Slot):
    code = "input()\nopen('left.txt', 'w').write('x')\nprint('---')\n"
    play(slot, code, [""])
    assert list(slot.directory.iterdir()) == []


@POSIX_ONLY
def test_launch_failure_is_a_launch_error(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, code_bytes=5)
    with ProgramSession(slot, limits) as session:
        with pytest.raises(LaunchError, match="larger than the limit"):
            session.start("print('too long')")


@POSIX_ONLY
def test_launcher_that_never_reports_is_a_launch_error(slot: Slot):
    session = ProgramSession(slot, HOST_LIMITS)
    session._run_deadline = 0.0
    read_end, write_end = os.pipe()
    try:
        with pytest.raises(LaunchError, match="did not start"):
            session._wait_for_launch(read_end)
    finally:
        os.close(write_end)


@POSIX_ONLY
def test_launcher_that_never_reads_the_code_is_a_launch_error(slot: Slot):
    with ProgramSession(slot, HOST_LIMITS) as session:
        with mock.patch.object(
            session, "_write", side_effect=RunTimeoutError("full")
        ):
            with pytest.raises(LaunchError, match="did not take the code"):
                session.start("print('hi')")


def test_spawn_failure_is_a_launch_error(slot: Slot):
    with ProgramSession(slot, HOST_LIMITS) as session:
        with mock.patch(
            "src.runner.session.subprocess.Popen",
            side_effect=BlockingIOError("fork failed"),
        ):
            with pytest.raises(LaunchError, match="fork failed"):
                session.start("print('hi')")


@POSIX_ONLY
def test_program_that_never_reads_input_cannot_stall_the_run(slot: Slot):
    """A program printing frames on a timer fills stdin; the run still ends."""
    limits = SandboxLimits(memory_bytes=None, run_seconds=2.0)
    code = (
        "import time\nwhile True:\n    print('---')\n    time.sleep(0.001)\n"
    )
    started = time.monotonic()
    with pytest.raises((RunTimeoutError, TickTimeoutError)):
        play(slot, code, ["x" * 64] * 2000, limits)
    assert time.monotonic() - started < 4


def test_close_before_start_does_nothing(slot: Slot):
    ProgramSession(slot, HOST_LIMITS).close()


def reap_with(tmp_path: Path, reaper: mock.Mock) -> mock.Mock:
    session = ProgramSession(Slot(10001, tmp_path), HOST_LIMITS)
    with mock.patch(
        "src.runner.session.subprocess.Popen", return_value=reaper
    ) as popen:
        session._reap(mock.Mock(pid=123))
    return popen


def test_reap_in_slot_mode_uses_the_launcher(tmp_path: Path):
    reaper = mock.Mock()
    reaper.wait.return_value = 0
    popen = reap_with(tmp_path, reaper)
    assert popen.call_args.args[0][-4:] == [
        "reap",
        "10001",
        str(tmp_path),
        "20001",
    ]
    reaper.wait.assert_called_once_with(timeout=REAP_TIMEOUT_SECONDS)


def test_failed_reap_compromises_the_slot(tmp_path: Path):
    reaper = mock.Mock()
    reaper.wait.return_value = 1
    with pytest.raises(SlotCompromisedError, match="exit code 1"):
        reap_with(tmp_path, reaper)


@pytest.mark.parametrize("kill_error", [None, PermissionError])
def test_hung_reaper_compromises_the_slot(
    tmp_path: Path, kill_error: type[OSError] | None
) -> None:
    reaper = mock.Mock()
    reaper.wait.side_effect = subprocess.TimeoutExpired(
        "r", REAP_TIMEOUT_SECONDS
    )
    reaper.kill.side_effect = kill_error
    with (
        mock.patch("src.runner.session.threading.Thread") as thread,
        pytest.raises(SlotCompromisedError),
    ):
        reap_with(tmp_path, reaper)
    assert reaper.mock_calls == [
        mock.call.wait(timeout=REAP_TIMEOUT_SECONDS),
        mock.call.kill(),
    ]
    # A reaper the server can't kill is still collected once it ends.
    thread.assert_called_once_with(target=reaper.wait, daemon=True)
    thread.return_value.start.assert_called_once_with()


@POSIX_ONLY
def test_reap_tolerates_a_group_of_only_zombies(slot: Slot):
    """MacOS answers EPERM to killpg when only zombies are left."""
    session = ProgramSession(slot, HOST_LIMITS)
    (slot.directory / "left.txt").write_text("x")
    with mock.patch(
        "src.runner.session.os.killpg", side_effect=PermissionError
    ):
        session._reap(mock.Mock(pid=123))
    assert list(slot.directory.iterdir()) == []


@POSIX_ONLY
def test_uncleanable_folder_compromises_the_slot(slot: Slot):
    session = ProgramSession(slot, HOST_LIMITS)
    with (
        mock.patch(
            "src.runner.session.clear_directory",
            side_effect=PermissionError("locked"),
        ),
        pytest.raises(SlotCompromisedError, match="locked"),
    ):
        session._reap(mock.Mock(pid=999999999))


@POSIX_ONLY
def test_survivor_after_reap_compromises_the_slot(slot: Slot):
    session = ProgramSession(slot, HOST_LIMITS)
    process = mock.Mock(pid=999999999)
    process.wait.side_effect = subprocess.TimeoutExpired("x", 1)
    session._process = process
    with pytest.raises(SlotCompromisedError, match="survived reaping"):
        session.close()
    process.stdout.close.assert_called_once()
