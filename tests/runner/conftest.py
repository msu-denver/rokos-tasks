"""
File: conftest.py
Description: Fixtures for the hostile-code suite. Each test posts a run
    to the real runner container (started by `make runner`) from inside
    the container, so the runner stays on its internal-only network.
Author(s): Richard Hall, Tyler Black
"""

import json
import subprocess
from collections.abc import Callable

import pytest

# Runs inside the runner container: POST stdin to argv[1], print the reply.
CLIENT = """
import sys, urllib.error, urllib.request
request = urllib.request.Request(
    "http://127.0.0.1:9000" + sys.argv[1],
    data=sys.stdin.buffer.read(),
    headers={"Content-Type": "application/json"},
)
try:
    response = urllib.request.urlopen(request, timeout=60)
except urllib.error.HTTPError as error:
    response = error
sys.stdout.write(response.read().decode())
"""
EXEC_TIMEOUT_SECONDS = 90

RunInSandbox = Callable[..., dict]
GradeInSandbox = Callable[[str, str], dict]


def post_in_container(path: str, payload: dict) -> dict:
    """POST ``payload`` to the runner from inside its container."""
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "runner",
            "python",
            "-I",
            "-c",
            CLIENT,
            path,
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=EXEC_TIMEOUT_SECONDS,
        check=True,
    )
    return json.loads(completed.stdout)


@pytest.fixture(scope="session")
def run_in_sandbox() -> RunInSandbox:
    """Return a function that plays ``code`` in the runner container.

    The returned function takes the program source and the input lines
    (none by default) and returns the runner's JSON reply.
    """

    def run(code: str, inputs: list[str] | None = None) -> dict:
        return post_in_container(
            "/run", {"code": code, "inputs": inputs or []}
        )

    return run


@pytest.fixture(scope="session")
def grade_in_sandbox() -> GradeInSandbox:
    """Return a function that grades ``code`` with a check script."""

    def grade(code: str, check_script: str) -> dict:
        return post_in_container(
            "/grade", {"code": code, "check_script": check_script}
        )

    return grade
