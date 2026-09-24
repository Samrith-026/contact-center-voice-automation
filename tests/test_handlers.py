import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
import start_call
import summarize_call
from local_server import VoiceAutomationDemo


class StartCallTests(unittest.TestCase):
    def test_starts_valid_call(self):
        connect = Mock()
        connect.start_outbound_voice_contact.return_value = {"ContactId": "contact-123"}
        env = {
            "CONTACT_FLOW_ID": "flow-1",
            "CONNECT_INSTANCE_ID": "instance-1",
            "SOURCE_PHONE_NUMBER": "+12145550123",
        }
        with patch.dict(os.environ, env, clear=True):
            result = start_call.handler(
                {"destination_phone_number": "+12145550100", "attributes": {"case": 42}}, None, connect
            )
        self.assertEqual(202, result["statusCode"])
        self.assertEqual("contact-123", json.loads(result["body"])["contact_id"])
        self.assertEqual("42", connect.start_outbound_voice_contact.call_args.kwargs["Attributes"]["case"])

    def test_rejects_non_e164_number(self):
        with self.assertRaisesRegex(ValueError, "E.164"):
            start_call.parse_event({"destination_phone_number": "214-555-0100"})


class SummarizerTests(unittest.TestCase):
    def test_extracts_common_connect_shape(self):
        payload = {"Transcript": [{"participantRole": "CUSTOMER", "content": "Need help"}]}
        self.assertEqual("CUSTOMER: Need help", summarize_call.transcript_text(payload))

    def test_processes_s3_record_without_cloud_calls(self):
        s3 = Mock()
        s3.get_object.return_value = {
            "Body": io.BytesIO(json.dumps({"transcript": "Issue reported. Agent fixed it. Customer confirmed."}).encode())
        }
        metrics = Mock()
        record = {"s3": {"bucket": {"name": "demo"}, "object": {"key": "transcripts/call.json"}}}
        with patch.dict(os.environ, {}, clear=True):
            result = summarize_call.process_record(record, s3, metrics)
        self.assertEqual("summaries/call.summary.json", result["output"])
        s3.put_object.assert_called_once()
        metrics.put_metric_data.assert_called_once()


class LocalDemoTests(unittest.TestCase):
    def test_local_workflow_needs_no_aws_clients(self):
        demo = VoiceAutomationDemo()
        call = demo.start_call({"destination_phone_number": "+12145550100", "attributes": {"case": "42"}})
        summary = demo.summarize({"transcript": "Customer reported a delay. Agent shared tracking. Customer confirmed."})
        self.assertEqual("local-simulator", call["provider"])
        self.assertEqual("local-extractive", summary["mode"])
        self.assertEqual(1, len(demo.calls()))
        self.assertEqual(1, len(demo.summaries()))


if __name__ == "__main__":
    unittest.main()
