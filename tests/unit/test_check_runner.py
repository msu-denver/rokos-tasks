"""
File: test_check_runner.py
Description: Unit tests for the trusted local check runner used by
    campaign validation: verdicts come back in the /grade format, screens
    come back one per input line after the first, and sandbox or program
    failures become CheckRunError.
Author(s): Richard Hall, Tyler Black
"""

from unittest import mock

import pytest

from src.business.campaigns.check_runner import (
    CheckRunError,
    TrustedSeedPlayer,
    host_play_supported,
    run_check,
    run_screens,
)
from src.runner.session import LaunchError
from tests.conftest import requires_host_play

ECHO = "print('ready')\nwhile True:\n    print(input())\n"
CHECK = "def check(game):\n    game.check(game.send('q') == 'q', 'echo')\n"


@requires_host_play
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


@requires_host_play
def test_check_script_crash_is_a_check_run_error():
    crash = "def check(game):\n    raise RuntimeError('oops')\n"
    with pytest.raises(CheckRunError, match="check script failed"):
        run_check(ECHO, crash)


@requires_host_play
def test_run_screens_returns_the_first_screen_then_one_per_input():
    assert run_screens(ECHO, ["a", "", "b"]) == ["ready", "a", "", "b"]


@requires_host_play
def test_failing_program_is_a_check_run_error():
    with pytest.raises(CheckRunError, match="the program failed: crashed"):
        run_screens("input()\n1 / 0\n", [""])


def test_run_screens_sandbox_failure_is_a_check_run_error():
    with mock.patch(
        "src.business.campaigns.check_runner.ProgramSession.start",
        side_effect=LaunchError("no fork"),
    ):
        with pytest.raises(CheckRunError, match="local sandbox failed"):
            run_screens(ECHO, [""])


@requires_host_play
def test_trusted_seed_player_uses_the_local_runner():
    player = TrustedSeedPlayer()
    assert player.grade(ECHO, CHECK)["verdict"] == "pass"
    assert player.screens(ECHO, ["x"]) == ["ready", "x"]


@pytest.mark.parametrize(
    ("platform", "supported"),
    [("win32", False), ("linux", True), ("darwin", True)],
)
def test_host_play_is_unsupported_only_on_windows(
    platform: str, supported: bool
):
    with mock.patch("src.business.campaigns.check_runner.sys") as fake_sys:
        fake_sys.platform = platform
        assert host_play_supported() is supported
