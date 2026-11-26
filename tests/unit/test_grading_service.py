"""
File: test_grading_service.py
Description: Unit tests for GradingService (US6): run checks, the
    not-gradable case, and how a runner reply becomes a Verdict, including
    the course-required white-box test of the verdict and normalization
    logic.
Author(s): Richard Hall, Tyler Black
"""

from unittest import mock

import pytest

from src.business.game_service import RunNotFoundError
from src.business.grading_service import (
    MAX_CODE_BYTES,
    REASON_TEXT,
    CodeTooLargeError,
    GradingService,
    InvalidCodeError,
    RunFinishedError,
    StageNotGradableError,
    clean_traceback,
    to_verdict,
)

CHECK = "def check(game):\n    game.send()\n"


def runner_reply(**overrides: object) -> dict:
    reply = {
        "verdict": "pass",
        "reason": None,
        "rule": None,
        "turn": 3,
        "inputs": ["", "q", ""],
        "last_screen": "..O..",
        "traceback": "",
    }
    reply.update(overrides)
    return reply


def make_service(
    status: str = "in_progress",
    check_script: str | None = CHECK,
    reply: dict | None = None,
) -> tuple[GradingService, mock.Mock]:
    runs = mock.Mock()
    runs.get_for_user.return_value = mock.Mock(status=status, current_stage=1)
    runs.check_script_for.return_value = check_script
    runner = mock.Mock()
    runner.grade.return_value = reply or runner_reply()
    return GradingService(runs, runner), runner


@pytest.mark.whitebox
def test_verdict_and_normalization_logic():
    """White-box test of GradingService's verdict and normalization logic.

    Purpose: cover every branch of ``to_verdict`` and ``clean_traceback``,
    the code that turns the runner's reply into what the player sees.

    Functionality tested: a pass has no reason and no failure kind; a
    rule failure shows the check script's rule (or the fallback when it
    is empty); every failure keeps the runner's reason as its kind;
    every other failure reason maps to its own text, and an unknown one
    to the fallback; sandbox paths on traceback location lines become
    ``main.py`` while other paths, and the player's own strings, stay;
    missing reply fields get safe defaults.

    Expected outcome: each reply produces the documented heading, reason,
    and cleaned traceback.
    """
    passed = to_verdict(runner_reply())
    assert (passed.passed, passed.heading, passed.reason) == (
        True,
        "PASS",
        None,
    )
    assert passed.kind is None
    assert passed.to_dict()["kind"] is None

    rule = to_verdict(
        runner_reply(verdict="fail", reason="rule", rule="One ball only.")
    )
    assert (rule.passed, rule.heading, rule.reason) == (
        False,
        "FAIL",
        "One ball only.",
    )
    assert rule.kind == "rule"
    empty_rule = to_verdict(runner_reply(verdict="fail", reason="rule"))
    assert empty_rule.reason == "Failed."

    for reason, text in REASON_TEXT.items():
        failed = to_verdict(runner_reply(verdict="fail", reason=reason))
        assert (failed.reason, failed.kind) == (text, reason)
        assert failed.to_dict()["kind"] == reason
    unknown = to_verdict(runner_reply(verdict="fail", reason="mystery"))
    assert unknown.reason == "Failed."

    traceback = (
        "Traceback (most recent call last):\n"
        '  File "/sandbox/3/main.py", line 2, in <module>\n'
        '  File "/usr/local/lib/python3.13/socket.py", line 868\n'
        'ValueError: no file "/home/me/main.py"\n'
    )
    assert clean_traceback(traceback) == (
        "Traceback (most recent call last):\n"
        '  File "main.py", line 2, in <module>\n'
        '  File "/usr/local/lib/python3.13/socket.py", line 868\n'
        'ValueError: no file "/home/me/main.py"\n'
    )
    crashed = to_verdict(
        runner_reply(verdict="fail", reason="crashed", traceback=traceback)
    )
    assert '  File "main.py", line 2' in crashed.traceback

    sparse = to_verdict({"verdict": "fail", "reason": "crashed"})
    assert (
        sparse.turn,
        sparse.inputs,
        sparse.last_screen,
        sparse.traceback,
    ) == (
        0,
        (),
        None,
        "",
    )


def test_grade_sends_code_and_check_script():
    service, runner = make_service()
    verdict = service.grade(user_id=1, run_id=7, code="print('hi')")
    runner.grade.assert_called_once_with("print('hi')", CHECK)
    assert verdict.to_dict() == {
        "passed": True,
        "heading": "PASS",
        "kind": None,
        "reason": None,
        "turn": 3,
        "inputs": ["", "q", ""],
        "last_screen": "..O..",
        "traceback": "",
    }


def test_missing_or_foreign_run_is_not_found():
    service, runner = make_service()
    service._runs.get_for_user.return_value = None
    with pytest.raises(RunNotFoundError):
        service.grade(1, 7, "")
    runner.grade.assert_not_called()


def test_finished_run_cannot_be_submitted():
    service, runner = make_service(status="lost")
    with pytest.raises(RunFinishedError):
        service.grade(1, 7, "")
    runner.grade.assert_not_called()


def test_missing_check_script_is_not_gradable() -> None:
    """Report a missing script without calling the runner."""
    service, runner = make_service(check_script=None)
    with pytest.raises(StageNotGradableError):
        service.grade(1, 7, "")
    runner.grade.assert_not_called()


def test_code_over_the_limit_is_rejected():
    service, runner = make_service()
    with pytest.raises(CodeTooLargeError):
        service.grade(1, 7, "x" * (MAX_CODE_BYTES + 1))
    service.grade(1, 7, "x" * MAX_CODE_BYTES)
    runner.grade.assert_called_once()


@pytest.mark.parametrize("code", ["print('\ud800')", "print(1)\0"])
def test_code_that_is_not_valid_text_is_rejected(code: str):
    """A lone surrogate or a NUL never reaches the runner.

    A surrogate can't be encoded, and Postgres can't store a NUL.
    """
    service, runner = make_service()
    with pytest.raises(InvalidCodeError):
        service.grade(1, 7, code)
    runner.grade.assert_not_called()
