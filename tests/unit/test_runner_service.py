"""
File: test_runner_service.py
Description: Unit tests for RunnerService and the runner HTTP server:
    request checks, status mapping, busy and launch-failure replies, and
    the /run and /health routes over a real local socket (host mode).
Author(s): Tyler Black
"""

import http.client
import json
import threading
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from unittest import mock

import pytest

from src.runner import server as runner_server
from src.runner.limits import SandboxLimits
from src.runner.service import (
    MAX_INPUTS,
    RunnerService,
    RunRequestError,
    parse_run_request,
)
from src.runner.session import LaunchError
from src.runner.slots import Slot, SlotPool

HOST_LIMITS = SandboxLimits(memory_bytes=None, tick_seconds=2.0)
ECHO = "while True:\n    line = input()\n    print(line)\n    print('---')\n"


@pytest.fixture
def service(tmp_path: Path) -> RunnerService:
    return RunnerService(SlotPool([Slot(None, tmp_path)]), HOST_LIMITS)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "JSON object"),
        ({"inputs": []}, "'code'"),
        ({"code": "x" * (64 * 1024 + 1), "inputs": []}, "larger"),
        ({"code": "", "inputs": "q"}, "'inputs'"),
        ({"code": "", "inputs": [""] * (MAX_INPUTS + 1)}, "'inputs'"),
        ({"code": "", "inputs": [1]}, "one line"),
        ({"code": "", "inputs": ["a\nb"]}, "one line"),
        ({"code": "", "inputs": ["a\rb"]}, "one line"),
        ({"code": "", "inputs": ["x" * 257]}, "one line"),
    ],
)
def test_bad_requests_are_rejected(payload: object, message: str):
    with pytest.raises(RunRequestError, match=message):
        parse_run_request(payload, SandboxLimits())


def test_completed_run(service: RunnerService):
    status, body = service.run({"code": ECHO, "inputs": ["q", "p"]})
    assert status == HTTPStatus.OK
    assert body == {
        "status": "completed",
        "frames": ["q", "p"],
        "ticks": 2,
        "stderr": "",
        "exit_code": None,
    }


def test_crash_keeps_frames_so_far_and_exit_code(service: RunnerService):
    code = "input()\nprint('---')\ninput()\nraise SystemExit(3)\n"
    status, body = service.run({"code": code, "inputs": ["", ""]})
    assert status == HTTPStatus.OK
    assert body["status"] == "crashed"
    assert body["frames"] == [""]
    assert body["exit_code"] == 3


def test_bad_request_is_400(service: RunnerService):
    status, body = service.run({"code": 5})
    assert status == HTTPStatus.BAD_REQUEST
    assert "'code'" in body["error"]


def test_busy_runner_is_503():
    busy = RunnerService(SlotPool([]), HOST_LIMITS, slot_wait_seconds=0)
    status, _ = busy.run({"code": "", "inputs": []})
    assert status == HTTPStatus.SERVICE_UNAVAILABLE


def test_launch_failure_is_500_not_the_players_fault(service):
    with (
        mock.patch(
            "src.runner.service.ProgramSession.start",
            side_effect=LaunchError("no"),
        ),
        mock.patch("src.runner.service.logger") as logger,
    ):
        status, body = service.run({"code": "", "inputs": [""]})
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert body == {"status": "runner_error"}
    assert "failed to launch" in logger.exception.call_args.args[0]


@pytest.fixture
def http_server(service: RunnerService) -> Iterator[int]:
    httpd = runner_server.RunnerHTTPServer(("127.0.0.1", 0), service)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def request(
    port: int,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    result = response.status, json.loads(response.read())
    connection.close()
    return result


def test_health(http_server: int):
    assert request(http_server, "GET", "/health") == (200, {"ok": True})


def test_unknown_paths_are_404(http_server: int):
    assert request(http_server, "GET", "/nope")[0] == 404
    assert request(http_server, "POST", "/nope", b"{}")[0] == 404


def test_run_over_http(http_server: int):
    body = json.dumps({"code": ECHO, "inputs": ["a"]}).encode()
    status, reply = request(http_server, "POST", "/run", body)
    assert status == 200
    assert reply["frames"] == ["a"]


def test_bad_json_is_400(http_server: int):
    assert request(http_server, "POST", "/run", b"{nope")[0] == 400


def test_body_size_is_capped(http_server: int):
    too_big = {"Content-Length": str(runner_server.MAX_BODY_BYTES + 1)}
    status, _ = request(http_server, "POST", "/run", b"", too_big)
    assert status == 413


def test_missing_length_is_411(http_server: int):
    connection = http.client.HTTPConnection("127.0.0.1", http_server)
    connection.putrequest("POST", "/run")
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 411
    connection.close()


def test_main_refuses_to_start_unprivileged():
    with (
        mock.patch.object(runner_server.os, "geteuid", return_value=1000),
        mock.patch.object(runner_server, "logger") as logger,
    ):
        assert runner_server.main() == 1
    assert "must start as root" in logger.error.call_args.args[0]


def test_main_serves_with_production_settings():
    with (
        mock.patch.object(runner_server.os, "geteuid", return_value=0),
        mock.patch.object(runner_server, "RunnerHTTPServer") as server_class,
    ):
        assert runner_server.main() == 0
    address, _service = server_class.call_args.args
    assert address == ("0.0.0.0", 9000)
    server_class.return_value.serve_forever.assert_called_once()
