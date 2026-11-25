"""
File: service.py
Description: The runner's two operations. `run` plays a program through
    a fixed list of input lines, typing each one when the program asks
    for input; `grade` has a stage's check script play it. Both check
    the request, borrow sandbox slots, and map failures to replies.
    Used by the HTTP server; has no HTTP code of its own.
Author(s): Richard Hall, Tyler Black
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus

from src.runner.grading import CHECK_SCRIPT_BYTES, CheckScriptError, Grader
from src.runner.limits import MAX_INPUT_CHARS, MAX_TURNS, SandboxLimits
from src.runner.session import LaunchError, ProgramError, ProgramSession
from src.runner.slots import (
    RunnerBusyError,
    Slot,
    SlotCompromisedError,
    SlotPool,
)

MAX_INPUTS = MAX_TURNS
SLOT_WAIT_SECONDS = 15.0
COMPLETED = "completed"
STATUSES_WITH_EXIT_CODE = ("crashed", "exited")
# Never the player's fault, so callers must never cost a life for it.
RUNNER_ERROR = (HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "runner_error"})
# The check script is broken: a campaign bug, also never the player's fault.
CHECK_ERROR = (HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "check_error"})

logger = logging.getLogger(__name__)


class RunRequestError(ValueError):
    """Raised when a run request is malformed or over a limit."""


@dataclass(frozen=True)
class RunRequest:
    """A checked request: the program and the input lines to type."""

    code: str
    inputs: tuple[str, ...]


@dataclass(frozen=True)
class GradeRequest:
    """A checked request: the program and the check script to play it."""

    code: str
    check_script: str


def _checked_code(payload: object, limits: SandboxLimits) -> str:
    """Return the request's ``code`` after checking the shared fields."""
    if not isinstance(payload, dict):
        raise RunRequestError("the body must be a JSON object")
    code = payload.get("code")
    if not isinstance(code, str):
        raise RunRequestError("'code' must be a string")
    if len(code.encode()) > limits.code_bytes:
        raise RunRequestError("'code' is larger than the limit")
    return code


def parse_grade_request(
    payload: object, limits: SandboxLimits
) -> GradeRequest:
    """Check a decoded JSON body and turn it into a ``GradeRequest``.

    Raises:
        RunRequestError: If a field is missing, the wrong type, or too big.
    """
    code = _checked_code(payload, limits)
    script = payload.get("check_script")
    if not isinstance(script, str) or not script.strip():
        raise RunRequestError("'check_script' must be a non-empty string")
    if len(script.encode()) > CHECK_SCRIPT_BYTES:
        raise RunRequestError("'check_script' is larger than the limit")
    return GradeRequest(code, script)


def parse_run_request(payload: object, limits: SandboxLimits) -> RunRequest:
    """Check a decoded JSON body and turn it into a ``RunRequest``.

    Args:
        payload: The decoded request body.
        limits: Limits that cap the code size.

    Returns:
        The checked request.

    Raises:
        RunRequestError: If a field is missing, the wrong type, or too big.
    """
    code = _checked_code(payload, limits)
    inputs = payload.get("inputs")
    if not isinstance(inputs, list) or len(inputs) > MAX_INPUTS:
        raise RunRequestError(f"'inputs' must be a list of {MAX_INPUTS} max")
    for line in inputs:
        if (
            not isinstance(line, str)
            or len(line) > MAX_INPUT_CHARS
            or "\n" in line
            or "\r" in line
        ):
            raise RunRequestError(
                f"each input must be one line of {MAX_INPUT_CHARS} max"
            )
    return RunRequest(code, tuple(inputs))


class RunnerService:
    """Plays player programs in the sandbox."""

    def __init__(
        self,
        pool: SlotPool,
        limits: SandboxLimits,
        slot_wait_seconds: float = SLOT_WAIT_SECONDS,
    ) -> None:
        """Use slots from ``pool`` and apply ``limits`` to every run."""
        self._pool = pool
        self._limits = limits
        self._slot_wait_seconds = slot_wait_seconds
        self._grader = Grader(limits)

    def health(self) -> tuple[HTTPStatus, dict]:
        """Report whether every sandbox slot is still usable."""
        retired = self._pool.retired
        if retired:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "ok": False,
                "retired": retired,
            }
        return HTTPStatus.OK, {"ok": True}

    def run(self, payload: object) -> tuple[HTTPStatus, dict]:
        """Handle one run request.

        Args:
            payload: The decoded JSON body.

        Returns:
            The HTTP status and the JSON body to send back.
        """
        try:
            request = parse_run_request(payload, self._limits)
        except RunRequestError as error:
            return HTTPStatus.BAD_REQUEST, {"error": str(error)}
        return self._in_slots(
            1,
            lambda slots: self._play(
                ProgramSession(slots[0], self._limits), request
            ),
        )

    def grade(self, payload: object) -> tuple[HTTPStatus, dict]:
        """Handle one grade request.

        Args:
            payload: The decoded JSON body.

        Returns:
            The HTTP status and the JSON body (the verdict) to send back.
        """
        try:
            request = parse_grade_request(payload, self._limits)
        except RunRequestError as error:
            return HTTPStatus.BAD_REQUEST, {"error": str(error)}
        return self._in_slots(
            2,
            lambda slots: self._grader.grade(
                slots[0], slots[1], request.code, request.check_script
            ),
        )

    def _in_slots(
        self, count: int, play: Callable[[list[Slot]], dict]
    ) -> tuple[HTTPStatus, dict]:
        """Borrow ``count`` slots, call ``play``, and map its failures."""
        try:
            with self._pool.acquire(self._slot_wait_seconds, count) as slots:
                return HTTPStatus.OK, play(slots)
        except RunnerBusyError as error:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(error)}
        except CheckScriptError as error:
            logger.error("check script failed: %s\n%s", error, error.stderr)
            return CHECK_ERROR
        except (LaunchError, SlotCompromisedError):
            logger.exception("the sandbox failed")
            return RUNNER_ERROR

    def _play(self, session: ProgramSession, request: RunRequest) -> dict:
        """Type every input into ``session`` and describe the result.

        The first screen comes before any input; each input line adds the
        screen that followed it. Sending a line to a program that already
        exited ends the run with ``exited``.
        """
        screens: list[str] = []
        status = COMPLETED
        with session:
            session.start(request.code)
            try:
                screens.append(session.first_screen())
                for line in request.inputs:
                    screens.append(session.send(line))
            except ProgramError as failure:
                status = failure.status
        exit_code = session.exit_code
        return {
            "status": status,
            "screens": screens,
            "finished": session.finished,
            "stderr": session.stderr,
            "exit_code": (
                exit_code if status in STATUSES_WITH_EXIT_CODE else None
            ),
        }
