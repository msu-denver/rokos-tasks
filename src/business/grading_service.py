"""
File: grading_service.py
Description: Grades a Submit (US6): checks the player's run, sends the
    code and the current stage's check script to the runner, and turns
    the runner's reply into a Verdict for the page. Lives, checkpoints,
    and score are not changed here (US7).
Author(s): Richard Hall
"""

import re
from dataclasses import dataclass

from src.business.game_service import RunNotFoundError
from src.business.runner_client import RunnerClient
from src.data.repositories.run_repository import RunRepository

MAX_CODE_BYTES = 64 * 1024
PASS = "PASS"
FAIL = "FAIL"
# Placeholder wording until the PO decides; US10 moves it to dialogue.
REASON_TEXT = {
    "crashed": "Crashed.",
    "tick_timeout": "Timed out: more than 1 second for one tick.",
    "run_timeout": "Timed out: more than 10 seconds in total.",
    "output_limit": "Printed more than 64 KB in one frame.",
    "exited": "Exited before the check finished.",
}
UNKNOWN_REASON = "Failed."
# The runner's slot folder means nothing to the player; their file is main.py.
_SANDBOX_PATH = re.compile(r'"[^"\n]*/main\.py"')


class RunFinishedError(Exception):
    """The run is no longer in progress, so it can't be submitted."""


class StageNotGradableError(Exception):
    """The stage has no check script yet (old seeds, until #15)."""


class CodeTooLargeError(ValueError):
    """The submitted program is larger than the runner accepts."""


@dataclass(frozen=True)
class Verdict:
    """What the page shows after a Submit."""

    passed: bool
    heading: str
    reason: str | None
    tick: int
    inputs: tuple[str, ...]
    last_frame: str | None
    traceback: str

    def to_dict(self) -> dict:
        """Return the verdict as the Submit route's JSON body."""
        return {
            "passed": self.passed,
            "heading": self.heading,
            "reason": self.reason,
            "tick": self.tick,
            "inputs": list(self.inputs),
            "last_frame": self.last_frame,
            "traceback": self.traceback,
        }


def clean_traceback(traceback: str) -> str:
    """Show the player's file as ``main.py`` instead of its sandbox path."""
    return _SANDBOX_PATH.sub('"main.py"', traceback)


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
        reason=reason_text,
        tick=reply.get("tick", 0),
        inputs=tuple(reply.get("inputs", ())),
        last_frame=reply.get("last_frame"),
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
            CodeTooLargeError: If the code is over the size limit.
            StageNotGradableError: If the stage has no check script.
            RunnerUnavailableError: If the runner couldn't grade.
            CheckScriptBrokenError: If the check script failed.
        """
        run = self._runs.get_for_user(run_id, user_id)
        if run is None:
            raise RunNotFoundError(run_id)
        if run.status != "in_progress":
            raise RunFinishedError(run_id)
        if len(code.encode()) > MAX_CODE_BYTES:
            raise CodeTooLargeError("the program is larger than 64 KB")
        check_script = self._runs.check_script_for(run)
        if not check_script:
            raise StageNotGradableError(run.current_stage)
        return to_verdict(self._runner.grade(code, check_script))
