#!/usr/bin/env python3
"""Narrow local gateway for TradingView webhook delivery.

Only POST requests to ``/webhook/tradingview/<path-secret>`` are forwarded to
the local API. The gateway intentionally does not expose the API's dashboard,
login, admin, or health routes to the public tunnel.
"""

from __future__ import annotations

import argparse
import http.client
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LOG = logging.getLogger("tradingview-gateway")
PATH_PREFIX = "/webhook/tradingview/"
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
MAX_BODY_BYTES = 64 * 1024


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ProtrixplusTradingViewGateway/1.0"

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlsplit(self.path)
        token = parsed.path[len(PATH_PREFIX) :] if parsed.path.startswith(PATH_PREFIX) else ""
        if not TOKEN_RE.fullmatch(token):
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self.send_error(413 if length > MAX_BODY_BYTES else 400)
            return

        body = self.rfile.read(length)
        upstream_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
        try:
            connection.request(
                "POST",
                upstream_path,
                body=body,
                headers={
                    "Content-Type": self.headers.get("Content-Type", "application/json"),
                    "Content-Length": str(len(body)),
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            response_body = response.read(MAX_BODY_BYTES + 1)
        except (OSError, TimeoutError) as exc:
            LOG.warning("upstream unavailable: %s", exc.__class__.__name__)
            self.send_error(502, "local API unavailable")
            return
        finally:
            connection.close()

        self.send_response(response.status)
        content_type = response.getheader("Content-Type")
        if content_type:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(response_body)
        self.close_connection = True
        LOG.info("forwarded TradingView request status=%s bytes=%s", response.status, len(body))

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self.send_error(404)

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler API
        self.send_error(405)

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler API
        self.send_error(405)

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API
        self.send_error(405)

    def log_message(self, format: str, *args: object) -> None:
        # Never log the request path because it contains the webhook secret.
        LOG.info("client request method=%s", self.command)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), GatewayHandler)
    LOG.info("gateway listening on 127.0.0.1:%s; forwarding only TradingView webhook", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
