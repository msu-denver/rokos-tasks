"""
File: test_runner_session.py
Description: Unit tests for ProgramSession in host mode: real player
    subprocesses (benign ones only) played one screen at a time. Covers
    how screens split at each request for input, plain scripts that exit,
    clean tracebacks, deadlines, the output limit, and the launch-failure
    path.
Author(s): Richard Hall, Tyler Black
"""

import os
import selectors
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
    TurnTimeoutError,
)
from src.runner.slots import Slot, SlotCompromisedError

# macOS rejects RLIMIT_AS, so host-mode tests leave memory unset.
POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="Linux only; CI runs it (POSIX APIs)"
)
HOST_LIMITS = SandboxLimits(memory_bytes=None, turn_seconds=2.0)

ECHO = dedent(
    """
    print("ready")
    while True:
        line = input()
        print(f"row one {line}")
        print("row two")
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
    with ProgramSession(slot, limits) as session:
        session.start(code)
        screens = [session.first_screen()]
        for line in inputs:
            screens.append(session.send(line))
    return screens, session


@POSIX_ONLY
def test_each_input_gets_the_screen_printed_after_it(slot: Slot):
    screens, session = play(slot, ECHO, ["q", "a"])
    assert screens == ["ready", "row one q\nrow two", "row one a\nrow two"]
    assert not session.finished


@POSIX_ONLY
def test_plain_script_prints_one_screen_and_finishes(slot: Slot):
    code = dedent(
        """
        def main():
            print("board")


        if __name__ == "__main__":
            main()
        """
    )
    screens, session = play(slot, code, [])
    assert screens == ["board"]
    assert session.finished
    assert session.exit_code == 0


@POSIX_ONLY
def test_last_screen_is_what_printed_before_exit(slot: Slot):
    code = "print('start')\nkeys = input()\nprint('end', keys)\n"
    screens, session = play(slot, code, ["q"])
    assert screens == ["start", "end q"]
    assert session.finished


@POSIX_ONLY
def test_input_prompt_is_part_of_the_screen(slot: Slot):
    code = "print('board')\nkeys = input('keys: ')\nprint(keys)\n"
    assert play(slot, code, ["q"])[0] == ["board\nkeys: ", "q"]


@POSIX_ONLY
def test_program_that_asks_first_has_an_empty_first_screen(slot: Slot):
    assert play(slot, "print(input())\n", ["x"])[0] == ["", "x"]


@POSIX_ONLY
@pytest.mark.parametrize(
    "read",
    [
        "import sys\nfor line in sys.stdin:\n    print(line.strip())\n",
        "import sys\nwhile True:\n    print(sys.stdin.readline().strip())\n",
        "import sys\nwhile True:\n    print(sys.stdin.buffer.readline())\n",
    ],
)
def test_every_read_of_stdin_ends_a_screen(slot: Slot, read: str):
    screens = play(slot, read, ["a", "b"])[0]
    assert len(screens) == 3
    assert "a" in screens[1] and "b" in screens[2]


@POSIX_ONLY
def test_the_program_runs_as_main_py(slot: Slot):
    code = "import sys\nprint(sys.argv, __name__, sys.path[0] != '')\n"
    assert play(slot, code, [])[0] == ["['main.py'] __main__ True"]


@POSIX_ONLY
def test_crash_reports_traceback_from_main_py_only(slot: Slot):
    code = "def fail():\n    raise ValueError('boom')\ninput()\nfail()\n"
    with ProgramSession(slot, HOST_LIMITS) as session:
        session.start(code)
        assert session.first_screen() == ""
        with pytest.raises(ProgramCrashedError):
            session.send("")
    assert session.stderr.startswith("Traceback (most recent call last):")
    assert 'File "main.py", line 4, in <module>' in session.stderr
    assert 'File "main.py", line 2, in fail' in session.stderr
    assert "ValueError: boom" in session.stderr
    for hidden in ("launcher", "runpy", "<string>"):
        assert hidden not in session.stderr
    assert session.exit_code == 1


@POSIX_ONLY
def test_failed_stdin_read_hides_the_bootstrap(slot: Slot):
    code = "import sys\nsys.stdin.close()\nsys.stdin.readline()\n"
    with pytest.raises(ProgramCrashedError):
        play(slot, code, [""])
    with ProgramSession(slot, HOST_LIMITS) as session:
        session.start(code)
        with pytest.raises(ProgramCrashedError):
            session.first_screen()
            session.send("")
    assert 'File "main.py", line 3, in <module>' in session.stderr
    assert "ValueError" in session.stderr
    assert "<string>" not in session.stderr


@POSIX_ONLY
def test_chained_exceptions_hide_the_bootstrap(slot: Slot):
    code = dedent(
        """
        try:
            1 / 0
        except ZeroDivisionError as error:
            raise ValueError("bad") from error
        """
    )
    with ProgramSession(slot, HOST_LIMITS) as session:
        session.start(code)
        with pytest.raises(ProgramCrashedError):
            session.first_screen()
    assert "ZeroDivisionError" in session.stderr
    assert "direct cause" in session.stderr
    assert session.stderr.count('File "main.py"') == 2
    for hidden in ("<string>", "runpy"):
        assert hidden not in session.stderr


@POSIX_ONLY
def test_exit_after_a_waiting_signal_is_still_checked(slot: Slot):
    """A crash right after a stray waiting signal is a crash, not a screen."""
    with ProgramSession(slot, HOST_LIMITS) as session:
        session.start("print('board')\nraise SystemExit(3)\n")
        session._process.wait(timeout=5)
        session._asked_for_input = True
        with pytest.raises(ProgramCrashedError):
            session.first_screen()
    assert session.exit_code == 3


@POSIX_ONLY
def test_closed_stdout_past_the_run_deadline_is_a_run_timeout(slot: Slot):
    limits = SandboxLimits(
        memory_bytes=None, turn_seconds=2.0, run_seconds=0.5
    )
    code = "import os, time\nos.close(1)\ntime.sleep(5)\n"
    with pytest.raises(RunTimeoutError):
        play(slot, code, [], limits)


@POSIX_ONLY
def test_syntax_error_reads_like_python_main_py(slot: Slot):
    with ProgramSession(slot, HOST_LIMITS) as session:
        session.start("print('a'\n")
        with pytest.raises(ProgramCrashedError):
            session.first_screen()
    assert session.stderr.startswith('  File "main.py", line 1')
    assert "SyntaxError" in session.stderr


@POSIX_ONLY
def test_sys_exit_with_a_message_is_a_crash(slot: Slot):
    with ProgramSession(slot, HOST_LIMITS) as session:
        session.start("import sys\nsys.exit('bye')\n")
        with pytest.raises(ProgramCrashedError):
            session.first_screen()
    assert session.stderr == "bye\n"


@POSIX_ONLY
def test_exit_is_seen_while_a_child_holds_stdout(slot: Slot):
    """A background child keeping the pipes open can't hide the exit."""
    code = dedent(
        """
        import subprocess, sys
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(9)"])
        print("done")
        """
    )
    import resource  # POSIX only, like the test.

    # Host mode runs as the developer, who already owns many processes.
    processes = resource.getrlimit(resource.RLIMIT_NPROC)[0]
    limits = SandboxLimits(memory_bytes=None, process_count=processes)
    started = time.monotonic()
    screens, session = play(slot, code, [], limits)
    assert screens == ["done"]
    assert session.finished
    assert time.monotonic() - started < 2.0


@POSIX_ONLY
def test_input_to_a_program_that_just_exited_finishes_it(slot: Slot):
    """The exit wasn't seen yet, so the write hits a closed pipe."""
    with ProgramSession(slot, HOST_LIMITS) as session:
        session.start("print('bye')\n")
        session._process.wait(timeout=5)
        session._asked_for_input = True
        with mock.patch.object(session._process, "poll", return_value=None):
            assert session.first_screen() == "bye"
        assert session.send("") == ""
        assert session.finished


@POSIX_ONLY
def test_input_after_exit_is_reported(slot: Slot):
    with pytest.raises(ProgramExitedError):
        play(slot, "print('only')\n", [""])


@POSIX_ONLY
def test_turn_timeout(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, turn_seconds=0.3)
    with pytest.raises(TurnTimeoutError):
        play(slot, "input()\nwhile True:\n    pass\n", [""], limits)


@POSIX_ONLY
def test_first_screen_has_a_turn_deadline_too(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, turn_seconds=0.3)
    with pytest.raises(TurnTimeoutError):
        play(slot, "while True:\n    pass\n", [], limits)


@POSIX_ONLY
def test_screen_ready_at_the_deadline_is_still_read(slot: Slot):
    with ProgramSession(slot, HOST_LIMITS) as session:
        session.start("print('ready')\ninput()\n")
        time.sleep(0.3)
        session._turn_deadline = time.monotonic()
        assert session.first_screen() == "ready"


@POSIX_ONLY
def test_run_timeout(slot: Slot):
    limits = SandboxLimits(
        memory_bytes=None, turn_seconds=2.0, run_seconds=0.5
    )
    with pytest.raises(RunTimeoutError):
        play(slot, "import time\ninput()\ntime.sleep(5)\n", [""], limits)


@POSIX_ONLY
def test_stdout_output_limit(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, output_bytes=1000)
    with pytest.raises(OutputLimitError):
        play(slot, "input()\nprint('x' * 5000)\n", [""], limits)


@POSIX_ONLY
def test_output_limit_is_per_screen(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, output_bytes=1000)
    code = "while True:\n    print('x' * 600)\n    input()\n"
    assert len(play(slot, code, ["", ""], limits)[0]) == 3


@POSIX_ONLY
def test_stderr_output_limit_keeps_the_start(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, output_bytes=1000)
    code = "import sys\ninput()\nsys.stderr.write('e' * 5000)\n"
    code += "import time\ntime.sleep(5)\n"
    with ProgramSession(slot, limits) as session:
        session.start(code)
        session.first_screen()
        with pytest.raises(OutputLimitError):
            session.send("")
    assert session.stderr == "e" * 1000


@POSIX_ONLY
def test_closed_stdout_on_live_program_is_a_timeout(slot: Slot):
    limits = SandboxLimits(memory_bytes=None, turn_seconds=0.5)
    code = "import os, time\ninput()\nos.close(1)\ntime.sleep(5)\n"
    with pytest.raises(TurnTimeoutError):
        play(slot, code, [""], limits)


@POSIX_ONLY
def test_program_that_closes_the_waiting_pipe_times_out(slot: Slot):
    """Sabotaging the input signal only hurts the program itself."""
    limits = SandboxLimits(memory_bytes=None, turn_seconds=0.5)
    code = "import os\nos.closerange(3, 100)\nprint('a')\ninput()\n"
    with pytest.raises(TurnTimeoutError):
        play(slot, code, [], limits)


@POSIX_ONLY
def test_slot_folder_is_emptied(slot: Slot):
    code = "input()\nopen('left.txt', 'w').write('x')\n"
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
    """Lines sent to a program that never reads fill stdin; the turn ends.

    The container suite plays the hostile version, which forges the
    waiting signal itself.
    """
    limits = SandboxLimits(memory_bytes=None, turn_seconds=0.5)
    with ProgramSession(slot, limits) as session:
        session.start("import time\ntime.sleep(30)\n")
        started = time.monotonic()
        with pytest.raises(TurnTimeoutError):
            for _ in range(10_000):
                session._asked_for_input = True
                session.send("x" * 64)
    assert time.monotonic() - started < 2


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


def test_spurious_wakeup_reads_nothing(slot: Slot):
    session = ProgramSession(slot, HOST_LIMITS)
    session._process = mock.Mock()
    read_end, write_end = os.pipe()
    os.set_blocking(read_end, False)
    try:
        key = session._selector.register(read_end, selectors.EVENT_READ)
        with mock.patch.object(
            session._selector, "select", return_value=[(key, 1)]
        ):
            assert session._pump(0) is False
        assert not session._asked_for_input
    finally:
        session._selector.unregister(read_end)
        os.close(read_end)
        os.close(write_end)


def test_pump_with_nothing_to_watch_just_waits(slot: Slot):
    session = ProgramSession(slot, HOST_LIMITS)
    started = time.monotonic()
    assert session._pump(0.05) is False
    assert time.monotonic() - started >= 0.04


@pytest.mark.parametrize("failing_pipe", [0, 1])
def test_pipe_failure_is_a_launch_error_without_leaks(
    slot: Slot, failing_pipe: int
):
    made: list[int] = []
    real_pipe = os.pipe

    def pipe() -> tuple[int, int]:
        if len(made) // 2 == failing_pipe:
            raise OSError(24, "Too many open files")
        ends = real_pipe()
        made.extend(ends)
        return ends

    session = ProgramSession(slot, HOST_LIMITS)
    with mock.patch("src.runner.session.os.pipe", side_effect=pipe):
        with pytest.raises(LaunchError, match="could not make a pipe"):
            session.start("print('hi')")
    session.close()
    for fd in made:
        with pytest.raises(OSError):
            os.fstat(fd)
