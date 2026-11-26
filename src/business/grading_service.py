"""
File: grading_service.py
Description: Grades a Submit (US6): checks the player's run, sends the
    code and the current stage's check script to the runner, and turns
    the runner's reply into a Verdict for the page. Lives, checkpoints,
    and score are not changed here (US7).
Author(s): Richard Hall, Tyler Black
"""

import re
from dataclasses import dataclass

from src.business.runner_client import RunnerClient
from src.data.repositories.run_repository import RunRepository

MAX_CODE_BYTES = 64 * 1024
PASS = "PASS"
FAIL = "FAIL"
# Placeholder wording until the PO decides; US10 moves it to dialogue.
REASON_TEXT = {
    "crashed": "Crashed.",
    "turn_timeout": (
        "Timed out: more than 1 second before asking for input or exiting."
    ),
    "run_timeout": "Timed out: more than 10 seconds in total.",
    "output_limit": "Printed more than 64 KB in one screen.",
    "exited": "Exited before reading all of its input.",
}
UNKNOWN_REASON = "Failed."
# The runner's slot folder means nothing to the player; their file is
# main.py. Only traceback location lines are rewritten, never the
# player's own messages.
_SANDBOX_PATH = re.compile(r'^(\s*File )"[^"\n]*/main\.py"', re.MULTILINE)


class RunNotFoundError(LookupError):
    """The requested run is absent or belongs to another player."""


class RunFinishedError(Exception):
    """The run is no longer in progress, so it can't be submitted."""


class InvalidCodeError(ValueError):
    """The submitted program can't be sent to the runner."""


class CodeTooLargeError(InvalidCodeError):
    """The submitted program is larger than the runner accepts."""


class StageNotGradableError(Exception):
    """The current stage has no check script."""


@dataclass(frozen=True)
class Verdict:
    """What the page shows after a Submit.

    ``kind`` is how the program failed, for US7 and US10: ``rule``,
    ``crashed``, ``exited``, ``turn_timeout``, ``run_timeout``, or
    ``output_limit``; None on a pass.
    """

    passed: bool
    heading: str
    kind: str | None
    reason: str | None
    turn: int
    inputs: tuple[str, ...]
    last_screen: str | None
    traceback: str

    def to_dict(self) -> dict:
        """Return the verdict as the Submit route's JSON body."""
        return {
            "passed": self.passed,
            "heading": self.heading,
            "kind": self.kind,
            "reason": self.reason,
            "turn": self.turn,
            "inputs": list(self.inputs),
            "last_screen": self.last_screen,
            "traceback": self.traceback,
        }


def clean_traceback(traceback: str) -> str:
    """Show the player's file as ``main.py`` instead of its sandbox path."""
    return _SANDBOX_PATH.sub(r'\1"main.py"', traceback)


def to_verdict(reply: dict) -> Verdict:
    """Turn the runner's ``/grade`` reply into a ``Verdict``.

    Args:
        reply: The runner's JSON reply.

    Returns:
        The verdict: the broken rule's own text for a rule failure,
        otherwise the placeholder text for how the program failed.
    """
    passed = reply.get("verdict") == "pass"
    reason = reply.get("reason")
    if passed:
        reason_text = None
    elif reason == "rule":
        reason_text = reply.get("rule") or UNKNOWN_REASON
    else:
        reason_text = REASON_TEXT.get(reason, UNKNOWN_REASON)
    return Verdict(
        passed=passed,
        heading=PASS if passed else FAIL,
        kind=None if passed else reason,
        reason=reason_text,
        turn=reply.get("turn", 0),
        inputs=tuple(reply.get("inputs", ())),
        last_screen=reply.get("last_screen"),
        traceback=clean_traceback(reply.get("traceback") or ""),
    )


class GradingService:
    """Grades a player's program for the current stage of their run."""

    def __init__(self, runs: RunRepository, runner: RunnerClient) -> None:
        """Use ``runs`` to find the stage and ``runner`` to grade it."""
        self._runs = runs
        self._runner = runner

    def grade(self, user_id: int, run_id: int, code: str) -> Verdict:
        """Grade ``code`` against the run's current stage.

        Args:
            user_id: The player submitting.
            run_id: One of the player's runs.
            code: The program in the editor.

        Returns:
            The verdict.

        Raises:
            RunNotFoundError: If the run is missing or someone else's.
            RunFinishedError: If the run is over.
            InvalidCodeError: If the code is over the size limit or
                isn't valid text (a lone surrogate or a NUL character).
            RunnerUnavailableError: If the runner couldn't grade.
            CheckScriptBrokenError: If the check script failed.
            StageNotGradableError: If the current stage has no check script.
        """
        run = self._runs.get_for_user(run_id, user_id)
        if run is None:
            raise RunNotFoundError(run_id)
        if run.status != "in_progress":
            raise RunFinishedError(run_id)
        try:
            size = len(code.encode())
        except UnicodeEncodeError as error:
            raise InvalidCodeError("the program isn't valid text") from error
        if "\0" in code:
            # Python rejects it, and Postgres can't store it in a Submission.
            raise InvalidCodeError("the program contains a NUL character")
        if size > MAX_CODE_BYTES:
            raise CodeTooLargeError("the program is larger than 64 KB")
        check_script = self._runs.check_script_for(run)
        if check_script is None:
            raise StageNotGradableError(
                "the current stage has no check script"
            )
        return to_verdict(self._runner.grade(code, check_script))
