"""
File: test_grading_service.py
Description: Unit tests for GradingService (US6): run checks, the
    not-gradable case, and how a runner reply becomes a Verdict, including
    the course-required white-box test of the verdict and normalization
    logic.
Author(s): Richard Hall
"""

from unittest import mock

import pytest

from src.business.game_service import RunNotFoundError
from src.business.grading_service import (
    MAX_CODE_BYTES,
    REASON_TEXT,
    CodeTooLargeError,
    GradingService,
    RunFinishedError,
    StageNotGradableError,
    clean_traceback,
    to_verdict,
)

CHECK = "def check(game):\n    game.tick()\n"


def runner_reply(**overrides: object) -> dict:
    reply = {
        "verdict": "pass",
        "reason": None,
        "rule": None,
        "tick": 3,
        "inputs": ["", "q", ""],
        "last_frame": "..O..",
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

    Functionality tested: a pass has no reason; a rule failure shows the
    check script's rule (or the fallback when it is empty); every other
    failure reason maps to its own text, and an unknown one to the
    fallback; sandbox paths in tracebacks become ``main.py`` while other
    paths stay; missing reply fields get safe defaults.

    Expected outcome: each reply produces the documented heading, reason,
    and cleaned traceback.
    """
    passed = to_verdict(runner_reply())
    assert (passed.passed, passed.heading, passed.reason) == (
        True,
        "PASS",
        None,
    )

    rule = to_verdict(
        runner_reply(verdict="fail", reason="rule", rule="One ball only.")
    )
    assert (rule.passed, rule.heading, rule.reason) == (
        False,
        "FAIL",
        "One ball only.",
    )
    empty_rule = to_verdict(runner_reply(verdict="fail", reason="rule"))
    assert empty_rule.reason == "Failed."

    for reason, text in REASON_TEXT.items():
        assert (
            to_verdict(runner_reply(verdict="fail", reason=reason)).reason
            == text
        )
    unknown = to_verdict(runner_reply(verdict="fail", reason="mystery"))
    assert unknown.reason == "Failed."

    traceback = (
        'File "/sandbox/3/main.py", line 2, in <module>\n'
        'File "/usr/local/lib/python3.13/socket.py", line 868\n'
    )
    assert clean_traceback(traceback) == (
        'File "main.py", line 2, in <module>\n'
        'File "/usr/local/lib/python3.13/socket.py", line 868\n'
    )
    crashed = to_verdict(
        runner_reply(verdict="fail", reason="crashed", traceback=traceback)
    )
    assert crashed.traceback.startswith('File "main.py"')

    sparse = to_verdict({"verdict": "fail", "reason": "crashed"})
    assert (
        sparse.tick,
        sparse.inputs,
        sparse.last_frame,
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
        "reason": None,
        "tick": 3,
        "inputs": ["", "q", ""],
        "last_frame": "..O..",
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


def test_code_over_the_limit_is_rejected():
    service, runner = make_service()
    with pytest.raises(CodeTooLargeError):
        service.grade(1, 7, "x" * (MAX_CODE_BYTES + 1))
    service.grade(1, 7, "x" * MAX_CODE_BYTES)
    runner.grade.assert_called_once()


def test_stage_without_check_script_is_not_gradable():
    service, runner = make_service(check_script=None)
    with pytest.raises(StageNotGradableError):
        service.grade(1, 7, "print('hi')")
    runner.grade.assert_not_called()
