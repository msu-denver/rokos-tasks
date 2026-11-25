"""
File: test_runner_service.py
Description: Unit tests for RunnerService and the runner HTTP server:
    request checks, status mapping, busy and launch-failure replies, and
    the /run and /health routes over a real local socket (host mode).
Author(s): Richard Hall, Tyler Black
"""

import errno
import http.client
import json
import sys
import threading
from collections.abc import Iterator
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

from src.runner import server as runner_server
from src.runner.grading import CHECK_SCRIPT_BYTES, CheckScriptError
from src.runner.limits import SandboxLimits
from src.runner.service import (
    MAX_INPUT_CHARS,
    MAX_INPUTS,
    RunnerService,
    RunRequestError,
    parse_grade_request,
    parse_run_request,
)
from src.runner.session import LaunchError
from src.runner.slots import Slot, SlotCompromisedError, SlotPool

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="Linux only; CI runs it (POSIX APIs)"
)
HOST_LIMITS = SandboxLimits(memory_bytes=None, turn_seconds=2.0)
ECHO = "print('ready')\nwhile True:\n    print(input())\n"


@pytest.fixture
def service(tmp_path: Path) -> RunnerService:
    slots = []
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        slots.append(Slot(None, tmp_path / name))
    return RunnerService(SlotPool(slots), HOST_LIMITS)


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
        ({"code": "", "inputs": ["x" * 65]}, "one line"),
    ],
)
def test_bad_requests_are_rejected(payload: object, message: str):
    with pytest.raises(RunRequestError, match=message):
        parse_run_request(payload, SandboxLimits())


@POSIX_ONLY
def test_completed_run(service: RunnerService):
    status, body = service.run({"code": ECHO, "inputs": ["q", "p"]})
    assert status == HTTPStatus.OK
    assert body == {
        "status": "completed",
        "screens": ["ready", "q", "p"],
        "finished": False,
        "stderr": "",
        "exit_code": None,
    }


@POSIX_ONLY
def test_program_that_prints_and_exits_completes(service: RunnerService):
    status, body = service.run({"code": "print('board')\n", "inputs": []})
    assert status == HTTPStatus.OK
    assert body["status"] == "completed"
    assert (body["screens"], body["finished"]) == (["board"], True)


@POSIX_ONLY
def test_input_after_the_program_exits_is_exited(service: RunnerService):
    code = "print(input())\n"
    status, body = service.run({"code": code, "inputs": ["a", "b"]})
    assert status == HTTPStatus.OK
    assert body["status"] == "exited"
    assert body["screens"] == ["", "a"]
    assert body["exit_code"] == 0


@POSIX_ONLY
def test_crash_keeps_screens_so_far_and_exit_code(service: RunnerService):
    code = "input()\nprint('one')\ninput()\nraise SystemExit(3)\n"
    status, body = service.run({"code": code, "inputs": ["", ""]})
    assert status == HTTPStatus.OK
    assert body["status"] == "crashed"
    assert body["screens"] == ["", "one"]
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
    assert "sandbox failed" in logger.exception.call_args.args[0]


@POSIX_ONLY
def test_compromised_slot_is_500(service: RunnerService):
    with mock.patch(
        "src.runner.service.ProgramSession.close",
        side_effect=SlotCompromisedError("left over"),
    ):
        status, body = service.run({"code": "", "inputs": []})
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert body == {"status": "runner_error"}


ONE_TURN_CHECK = (
    "def check(game):\n    game.check(game.send('q') == 'q', 'echo')\n"
)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"code": ""}, "'check_script'"),
        ({"code": "", "check_script": "  "}, "'check_script'"),
        (
            {"code": "", "check_script": "x" * (CHECK_SCRIPT_BYTES + 1)},
            "larger",
        ),
        ({"check_script": "x"}, "'code'"),
    ],
)
def test_bad_grade_requests_are_rejected(payload: dict, message: str):
    with pytest.raises(RunRequestError, match=message):
        parse_grade_request(payload, SandboxLimits())


@POSIX_ONLY
def test_grade_returns_the_verdict(service: RunnerService):
    status, body = service.grade(
        {"code": ECHO, "check_script": ONE_TURN_CHECK}
    )
    assert status == HTTPStatus.OK
    assert body["verdict"] == "pass"
    assert body["inputs"] == ["q"]


def test_bad_grade_request_is_400(service: RunnerService):
    status, _ = service.grade({"code": ECHO})
    assert status == HTTPStatus.BAD_REQUEST


def test_grade_needs_two_free_slots(tmp_path: Path):
    lonely = RunnerService(
        SlotPool([Slot(None, tmp_path)]), HOST_LIMITS, slot_wait_seconds=0
    )
    status, _ = lonely.grade({"code": ECHO, "check_script": ONE_TURN_CHECK})
    assert status == HTTPStatus.SERVICE_UNAVAILABLE


