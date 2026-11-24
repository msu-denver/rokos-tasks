"""
File: server.py
Description: Standard-library HTTP front end for the runner: POST /run
    plays a program, GET /health reports readiness. Listens on port 9000
    inside the runner container, which only the web container can reach.
Author(s): Tyler Black
"""

import json
import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.runner.limits import PRODUCTION_LIMITS
from src.runner.service import RUNNER_ERROR, RunnerService
from src.runner.slots import SlotPool, production_slots

HOST = "0.0.0.0"
PORT = 9000
# Fits the largest valid request: 64 KB of code (JSON-escaped) plus
# MAX_INPUTS lines of MAX_INPUT_CHARS.
MAX_BODY_BYTES = 1024 * 1024

logger = logging.getLogger(__name__)


class RunnerRequestHandler(BaseHTTPRequestHandler):
    """Routes requests to the ``RunnerService`` bound to the server."""

    server: "RunnerHTTPServer"

    def do_GET(self) -> None:  # noqa: N802 - name required by http.server
        """Answer the health check."""
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"ok": True})
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - name required by http.server
        """Play the program in the request body."""
        if self.path != "/run":
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
            status, body = self.server.service.run(payload)
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
        self, address: tuple[str, int], service: RunnerService
    ) -> None:
        """Listen on ``address`` and answer with ``service``."""
        super().__init__(address, RunnerRequestHandler)
        self.service = service


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
