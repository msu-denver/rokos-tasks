"""
File: conftest.py
Description: Fixtures for the hostile-code suite. Each test posts a run
    to the real runner container (started by `make runner`) from inside
    the container, so the runner stays on its internal-only network.
Author(s): Richard Hall
"""

import json
import subprocess
from collections.abc import Callable

import pytest

# Runs inside the runner container: POST stdin to /run, print the reply.
CLIENT = """
import sys, urllib.error, urllib.request
request = urllib.request.Request(
    "http://127.0.0.1:9000/run",
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


@pytest.fixture(scope="session")
def run_in_sandbox() -> RunInSandbox:
    """Return a function that plays ``code`` in the runner container.

    The returned function takes the program source and the input lines
    (one empty line by default) and returns the runner's JSON reply.
    """

    def run(code: str, inputs: list[str] | None = None) -> dict:
        payload = {"code": code, "inputs": inputs or [""]}
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
            ],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT_SECONDS,
            check=True,
        )
        return json.loads(completed.stdout)

    return run