def test_broken_check_script_is_500_check_error(service: RunnerService):
    error = CheckScriptError("crashed")
    error.stderr = "ZeroDivisionError"
    with (
        mock.patch("src.runner.service.Grader.grade", side_effect=error),
        mock.patch("src.runner.service.logger") as logger,
    ):
        status, body = service.grade({"code": ECHO, "check_script": "x"})
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert body == {"status": "check_error"}
    assert "ZeroDivisionError" in logger.error.call_args.args


@pytest.fixture
def http_server(
    service: RunnerService, monkeypatch: pytest.MonkeyPatch
) -> Iterator[int]:
    monkeypatch.setattr(runner_server, "peer_is_allowed", lambda *_: True)
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


def handle_http(
    service: RunnerService, method: str, path: str
) -> tuple[int, dict]:
    """Run the real request handler against one in-memory HTTP request."""
    handler = runner_server.RunnerRequestHandler.__new__(
        runner_server.RunnerRequestHandler
    )
    handler.server = mock.Mock(service=service)
    handler.connection = mock.Mock()
    handler.connection.getsockname.return_value = TCP_SERVER
    handler.client_address = TCP_PEER
    handler.rfile = BytesIO(
        f"{method} {path} HTTP/1.1\r\nContent-Length: 0\r\n\r\n".encode()
    )
    handler.wfile = BytesIO()
    handler.handle_one_request()
    headers, body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)
    return int(headers.split()[1]), json.loads(body)


def test_health_reports_retired_slots(service: RunnerService) -> None:
    assert handle_http(service, "GET", "/health") == (200, {"ok": True})
    with pytest.raises(SlotCompromisedError):
        with service._pool.acquire(timeout=0):
            raise SlotCompromisedError("left over")
    assert handle_http(service, "GET", "/health") == (
        503,
        {"ok": False, "retired": 1},
    )


@pytest.fixture
def httpd(service: RunnerService) -> Iterator[runner_server.RunnerHTTPServer]:
    server = runner_server.RunnerHTTPServer(("127.0.0.1", 0), service)
    yield server
    server.server_close()


@pytest.mark.parametrize("allowed", [True, False])
def test_peer_check_runs_before_a_thread_is_spawned(
    httpd: runner_server.RunnerHTTPServer, allowed: bool
) -> None:
    """A refused local client is dropped in the accept loop.

    ``verify_request`` runs before ``ThreadingHTTPServer`` starts a
    thread, so idle player connections can't use up server threads.
    """
    request = mock.Mock()
    request.getsockname.return_value = TCP_SERVER
    with (
        mock.patch.object(
            runner_server, "peer_is_allowed", return_value=allowed
        ) as policy,
        mock.patch.object(runner_server, "logger") as logger,
    ):
        assert httpd.verify_request(request, TCP_PEER) is allowed
    policy.assert_called_once_with(TCP_PEER, TCP_SERVER)
    assert logger.warning.called is not allowed


def test_peer_check_can_be_turned_off_for_host_mode(
    service: RunnerService, httpd: runner_server.RunnerHTTPServer
) -> None:
    """Host-mode tests skip the /proc/net check; production never does."""
    assert httpd.check_peers is True
    host = runner_server.RunnerHTTPServer(
        ("127.0.0.1", 0), service, check_peers=False
    )
    try:
        with mock.patch.object(runner_server, "peer_is_allowed") as policy:
            assert host.verify_request(mock.Mock(), TCP_PEER) is True
        policy.assert_not_called()
    finally:
        host.server_close()


def test_idle_connections_time_out() -> None:
    """A connected client that sends nothing can't hold a thread forever."""
    assert runner_server.RunnerRequestHandler.timeout == (
        runner_server.REQUEST_TIMEOUT_SECONDS
    )
    assert 0 < runner_server.REQUEST_TIMEOUT_SECONDS <= 30


TCP_HEADER = "sl local_address rem_address st tx_queue rx_queue uid\n"
TCP_PEER = ("127.0.0.1", 49152)
TCP_SERVER = ("127.0.0.1", 9000)
V4_HOST = "0100007F" if sys.byteorder == "little" else "7F000001"
V6_MAPPED = (
    "0000000000000000FFFF0000"
    if sys.byteorder == "little"
    else "00000000000000000000FFFF"
) + V4_HOST
V6_LOOPBACK = "000000000000000000000000" + (
    "01000000" if sys.byteorder == "little" else "00000001"
)


@pytest.mark.parametrize(
    ("host", "address", "ipv6"),
    [
        (V4_HOST, TCP_PEER[0], False),
        (V6_MAPPED, TCP_PEER[0], True),
        (V6_LOOPBACK, "::1", True),
    ],
)
def test_tcp_parser_matches_client_tuple(
    host: str, address: str, ipv6: bool
) -> None:
    table = TCP_HEADER + (
        f"0: {host}:2328 {host}:C000 01 0:0 00:0 0 0 0 77\n"
        f"1: {host}:C000 {host}:2329 01 0:0 00:0 0 0 0 78\n"
        f"2: {host}:C000 {host}:2328 06 0:0 00:0 0 0 0 0\n"
        f"3: {host}:C000 {host}:2328 01 0:0 00:0 0 10001 0 79\n"
    )
    assert (
        runner_server.tcp_peer_uid(
            table, (address, 49152), (address, 9000), ipv6=ipv6
        )
        == 10001
    )
    assert (
        runner_server.tcp_peer_uid(
            table, (address, 49153), (address, 9000), ipv6=ipv6
        )
        is None
    )


