"""
File: test_check_runner.py
Description: Unit tests for the trusted local check runner used by
    campaign validation: verdicts come back in the /grade format, and
    sandbox failures become CheckRunError.
Author(s): Richard Hall
"""

from unittest import mock

import pytest

from src.business.campaigns.check_runner import CheckRunError, run_check
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
