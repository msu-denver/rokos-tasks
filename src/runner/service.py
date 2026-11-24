"""
File: service.py
Description: The runner's one operation: check a run request, borrow a
    sandbox slot, play the program through every input line, and report
    how it went. Used by the HTTP server; has no HTTP code of its own.
Author(s): Tyler Black
"""

import logging
from dataclasses import dataclass
from http import HTTPStatus

from src.runner.limits import SandboxLimits
from src.runner.session import LaunchError, ProgramError, ProgramSession
from src.runner.slots import (
    RunnerBusyError,
    SlotCompromisedError,
    SlotPool,
)

MAX_INPUTS = 2000
MAX_INPUT_CHARS = 64
SLOT_WAIT_SECONDS = 15.0
COMPLETED = "completed"
STATUSES_WITH_EXIT_CODE = ("crashed", "exited")
# Never the player's fault, so callers must never cost a life for it.
RUNNER_ERROR = (HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "runner_error"})

logger = logging.getLogger(__name__)


class RunRequestError(ValueError):
    """Raised when a run request is malformed or over a limit."""


@dataclass(frozen=True)
class RunRequest:
    """A checked request: the program and the input line for each tick."""

    code: str
    inputs: tuple[str, ...]


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
    if not isinstance(payload, dict):
        raise RunRequestError("the body must be a JSON object")
    code = payload.get("code")
    inputs = payload.get("inputs")
    if not isinstance(code, str):
        raise RunRequestError("'code' must be a string")
    if len(code.encode()) > limits.code_bytes:
        raise RunRequestError("'code' is larger than the limit")
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
        try:
            with self._pool.acquire(self._slot_wait_seconds) as slot:
                session = ProgramSession(slot, self._limits)
                return HTTPStatus.OK, self._play(session, request)
        except RunnerBusyError as error:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(error)}
        except (LaunchError, SlotCompromisedError):
            logger.exception("the sandbox failed")
            return RUNNER_ERROR

    def _play(self, session: ProgramSession, request: RunRequest) -> dict:
        """Run every input through ``session`` and describe the result."""
        frames: list[str] = []
        status = COMPLETED
        with session:
            session.start(request.code)
            try:
                for line in request.inputs:
                    frames.append(session.tick(line))
            except ProgramError as failure:
                status = failure.status
        exit_code = session.exit_code
        return {
            "status": status,
            "frames": frames,
            "ticks": len(frames),
            "stderr": session.stderr,
            "exit_code": (
                exit_code if status in STATUSES_WITH_EXIT_CODE else None
            ),
        }
