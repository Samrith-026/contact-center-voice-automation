"""Amazon Connect outbound-call Lambda handler."""

from __future__ import annotations

import json
import os
import re
from typing import Any


E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_event(event: dict[str, Any]) -> tuple[str, dict[str, str]]:
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")

    destination = str(body.get("destination_phone_number", "")).strip()
    if not E164.fullmatch(destination):
        raise ValueError("destination_phone_number must use E.164 format")

    raw_attributes = body.get("attributes", {})
    if not isinstance(raw_attributes, dict) or len(raw_attributes) > 32:
        raise ValueError("attributes must be a JSON object with at most 32 entries")
    attributes: dict[str, str] = {}
    for key, value in raw_attributes.items():
        name, text = str(key), str(value)
        if not name or len(name) > 32 or len(text) > 32767:
            raise ValueError("attribute names must be 1 to 32 characters and values at most 32767 characters")
        attributes[name] = text
    return destination, attributes


def handler(event: dict[str, Any], _context: Any, connect_client: Any = None) -> dict[str, Any]:
    destination, attributes = parse_event(event)
    if connect_client is None:
        import boto3

        connect_client = boto3.client("connect")

    response = connect_client.start_outbound_voice_contact(
        DestinationPhoneNumber=destination,
        ContactFlowId=_required("CONTACT_FLOW_ID"),
        InstanceId=_required("CONNECT_INSTANCE_ID"),
        SourcePhoneNumber=_required("SOURCE_PHONE_NUMBER"),
        Attributes=attributes,
        RingTimeoutInSeconds=30,
    )
    return {
        "statusCode": 202,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"contact_id": response["ContactId"], "status": "accepted"}),
    }
