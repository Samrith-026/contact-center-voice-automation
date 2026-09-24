"""Summarize Amazon Connect transcript objects written to S3."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote_plus


def transcript_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        parts = []
        for item in payload:
            if isinstance(item, dict):
                speaker = item.get("participantRole") or item.get("speaker") or "Unknown"
                text = item.get("content") or item.get("text") or ""
                if text:
                    parts.append(f"{speaker}: {text}")
        return "\n".join(parts)
    if isinstance(payload, dict):
        for key in ("Transcript", "transcript", "segments", "messages"):
            if key in payload:
                return transcript_text(payload[key])
    raise ValueError("No supported transcript content found")


def fallback_summary(text: str, limit: int = 3) -> str:
    sentences = [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]
    return ". ".join(sentences[:limit]) + ("." if sentences else "")


def bedrock_summary(text: str, client: Any, model_id: str) -> str:
    prompt = (
        "Summarize this customer call in at most five bullets. Include the reason for the call, "
        "resolution, unresolved risks, sentiment, and next action. Do not invent facts.\n\n" + text[:45000]
    )
    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 500, "temperature": 0.1},
    )
    return response["output"]["message"]["content"][0]["text"].strip()


def process_record(record: dict[str, Any], s3: Any, cloudwatch: Any, bedrock: Any = None) -> dict[str, str]:
    bucket = record["s3"]["bucket"]["name"]
    key = unquote_plus(record["s3"]["object"]["key"])
    payload = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    text = transcript_text(payload)
    model_id = os.environ.get("BEDROCK_MODEL_ID", "").strip()
    summary = bedrock_summary(text, bedrock, model_id) if model_id and bedrock else fallback_summary(text)
    output_key = "summaries/" + key.removeprefix("transcripts/").rsplit(".", 1)[0] + ".summary.json"
    result = {
        "source": key,
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "bedrock" if model_id and bedrock else "extractive",
    }
    s3.put_object(
        Bucket=bucket,
        Key=output_key,
        Body=json.dumps(result, indent=2).encode(),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    cloudwatch.put_metric_data(
        Namespace=os.environ.get("METRIC_NAMESPACE", "VoiceAutomationPOC"),
        MetricData=[{"MetricName": "TranscriptsSummarized", "Value": 1, "Unit": "Count"}],
    )
    return {"source": key, "output": output_key}


def handler(event: dict[str, Any], _context: Any, s3_client: Any = None, cloudwatch_client: Any = None, bedrock_client: Any = None) -> dict[str, Any]:
    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")
        cloudwatch_client = boto3.client("cloudwatch")
        if os.environ.get("BEDROCK_MODEL_ID", "").strip():
            bedrock_client = boto3.client("bedrock-runtime")
    processed = [process_record(r, s3_client, cloudwatch_client, bedrock_client) for r in event.get("Records", [])]
    return {"processed": processed}


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as stream:
        print(fallback_summary(transcript_text(json.load(stream))))
