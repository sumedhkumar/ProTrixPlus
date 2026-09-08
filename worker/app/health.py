"""Minimal stdlib HTTP health endpoint for the worker (no web framework)."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from redis import Redis
from sqlalchemy import Engine, text

from app import __version__

log = logging.getLogger("worker.health")


def _checks(engine: Engine, redis_url: str) -> tuple[bool, dict[str, dict[str, str]]]:
    checks: dict[str, dict[str, str]] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = {"status": "error", "detail": exc.__class__.__name__}
    try:
        client = Redis.from_url(redis_url, socket_connect_timeout=2)
        with client:
            client.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = {"status": "error", "detail": exc.__class__.__name__}
    healthy = all(c["status"] == "ok" for c in checks.values())
    return healthy, checks


def start_health_server(
    *, port: int, engine: Engine, redis_url: str, service: str
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/") not in ("", "/health"):
                self.send_response(404)
                self.end_headers()
                return
            healthy, checks = _checks(engine, redis_url)
            body = json.dumps(
                {
                    "service": service,
                    "version": __version__,
                    "status": "ok" if healthy else "degraded",
                    "checks": checks,
                }
            ).encode()
            self.send_response(200 if healthy else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)  # noqa: S104
    thread = threading.Thread(target=server.serve_forever, name="health", daemon=True)
    thread.start()
    log.info("health server listening on :%d", port)
    return server
