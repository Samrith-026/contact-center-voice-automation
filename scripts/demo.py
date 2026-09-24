"""Exercise the local call routing and transcript-summary workflow."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen


BASE_URL = "http://localhost:8001"


def request(path: str, payload: dict | None = None) -> dict | list:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    with urlopen(Request(f"{BASE_URL}{path}", data=body, headers=headers), timeout=5) as response:
        return json.load(response)


def main() -> None:
    print("health:", request("/health"))
    print("call:", request("/calls", {
        "destination_phone_number": "+12145550100",
        "attributes": {"customerId": "demo-42", "reason": "delivery-status"},
    }))
    with open("fixtures/transcript.json", encoding="utf-8") as stream:
        transcript = json.load(stream)
    print("summary:", request("/transcripts", transcript))


if __name__ == "__main__":
    main()

