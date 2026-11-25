"""
File: server.py
Description: Standard-library HTTP front end for the runner: POST /run
    plays a program from fixed inputs, POST /grade has a check script
    play it, GET /health reports readiness. Listens on port 9000
    inside the runner container on the internal sandbox network.
Author(s): Richard Hall, Tyler Black
"""

import errno
import json
import logging
import os
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path

from src.runner.limits import PRODUCTION_LIMITS
from src.runner.service import RUNNER_ERROR, RunnerService
from src.runner.slots import SlotPool, production_slots

HOST = "0.0.0.0"
PORT = 9000
# Fits the largest valid request: 64 KB of code (JSON-escaped) plus
# MAX_INPUTS lines of MAX_INPUT_CHARS.
MAX_BODY_BYTES = 1024 * 1024
# Seconds a connection may sit idle while its request is read or its
# reply is written. The grade itself may take longer; nothing is read
# from the socket while it runs.
REQUEST_TIMEOUT_SECONDS = 10.0

logger = logging.getLogger(__name__)


def _proc_endpoint(address: tuple[str, int], ipv6: bool) -> str:
    """Encode an endpoint as Linux prints it in its TCP tables."""
    host, port = address
    packed = ip_address(host).packed
    if ipv6 and len(packed) == 4:
        packed = b"\0" * 10 + b"\xff\xff" + packed
    words = [
        int.from_bytes(packed[index : index + 4], sys.byteorder)
        for index in range(0, len(packed), 4)
    ]
    return "".join(f"{word:08X}" for word in words) + f":{port:04X}"


def tcp_peer_uid(
    table: str,
    peer: tuple[str, int],
    local: tuple[str, int],
    *,
    ipv6: bool = False,
) -> int | None:
    """Find the client socket owner by matching both ends of the flow."""
    peer_address = _proc_endpoint(peer, ipv6)
    local_address = _proc_endpoint(local, ipv6)
    for line in table.splitlines()[1:]:
        fields = line.split()
        # Inode 0 rows have no socket file and cannot establish ownership.
        if fields[1:3] == [peer_address, local_address] and fields[9] != "0":
            return int(fields[7])
    return None


def peer_is_allowed(
    peer: tuple[str, int],
    local: tuple[str, int],
    proc_net: Path = Path("/proc/net"),
) -> bool:
    """Allow root-owned local connections and peers outside the namespace."""
    try:
        for name in ("tcp", "tcp6"):
            try:
                table = (proc_net / name).read_text(encoding="ascii")
            except FileNotFoundError:
                if name == "tcp6":  # The kernel may have IPv6 disabled.
                    continue
                raise
            uid = tcp_peer_uid(table, peer, local, ipv6=name == "tcp6")
            if uid is not None:
                return uid == 0
        # A local socket can close before we inspect it. Probe whether its
        # source address is ours without sending any traffic.
        family = socket.AF_INET6 if ":" in peer[0] else socket.AF_INET
        with socket.socket(family, socket.SOCK_DGRAM) as probe:
            try:
                probe.bind((peer[0], 0))
            except OSError as error:
                return error.errno == errno.EADDRNOTAVAIL
        return False
    except OSError:
        logger.exception("could not inspect the runner request peer")
        return False


class RunnerRequestHandler(BaseHTTPRequestHandler):
    """Routes requests to the ``RunnerService`` bound to the server."""

    server: "RunnerHTTPServer"
    # A client that connects and then goes quiet can't hold a thread.
    timeout = REQUEST_TIMEOUT_SECONDS

    def do_GET(self) -> None:  # noqa: N802 - name required by http.server
        """Answer the health check."""
        if self.path == "/health":
            self._send_json(*self.server.service.health())
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - name required by http.server
        """Run or grade the program in the request body."""
        routes = {
            "/run": self.server.service.run,
            "/grade": self.server.service.grade,
        }
        handle = routes.get(self.path)
        if handle is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send_json(
                HTTPStatus.LENGTH_REQUIRED, {"error": "length required"}
            )
            return
        if not 0 <= length <= MAX_BODY_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "too large"}
            )
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "bad JSON"})
            return
        try:
            status, body = handle(payload)
        except Exception:
            # The HTTP boundary: anything unexpected still gets the one
            # error shape RunnerClient handles, never a dropped connection.
            logger.exception("unexpected error while running a program")
            status, body = RUNNER_ERROR
        self._send_json(status, body)

    def _send_json(self, status: HTTPStatus, body: dict) -> None:
        """Send ``body`` as a JSON response with ``status``."""
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        """Send access logs to ``logging`` instead of stderr."""
        logger.info(format, *args)


class RunnerHTTPServer(ThreadingHTTPServer):
    """A threaded HTTP server that carries the ``RunnerService``."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        service: RunnerService,
        *,
        check_peers: bool = True,
    ) -> None:
        """Listen on ``address`` and answer with ``service``.

        Args:
            address: Host and port to listen on.
            service: Answers the requests.
            check_peers: Refuse local, non-root clients (player programs).
                Only host-mode tests turn this off, since the check reads
                Linux's ``/proc/net`` tables.
        """
        super().__init__(address, RunnerRequestHandler)
        self.service = service
        self.check_peers = check_peers

    def verify_request(
        self, request: socket.socket, client_address: tuple[str, int]
    ) -> bool:
        """Drop a local, non-root client before it gets a thread.

        Player programs share this container's network, so they could
        call the API or park idle connections on server threads (which
        count toward the container's process limit). This runs in the
        accept loop, so a refused connection never costs a thread. The
        healthcheck and the hostile suite connect as root and pass.
        """
        if not self.check_peers:
            return True
        allowed = peer_is_allowed(client_address, request.getsockname())
        if not allowed:
            logger.warning(
                "refused a local connection from %s", client_address
            )
        return allowed


def main() -> int:
    """Start the production runner. Refuses to run outside the container.

    Returns:
        The process exit code.
    """
    logging.basicConfig(level=logging.INFO)
    if os.geteuid() != 0:
        logger.error("the runner must start as root to switch slot users")
        return 1
    service = RunnerService(SlotPool(production_slots()), PRODUCTION_LIMITS)
    server = RunnerHTTPServer((HOST, PORT), service)
    logger.info("runner listening on %s:%s", HOST, PORT)
    server.serve_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover - container entry point
    raise SystemExit(main())
