"""
File: grading.py
Description: Grades a player's program with a stage's check script. Runs
    the program and the check script in two sandbox slots and relays
    between them: each tick request from the check script is played on
    the program, and its frame is sent back. Stops at the first broken
    rule, crash, or timeout and returns the verdict.
Author(s): Richard Hall
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from src.runner import harness
from src.runner.limits import MAX_INPUT_CHARS, MAX_TICKS, SandboxLimits
from src.runner.session import ProgramError, ProgramSession
from src.runner.slots import Slot

HARNESS_SOURCE = Path(harness.__file__).read_text(encoding="utf-8")
CHECK_SCRIPT_BYTES = 32 * 1024
# The check script waits on the player's ticks, so its run clock gets a
# margin: when time runs out, the player's clock must stop first.
CHECK_RUN_MARGIN_SECONDS = 2.0
START = "start"
RULE = "rule"


class CheckScriptError(Exception):
    """The check script crashed, hung, or broke the protocol.

    A campaign bug, never the player's fault. ``stderr`` holds the check
    script's output for the log.
    """

    def __init__(self, message: str) -> None:
        """Describe what the check script did wrong."""
        super().__init__(message)
        self.stderr = ""


@dataclass
class Verdict:
    """What happened while the check script played the program."""

    reason: str | None = None
    rule: str | None = None
    inputs: list[str] = field(default_factory=list)
    last_frame: str | None = None
    traceback: str = ""

    def to_dict(self) -> dict:
        """Return the JSON body for the runner's ``/grade`` reply."""
        return {
            "verdict": "pass" if self.reason is None else "fail",
            "reason": self.reason,
            "rule": self.rule,
            "tick": len(self.inputs),
            "inputs": self.inputs,
            "last_frame": self.last_frame,
            "traceback": self.traceback,
        }


def harness_program(check_script: str) -> str:
    """Return the check slot's ``main.py``: the harness plus the script."""
    return f"{HARNESS_SOURCE}\n\nrun({check_script!r})\n"


def parse_check_request(frame: str) -> dict:
    """Decode and check one message the check script sent.

    Returns:
        ``{"tick": line}`` or ``{"done": True, "rule": str | None}``.

    Raises:
        CheckScriptError: If the message isn't one of those.
    """
    try:
        message = json.loads(frame)
    except json.JSONDecodeError as error:
        raise CheckScriptError("the check script sent bad JSON") from error
    if not isinstance(message, dict):
        raise CheckScriptError("the check script sent a non-object")
    line = message.get("tick")
    if isinstance(line, str) and len(line) <= MAX_INPUT_CHARS:
        if "\n" not in line and "\r" not in line:
            return {"tick": line}
    rule = message.get("rule")
    if message.get("done") is True and (rule is None or isinstance(rule, str)):
        return {"done": True, "rule": rule}
    raise CheckScriptError(f"the check script sent {message!r}")


class Grader:
    """Plays a player's program with a check script, both sandboxed."""

    def __init__(self, limits: SandboxLimits) -> None:
        """Apply ``limits`` to the player's program and the check script."""
        self._limits = limits
        self._check_limits = replace(
            limits, run_seconds=limits.run_seconds + CHECK_RUN_MARGIN_SECONDS
        )

    def grade(
        self,
        program_slot: Slot,
        check_slot: Slot,
        code: str,
        check_script: str,
    ) -> dict:
        """Grade ``code`` with ``check_script``.

        Returns:
            The verdict as the ``/grade`` JSON body.

        Raises:
            CheckScriptError: If the check script failed.
            LaunchError: If the sandbox couldn't start either program.
        """
        verdict = Verdict()
        program = ProgramSession(program_slot, self._limits)
        checker = ProgramSession(check_slot, self._check_limits)
        try:
            with program, checker:
                program.start(code)
                checker.start(harness_program(check_script))
                self._play(program, checker, verdict)
        except CheckScriptError as error:
            error.stderr = checker.stderr
            raise
        if verdict.reason not in (None, RULE):
            verdict.traceback = program.stderr
        return verdict.to_dict()

    def _play(
        self,
        program: ProgramSession,
        checker: ProgramSession,
        verdict: Verdict,
    ) -> None:
        """Relay ticks until the check script finishes or the program fails."""
        reply = START
        while True:
            request = self._next_request(checker, reply)
            if "done" in request:
                if request["rule"] is not None:
                    verdict.reason = RULE
                    verdict.rule = request["rule"] or harness.DEFAULT_RULE
                return
            if len(verdict.inputs) >= MAX_TICKS:
                raise CheckScriptError("the check script played too long")
            verdict.inputs.append(request["tick"])
            try:
                frame = program.tick(request["tick"])
            except ProgramError as failure:
                verdict.reason = failure.status
                return
            verdict.last_frame = frame
            reply = json.dumps({"frame": frame})

    def _next_request(self, checker: ProgramSession, reply: str) -> dict:
        """Send the check script ``reply`` and return its next request."""
        try:
            frame = checker.tick(reply)
        except ProgramError as failure:
            raise CheckScriptError(
                f"the check script stopped: {failure.status}"
            ) from failure
        return parse_check_request(frame)
