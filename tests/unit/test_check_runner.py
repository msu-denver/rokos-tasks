"""
File: test_check_runner.py
Description: Unit tests for the trusted local check runner used by
    campaign validation: verdicts come back in the /grade format, frames
    come back one per tick, and sandbox or program failures become
    CheckRunError.
Author(s): Richard Hall, Tyler Black
"""

from unittest import mock

import pytest

from src.business.campaigns.check_runner import (
    CheckRunError,
    TrustedSeedPlayer,
    run_check,
    run_frames,
)
from src.runner.session import LaunchError

ECHO = "import sys\nfor line in sys.stdin:\n    print(line.strip())\n"
ECHO += "    print('---')\n"
CHECK = "def check(game):\n    game.check(game.tick('q') == 'q', 'echo')\n"


def test_run_check_returns_the_verdict():
    verdict = run_check(ECHO, CHECK)
    assert verdict["verdict"] == "pass"
    assert verdict["inputs"] == ["q"]


def test_sandbox_failure_is_a_check_run_error():
    with mock.patch(
        "src.business.campaigns.check_runner.Grader.grade",
        side_effect=LaunchError("no fork"),
    ):
        with pytest.raises(CheckRunError, match="local sandbox failed"):
            run_check(ECHO, CHECK)


def test_check_script_crash_is_a_check_run_error():
    crash = "def check(game):\n    raise RuntimeError('oops')\n"
    with pytest.raises(CheckRunError, match="check script failed"):
        run_check(ECHO, crash)


def test_run_frames_returns_one_frame_per_tick():
    assert run_frames(ECHO, ["a", "", "b"]) == ["a", "", "b"]


def test_failing_program_is_a_check_run_error():
    with pytest.raises(CheckRunError, match="the program failed: crashed"):
        run_frames("input()\n1 / 0\n", [""])


def test_run_frames_sandbox_failure_is_a_check_run_error():
    with mock.patch(
        "src.business.campaigns.check_runner.ProgramSession.start",
        side_effect=LaunchError("no fork"),
    ):
        with pytest.raises(CheckRunError, match="local sandbox failed"):
            run_frames(ECHO, [""])


def test_trusted_seed_player_uses_the_local_runner():
    player = TrustedSeedPlayer()
    assert player.grade(ECHO, CHECK)["verdict"] == "pass"
    assert player.frames(ECHO, ["x"]) == ["x"]
