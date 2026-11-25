"""
File: test_runner_client.py
Description: Integration tests for RunnerClient over real HTTP against
    the runner server (host mode): verdicts come back, and every way the
    runner can fail becomes an error that is never the player's fault.
Author(s): Richard Hall, Tyler Black
"""

import http.client
import re
import socket
import threading
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from src.business.runner_client import (
    DEFAULT_TIMEOUT_SECONDS,
    WORST_CASE_SECONDS,
    CheckScriptBrokenError,
    RunnerClient,
    RunnerUnavailableError,
)
from src.runner.grading import CHECK_RUN_MARGIN_SECONDS
from src.runner.limits import PRODUCTION_LIMITS, SandboxLimits
from src.runner.server import RunnerHTTPServer
from src.runner.service import SLOT_WAIT_SECONDS, RunnerService
from src.runner.session import REAP_TIMEOUT_SECONDS
from src.runner.slots import SlotPool

ROOT = Path(__file__).resolve().parents[2]

ECHO = "import sys\nfor line in sys.stdin:\n    print(line.strip())\n"
ECHO += "    print('---')\n"
ECHO_CHECK = (
    "def check(game):\n    game.check(game.tick('q') == 'q', 'echo')\n"
)


def test_pass_and_fail_verdicts(local_runner: str):
    client = RunnerClient(local_runner)
    assert client.grade(ECHO, ECHO_CHECK)["verdict"] == "pass"
    failing = client.grade("input()\nprint('x\\n---')\n", ECHO_CHECK)
    assert (failing["verdict"], failing["rule"]) == ("fail", "echo")


def test_broken_check_script(local_runner: str):
    with pytest.raises(CheckScriptBrokenError):
        RunnerClient(local_runner).grade(ECHO, "def check(game):\n    1 / 0\n")


@pytest.fixture
def busy_runner(tmp_path: Path) -> Iterator[str]:
    service = RunnerService(
        SlotPool([]), SandboxLimits(memory_bytes=None), slot_wait_seconds=0
    )
    server = RunnerHTTPServer(("127.0.0.1", 0), service, check_peers=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_busy_runner_is_unavailable(busy_runner: str):
    with mock.patch("src.business.runner_client.logger") as logger:
        with pytest.raises(RunnerUnavailableError, match="503"):
            RunnerClient(busy_runner).grade(ECHO, ECHO_CHECK)
    logger.error.assert_called_once()


def test_unreachable_runner_is_unavailable():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    with pytest.raises(RunnerUnavailableError):
        RunnerClient(f"http://127.0.0.1:{free_port}").grade(ECHO, ECHO_CHECK)


def test_timeout_is_unavailable(local_runner: str):
    with mock.patch(
        "src.business.runner_client.urllib.request.urlopen",
        side_effect=TimeoutError("timed out"),
    ):
        with pytest.raises(RunnerUnavailableError, match="timed out"):
            RunnerClient(local_runner).grade(ECHO, ECHO_CHECK)


def test_bad_json_reply_is_unavailable(local_runner: str):
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = b"<html>"
    with mock.patch(
        "src.business.runner_client.urllib.request.urlopen",
        return_value=response,
    ):
        with pytest.raises(RunnerUnavailableError, match="bad JSON"):
            RunnerClient(local_runner).grade(ECHO, ECHO_CHECK)


def test_error_reply_without_json_is_unavailable():
    error = mock.Mock(code=502)
    error.read.return_value = b"Bad gateway"
    with mock.patch("src.business.runner_client.logger"):
        assert isinstance(
            RunnerClient._error_for(error), RunnerUnavailableError
        )


@pytest.fixture
def hang_up_server() -> Iterator[str]:
    """A server that accepts each connection and closes it unanswered."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            connection.recv(65536)
            connection.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    stop.set()
    listener.close()
    thread.join(timeout=5)


def test_dropped_connection_is_unavailable(hang_up_server: str):
    """A runner that hangs up mid-request is never the player's fault."""
    with pytest.raises(RunnerUnavailableError):
        RunnerClient(hang_up_server).grade(ECHO, ECHO_CHECK)


@pytest.mark.parametrize(
    "error",
    [
        http.client.IncompleteRead(b"partial"),
        http.client.RemoteDisconnected("gone"),
        ConnectionResetError("reset"),
    ],
)
def test_broken_reply_is_unavailable(error: Exception):
    with mock.patch(
        "src.business.runner_client.urllib.request.urlopen",
        side_effect=error,
    ):
        with pytest.raises(RunnerUnavailableError):
            RunnerClient("http://runner:9000").grade(ECHO, ECHO_CHECK)


def test_client_timeout_covers_the_runner_worst_case():
    """A slow but valid verdict must arrive before the client gives up.

    The worst case is a full wait for two slots, the check script's whole
    clock, and two reaps. The web server's own timeout must be longer.
    """
    worst_case = (
        SLOT_WAIT_SECONDS
        + PRODUCTION_LIMITS.run_seconds
        + CHECK_RUN_MARGIN_SECONDS
        + 2 * REAP_TIMEOUT_SECONDS
    )
    assert WORST_CASE_SECONDS == worst_case
    assert DEFAULT_TIMEOUT_SECONDS > worst_case
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")
    gunicorn_timeout = int(
        re.search(r'"--timeout", "(\d+)"', dockerfile).group(1)
    )
    assert gunicorn_timeout > DEFAULT_TIMEOUT_SECONDS
