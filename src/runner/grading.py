"""
File: grading.py
Description: Grades a player's program with a stage's check script. Runs
    the program and the check script in two sandbox slots and relays
    between them: the check script gets the program's first screen, and
    each line it sends is typed into the program, whose next screen goes
    back. Stops at the first broken rule, crash, or timeout and returns
    the verdict.
Author(s): Richard Hall, Tyler Black
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from src.runner import harness
from src.runner.limits import MAX_INPUT_CHARS, MAX_TURNS, SandboxLimits
from src.runner.session import ProgramError, ProgramSession
from src.runner.slots import Slot

HARNESS_SOURCE = Path(harness.__file__).read_text(encoding="utf-8")
CHECK_SCRIPT_BYTES = 32 * 1024
# The check script waits on the player's turns, so its run clock gets a
# margin: when time runs out, the player's clock must stop first.
CHECK_RUN_MARGIN_SECONDS = 2.0
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
    last_screen: str | None = None
    traceback: str = ""

    def to_dict(self) -> dict:
        """Return the JSON body for the runner's ``/grade`` reply."""
        return {
            "verdict": "pass" if self.reason is None else "fail",
            "reason": self.reason,
            "rule": self.rule,
            "turn": len(self.inputs),
            "inputs": self.inputs,
            "last_screen": self.last_screen,
            "traceback": self.traceback,
        }


def harness_program(check_script: str) -> str:
    """Return the check slot's ``main.py``: the harness plus the script."""
    return f"{HARNESS_SOURCE}\n\nrun({check_script!r})\n"


def parse_check_request(screen: str) -> dict:
    """Decode and check one message the check script sent.

    Returns:
        ``{"send": line}`` or ``{"done": True, "rule": str | None}``.

    Raises:
        CheckScriptError: If the message isn't one of those.
    """
    try:
        message = json.loads(screen)
    except json.JSONDecodeError as error:
        raise CheckScriptError("the check script sent bad JSON") from error
    if not isinstance(message, dict):
        raise CheckScriptError("the check script sent a non-object")
    line = message.get("send")
    if isinstance(line, str) and len(line) <= MAX_INPUT_CHARS:
        if "\n" not in line and "\r" not in line:
            return {"send": line}
    rule = message.get("rule")
    if message.get("done") is True and (rule is None or isinstance(rule, str)):
        return {"done": True, "rule": rule}
    raise CheckScriptError(f"the check script sent {message!r}")


def screen_reply(screen: str, finished: bool) -> str:
    """Return the message that hands the check script one screen."""
    return json.dumps({"screen": screen, "finished": finished})


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
        """Relay turns until the check script finishes or the program fails."""
        try:
            screen = program.first_screen()
        except ProgramError as failure:
            verdict.reason = failure.status
            return
        verdict.last_screen = screen
        # The harness asks for the first screen before printing anything.
        self._check_script_says(checker, None)
        reply = screen_reply(screen, program.finished)
        while True:
            request = parse_check_request(
                self._check_script_says(checker, reply)
            )
            if "done" in request:
                if request["rule"] is not None:
                    verdict.reason = RULE
                    verdict.rule = request["rule"] or harness.DEFAULT_RULE
                return
            if len(verdict.inputs) >= MAX_TURNS:
                raise CheckScriptError("the check script played too long")
            verdict.inputs.append(request["send"])
            try:
                screen = program.send(request["send"])
            except ProgramError as failure:
                verdict.reason = failure.status
                return
            verdict.last_screen = screen
            reply = screen_reply(screen, program.finished)

    @staticmethod
    def _check_script_says(checker: ProgramSession, reply: str | None) -> str:
        """Send the check script ``reply`` and return what it prints next.

        ``None`` reads the check script's first screen instead.
        """
        try:
            if reply is None:
                return checker.first_screen()
            return checker.send(reply)
        except ProgramError as failure:
            raise CheckScriptError(
                f"the check script stopped: {failure.status}"
            ) from failure