@pytest.mark.parametrize(("uid", "allowed"), [(0, True), (10001, False)])
def test_peer_policy_uses_the_tcp_owner(
    tmp_path: Path, uid: int, allowed: bool
) -> None:
    (tmp_path / "tcp").write_text(TCP_HEADER)
    (tmp_path / "tcp6").write_text(
        TCP_HEADER
        + (f"0: {V6_MAPPED}:C000 {V6_MAPPED}:2328 01 0:0 00:0 0 {uid} 0 79\n")
    )
    assert (
        runner_server.peer_is_allowed(TCP_PEER, TCP_SERVER, tmp_path)
        is allowed
    )


@pytest.mark.parametrize(
    ("bind_error", "allowed"),
    [(None, False), (errno.EADDRNOTAVAIL, True), (errno.EACCES, False)],
)
def test_peer_policy_checks_unknown_source_addresses(
    tmp_path: Path, bind_error: int | None, allowed: bool
) -> None:
    (tmp_path / "tcp").write_text(TCP_HEADER)
    with mock.patch.object(runner_server.socket, "socket") as socket_factory:
        probe = socket_factory.return_value.__enter__.return_value
        if bind_error is not None:
            probe.bind.side_effect = OSError(bind_error, "bind failed")
        assert (
            runner_server.peer_is_allowed(TCP_PEER, TCP_SERVER, tmp_path)
            is allowed
        )
    probe.bind.assert_called_once_with((TCP_PEER[0], 0))


def test_peer_policy_denies_unreadable_tcp_table(tmp_path: Path) -> None:
    assert not runner_server.peer_is_allowed(TCP_PEER, TCP_SERVER, tmp_path)


def test_unknown_paths_are_404(http_server: int):
    assert request(http_server, "GET", "/nope")[0] == 404
    assert request(http_server, "POST", "/nope", b"{}")[0] == 404


@POSIX_ONLY
def test_run_over_http(http_server: int):
    body = json.dumps({"code": ECHO, "inputs": ["a"]}).encode()
    status, reply = request(http_server, "POST", "/run", body)
    assert status == 200
    assert reply["screens"] == ["ready", "a"]


@POSIX_ONLY
def test_grade_over_http(http_server: int):
    body = json.dumps({"code": ECHO, "check_script": ONE_TURN_CHECK}).encode()
    status, reply = request(http_server, "POST", "/grade", body)
    assert (status, reply["verdict"]) == (200, "pass")


def test_bad_json_is_400(http_server: int):
    assert request(http_server, "POST", "/run", b"{nope")[0] == 400


def test_body_size_is_capped(http_server: int):
    too_big = {"Content-Length": str(runner_server.MAX_BODY_BYTES + 1)}
    status, _ = request(http_server, "POST", "/run", b"", too_big)
    assert status == 413


def test_unexpected_error_still_gets_json(http_server: int):
    with (
        mock.patch.object(RunnerService, "run", side_effect=RuntimeError),
        mock.patch.object(runner_server, "logger"),
    ):
        status, body = request(http_server, "POST", "/run", b"{}")
    assert (status, body) == (500, {"status": "runner_error"})


def test_missing_length_is_411(http_server: int):
    connection = http.client.HTTPConnection("127.0.0.1", http_server)
    connection.putrequest("POST", "/run")
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 411
    connection.close()


def test_main_refuses_to_start_unprivileged():
    with (
        mock.patch.object(
            runner_server.os, "geteuid", return_value=1000, create=True
        ),
        mock.patch.object(runner_server, "logger") as logger,
    ):
        assert runner_server.main() == 1
    assert "must start as root" in logger.error.call_args.args[0]


def test_main_serves_with_production_settings():
    with (
        mock.patch.object(
            runner_server.os, "geteuid", return_value=0, create=True
        ),
        mock.patch.object(runner_server, "RunnerHTTPServer") as server_class,
    ):
        assert runner_server.main() == 0
    address, _service = server_class.call_args.args
    assert address == ("0.0.0.0", 9000)
    server_class.return_value.serve_forever.assert_called_once()


def test_largest_valid_requests_fit_the_body_cap():
    worst_code = "\x01" * (64 * 1024)  # JSON-escapes to six bytes each
    largest_run = {
        "code": worst_code,
        "inputs": ["x" * MAX_INPUT_CHARS] * MAX_INPUTS,
    }
    largest_grade = {
        "code": worst_code,
        "check_script": "\x01" * CHECK_SCRIPT_BYTES,
    }
    parse_run_request(largest_run, SandboxLimits())
    parse_grade_request(largest_grade, SandboxLimits())
    for largest in (largest_run, largest_grade):
        size = len(json.dumps(largest).encode())
        assert size <= runner_server.MAX_BODY_BYTES
