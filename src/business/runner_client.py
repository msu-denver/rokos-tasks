"""
File: runner_client.py
Description: The only code that talks to the sandbox runner container.
    Sends a player's program and a stage's check script to the runner's
    POST /grade and returns its verdict, or raises an error that is never
    the player's fault.
Author(s): Richard Hall, Tyler Black
"""

import http.client
import json
import logging
import urllib.error
import urllib.request
from http import HTTPStatus

# The runner's worst case: up to 15 s waiting for two free slots, up to
# 12 s on the check script's clock, then reaping both slots (up to 5 s
# each). A margin on top keeps a slow verdict from showing as a 503.
# A unit test pins this to the runner's own constants; the web
# container's gunicorn timeout (Dockerfile) must stay above it.
WORST_CASE_SECONDS = 15.0 + 12.0 + 2 * 5.0
DEFAULT_TIMEOUT_SECONDS = WORST_CASE_SECONDS + 5.0

logger = logging.getLogger(__name__)


class RunnerUnavailableError(Exception):
    """The runner couldn't grade: unreachable, busy, or failed itself."""


class CheckScriptBrokenError(Exception):
    """The stage's check script failed in the runner: a campaign bug."""


class RunnerClient:
    """Calls the runner's HTTP API."""

    def __init__(
        self, base_url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        """Talk to the runner at ``base_url`` (for example RUNNER_URL)."""
        self._grade_url = base_url.rstrip("/") + "/grade"
        self._timeout = timeout

    def grade(self, code: str, check_script: str) -> dict:
        """Have ``check_script`` play ``code`` and return the verdict.

        Args:
            code: The player's program.
            check_script: The current stage's check script.

        Returns:
            The runner's verdict, as documented in src/runner/AGENTS.md.

        Raises:
            RunnerUnavailableError: If the runner couldn't grade.
            CheckScriptBrokenError: If the check script itself failed.
        """
        body = json.dumps({"code": code, "check_script": check_script})
        request = urllib.request.Request(
            self._grade_url,
            data=body.encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout
            ) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise self._error_for(error) from error
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.HTTPException,
        ) as error:
            # Includes a dropped connection (RemoteDisconnected,
            # ConnectionResetError, IncompleteRead): never the player's.
            raise RunnerUnavailableError(str(error)) from error
        except json.JSONDecodeError as error:
            raise RunnerUnavailableError("the runner sent bad JSON") from error

    @staticmethod
    def _error_for(error: urllib.error.HTTPError) -> Exception:
        """Return the exception matching the runner's error reply."""
        try:
            status = json.loads(error.read()).get("status")
        except (json.JSONDecodeError, AttributeError):
            status = None
        if error.code == HTTPStatus.INTERNAL_SERVER_ERROR and (
            status == "check_error"
        ):
            return CheckScriptBrokenError("the check script failed")
        logger.error("runner replied %s (%s)", error.code, status)
        return RunnerUnavailableError(f"runner replied {error.code}")
