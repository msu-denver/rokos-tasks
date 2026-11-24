"""
File: test_runner_session.py
Description: Unit tests for ProgramSession in host mode: real player
    subprocesses (benign ones only) driven tick by tick, with the frame
    parser, deadlines, output limit, and launch-failure path.
Author(s): Richard Hall
"""

import os
import subprocess
import time
from pathlib import Path
from textwrap import dedent
from unittest import mock

import pytest

from src.runner.limits import SandboxLimits
from src.runner.session import (
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


def test_frames_come_back_one_per_tick(slot: Slot):
    frames, _ = play(slot, ECHO, ["q", "a"])
    assert frames == ["row one q\nrow two", "row one a\nrow two"]


def test_empty_frame_is_allowed(slot: Slot):
    frames, _ = play(
        slot, "while True:\n    input()\n    print('---')\n", [""]
    )
    assert frames == [""]


def test_frames_printed_together_are_split(slot: Slot):
    code = "input()\nprint('a\\n---\\nb\\n---')\ninput()\n"
    assert play(slot, code, ["", ""])[0] == ["a", "b"]


def test_dash_line_must_be_exact(slot: Slot):
    code = "input()\nprint('a ---')\nprint('----')\nprint('---')\n"
    assert play(slot, code, [""])[0] == ["a ---\n----"]


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


def test_clean_early_exit_is_reported(slot: Slot):
    with pytest.raises(ProgramExitedError):
        play(slot, "input()\n", [""])


def test_program_that_quit_before_reading(slot: Slot):
    with pytest.raises(ProgramExitedError):
        play(slot, "", ["", ""])


def test_tick_timeout(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, tick_seconds=0.3)
    with pytest.raises(TickTimeoutError):
        play(slot, "input()\nwhile True:\n    pass\n", [""], limits)


def test_run_timeout(slot: Slot):
    limits = SandboxLimits(
        memory_bytes=None, tick_seconds=2.0, run_seconds=0.5
    )
    with pytest.raises(RunTimeoutError):
        play(slot, "import time\ninput()\ntime.sleep(5)\n", [""], limits)


def test_stdout_output_limit(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, output_bytes=1000)
    with pytest.raises(OutputLimitError):
        play(slot, "input()\nprint('x' * 5000)\n", [""], limits)


def test_stderr_output_limit_keeps_the_start(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, output_bytes=1000)
    code = "import sys\ninput()\nsys.stderr.write('e' * 5000)\n"
    code += "import time\ntime.sleep(5)\n"
    with ProgramSession(slot, limits) as session:
        session.start(code)
        with pytest.raises(OutputLimitError):
            session.tick("")
    assert session.stderr == "e" * 1000


def test_closed_stdout_on_live_program_is_a_timeout(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, tick_seconds=0.5)
    code = "import os, time\ninput()\nos.close(1)\ntime.sleep(5)\n"
    with pytest.raises(TickTimeoutError):
        play(slot, code, [""], limits)


def test_slot_folder_is_emptied(slot: Slot):
    code = "input()\nopen('left.txt', 'w').write('x')\nprint('---')\n"
    play(slot, code, [""])
    assert list(slot.directory.iterdir()) == []


def test_launch_failure_is_a_launch_error(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, code_bytes=5)
    with ProgramSession(slot, limits) as session:
        with pytest.raises(LaunchError, match="larger than the limit"):
            session.start("print('too long')")


def test_launcher_that_never_reports_is_a_launch_error(slot: Slot):
    session = ProgramSession(slot, HOST_LIMITS)
    session._run_deadline = 0.0
    read_end, write_end = os.pipe()
    try:
        with pytest.raises(LaunchError, match="did not start"):
            session._wait_for_launch(read_end)
    finally:
        os.close(write_end)


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


def reap_with(tmp_path: Path, **run_behavior: object) -> mock.Mock:
    session = ProgramSession(Slot(10001, tmp_path), HOST_LIMITS)
    with mock.patch(
        "src.runner.session.subprocess.run", **run_behavior
    ) as run:
        session._reap(mock.Mock(pid=123))
    return run


def test_reap_in_slot_mode_uses_the_launcher(tmp_path: Path):
    done = subprocess.CompletedProcess([], 0, b"", b"")
    run = reap_with(tmp_path, return_value=done)
    assert run.call_args.args[0][-3:] == ["reap", "10001", str(tmp_path)]


def test_failed_reap_compromises_the_slot(tmp_path: Path):
    failed = subprocess.CompletedProcess([], 1, b"", b"denied")
    with pytest.raises(SlotCompromisedError, match="denied"):
        reap_with(tmp_path, return_value=failed)


def test_hung_reaper_compromises_the_slot(tmp_path: Path):
    with pytest.raises(SlotCompromisedError):
        reap_with(tmp_path, side_effect=subprocess.TimeoutExpired("r", 5))


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


def test_survivor_after_reap_compromises_the_slot(slot: Slot):
    session = ProgramSession(slot, HOST_LIMITS)
    process = mock.Mock(pid=999999999)
    process.wait.side_effect = subprocess.TimeoutExpired("x", 1)
    session._process = process
    with pytest.raises(SlotCompromisedError, match="survived reaping"):
        session.close()
    process.stdout.close.assert_called_once()
