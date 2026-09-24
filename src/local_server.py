"""Dependency-free local API for demonstrating the voice automation workflow."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from start_call import parse_event
from summarize_call import fallback_summary, transcript_text

HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "1000"))
if HISTORY_LIMIT < 1:
    raise ValueError("HISTORY_LIMIT must be at least 1")


class VoiceAutomationDemo:
    def __init__(self) -> None:
        self._calls: list[dict[str, Any]] = []
        self._summaries: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def start_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        destination, attributes = parse_event(payload)
        call = {
            "contact_id": str(uuid.uuid4()),
            "destination": destination,
            "attributes": attributes,
            "status": "ROUTED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": "local-simulator",
        }
        with self._lock:
            self._calls.append(call)
            del self._calls[:-HISTORY_LIMIT]
        return call

    def summarize(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = transcript_text(payload)
        result = {
            "summary_id": str(uuid.uuid4()),
            "summary": fallback_summary(text),
            "character_count": len(text),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "local-extractive",
        }
        with self._lock:
            self._summaries.append(result)
            del self._summaries[:-HISTORY_LIMIT]
        return result

    def calls(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._calls)

    def summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._summaries)


DEMO = VoiceAutomationDemo()


class Handler(BaseHTTPRequestHandler):
    server_version = "VoiceAutomationLocal/1.0"

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 1_000_000:
            raise ValueError("Request body must contain 1 to 1000000 bytes")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object")
        return value

    def do_GET(self) -> None:
        routes = {
            "/health": lambda: {"status": "UP", "service": "voice-automation"},
            "/calls": DEMO.calls,
            "/summaries": DEMO.summaries,
        }
        route = routes.get(self.path)
        self._json(HTTPStatus.OK, route()) if route else self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        try:
            payload = self._body()
            if self.path == "/calls":
                self._json(HTTPStatus.ACCEPTED, DEMO.start_call(payload))
            elif self.path == "/transcripts":
                self._json(HTTPStatus.CREATED, DEMO.summarize(payload))
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except (ValueError, json.JSONDecodeError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def log_message(self, format_string: str, *args: Any) -> None:
        print(json.dumps({"service": "voice-automation", "message": format_string % args}))


def main() -> None:
    port = int(os.environ.get("PORT", "8001"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Voice automation local API listening on http://localhost:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
