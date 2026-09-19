"""Buyer feedback uses synthetic receipts and transports; no live outcome writes."""
import copy
import io
import json
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import viridis_preflight_feedback as client
from viridis_preflight_watch import _digest

TOKEN = "synthetic-private-feedback-token-" + "x" * 32


def paid_result():
    result = {"status": "ok", "receipt": {"receipt_id": "vsr_" + "a" * 24}}
    delivery = {"version": "viridis-paid-delivery-v1",
                "route": "security-preflight/security_preflight",
                "settlement": {"transaction": "synthetic-reference"},
                "result_sha256": _digest(result),
                "feedback": {"version": client.VERSION,
                    "endpoint": "https://mcp.viridisconservation.com/x402/feedback",
                    "method": "POST", "feedback_token": TOKEN, "exactly_once": True}}
    delivery["receipt_sha256"] = _digest(delivery)
    return {**result, "viridis_delivery": delivery}


def rehash(result):
    delivery = result["viridis_delivery"]
    delivery["receipt_sha256"] = _digest({k: v for k, v in delivery.items()
                                          if k != "receipt_sha256"})


def recorded(payload, *, replay=False):
    return {"version": client.VERSION, "status": "RECORDED",
            "feedback_recorded": True, "idempotent_replay": replay,
            "feedback": {"version": client.VERSION,
                "classification": "buyer_possession_feedback",
                "independently_verified": False, "revenue_signal": False,
                "outcome": payload["outcome"],
                "useful": payload["outcome"] == "USEFUL",
                "would_buy_again": payload["would_buy_again"],
                "reason_code": payload["reason_code"],
                "note_sha256": None,
                "recorded_at": "2026-09-19T12:00:00+00:00",
                "request_sha256": client._digest({**{k: payload[k] for k in
                    ("outcome", "would_buy_again", "reason_code", "idempotency_key")},
                    "note_sha256": None}),
                "idempotency_key": payload["idempotency_key"]}}


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "feedback.json"

    def run_client(self, result=None, **kwargs):
        return client.run(paid_result() if result is None else result,
                          outcome="PARTIALLY_USEFUL", would_buy_again=False,
                          reason="missing_evidence", **kwargs)

    def test_preview_never_transmits_or_exposes_token(self):
        preview = self.run_client(transport=lambda *args: self.fail("network called"))
        self.assertEqual(preview["status"], "FEEDBACK_PREVIEW")
        self.assertFalse(preview["feedback_recorded"])
        self.assertFalse(preview["would_buy_again"])
        self.assertNotIn(TOKEN, json.dumps(preview))
        self.assertNotIn("feedback_token", preview)

    def test_no_opinion_or_boolean_inference(self):
        for outcome, again, reason in [(None, True, None), ("USEFUL", "yes", None),
                                      ("USEFUL", 1, None), ("USEFUL", True, "secret")]:
            with self.subTest(outcome=outcome, again=again, reason=reason):
                with self.assertRaises(client.FeedbackError):
                    client.prepare(paid_result(), outcome=outcome,
                                   would_buy_again=again, reason=reason)

    def test_damaged_saved_result_is_rejected(self):
        result = paid_result()
        result["receipt"]["receipt_id"] = "changed"
        with self.assertRaises(client.FeedbackError):
            self.run_client(result)

    def test_rehashed_external_endpoints_and_redirects_are_rejected(self):
        for endpoint in ["https://evil.invalid/x402/feedback", "/x402/feedback",
                         "http://mcp.viridisconservation.com/x402/feedback",
                         "https://mcp.viridisconservation.com/x402/feedback?token=bad",
                         "https://mcp.viridisconservation.com@evil.invalid/x402/feedback"]:
            result = paid_result()
            result["viridis_delivery"]["feedback"]["endpoint"] = endpoint
            rehash(result)
            with self.assertRaises(client.FeedbackError):
                self.run_client(result)
        self.assertIsNone(client.NoRedirect().redirect_request(None, None, 307, "", {}, "https://evil.invalid"))

    def test_unsupported_feedback_contract_is_rejected(self):
        for field, value in [("method", "GET"), ("version", "v0"),
                             ("exactly_once", False), ("feedback_token", "short")]:
            result = paid_result()
            result["viridis_delivery"]["feedback"][field] = value
            rehash(result)
            with self.assertRaises(client.FeedbackError):
                self.run_client(result)

    def test_confirmation_retains_choices_and_sanitizes_remote_fields(self):
        calls = []
        def transport(endpoint, payload, timeout):
            calls.append((endpoint, copy.deepcopy(payload)))
            response = recorded(payload)
            response["untrusted_extra"] = TOKEN
            return 201, response
        summary = self.run_client(submit=True, output=self.output, transport=transport)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["feedback_token"], TOKEN)
        self.assertEqual(summary["outcome"], "PARTIALLY_USEFUL")
        self.assertFalse(summary["would_buy_again"])
        self.assertTrue(summary["feedback_recorded"])
        self.assertFalse(summary["revenue_signal"])
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(json.loads(self.output.read_text()), summary)
        self.assertNotIn(TOKEN, self.output.read_text())

    def test_existing_storage_and_missing_storage_block_network(self):
        with self.assertRaises(client.FeedbackError):
            self.run_client(submit=True, transport=lambda *args: self.fail("network"))
        self.output.write_text("prior result")
        with self.assertRaises(client.FeedbackError):
            self.run_client(submit=True, output=self.output,
                            transport=lambda *args: self.fail("network"))
        self.assertEqual(self.output.read_text(), "prior result")

    def test_uncertain_response_not_retried_and_same_choices_reuse_identity(self):
        calls = []
        def timeout(endpoint, payload, seconds):
            calls.append(copy.deepcopy(payload))
            raise TimeoutError(TOKEN)
        with self.assertRaises(client.FeedbackError):
            self.run_client(submit=True, output=self.output, transport=timeout)
        saved = json.loads(self.output.read_text())
        self.assertEqual(saved["status"], "FEEDBACK_OUTCOME_UNKNOWN")
        self.assertIsNone(saved["feedback_recorded"])
        self.assertEqual(len(calls), 1)
        def replay(endpoint, payload, seconds):
            calls.append(copy.deepcopy(payload))
            return 200, recorded(payload, replay=True)
        second = self.output.with_name("reconciled.json")
        confirmed = self.run_client(submit=True, output=second, transport=replay)
        self.assertEqual(calls[0], calls[1])
        self.assertTrue(confirmed["idempotent_replay"])

    def test_bad_http_and_contradictory_receipt_never_confirm_feedback(self):
        def responses(payload):
            wrong = recorded(payload)
            wrong["feedback"]["outcome"] = "USEFUL"
            return [(307, recorded(payload)), (409, {"status": "ALREADY_RECORDED"}),
                    (500, {"error": TOKEN}), (200, wrong), (200, None),
                    (201, {"version": client.VERSION, "feedback_recorded": True})]
        prepared, _ = client.prepare(paid_result(), outcome="PARTIALLY_USEFUL",
                                    would_buy_again=False, reason="missing_evidence")
        for status, body in responses(prepared):
            self.output.unlink(missing_ok=True)
            with self.subTest(status=status, body_type=type(body).__name__):
                with self.assertRaises(client.FeedbackError):
                    self.run_client(submit=True, output=self.output,
                                    transport=lambda *args: (status, body))
                self.assertIsNone(json.loads(self.output.read_text())["feedback_recorded"])
                self.assertNotIn(TOKEN, self.output.read_text())

    def test_cli_requires_buyer_choices_and_does_not_echo_private_errors(self):
        source = self.output.with_name("paid.json")
        source.write_text(json.dumps(paid_result()))
        args = ["--paid-result", str(source), "--outcome", "NOT_USEFUL",
                "--would-buy-again", "no"]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(client.main(args), 0)
            source.write_text(TOKEN)
            self.assertEqual(client.main(args), 1)
        self.assertNotIn(TOKEN, stdout.getvalue() + stderr.getvalue())

    def test_confirmation_binds_exact_typed_request_and_timestamp(self):
        changes = [("would_buy_again", 0), ("would_buy_again", 0.0),
                   ("note_sha256", "a" * 64), ("request_sha256", "a" * 64),
                   ("recorded_at", "not a date"), ("recorded_at", "2026-09-19T12:00:00")]
        for key, value in changes:
            self.output.unlink(missing_ok=True)
            def transport(endpoint, payload, timeout):
                body = recorded(payload)
                body["feedback"][key] = value
                return 201, body
            with self.subTest(key=key, value=value):
                with self.assertRaises(client.FeedbackError):
                    self.run_client(submit=True, output=self.output, transport=transport)
                self.assertIsNone(json.loads(self.output.read_text())["feedback_recorded"])

    def test_replay_flag_requires_a_boolean(self):
        for value in (None, 0, 1, "true"):
            self.output.unlink(missing_ok=True)
            def transport(endpoint, payload, timeout):
                body = recorded(payload)
                body["idempotent_replay"] = value
                return 201, body
            with self.assertRaises(client.FeedbackError):
                self.run_client(submit=True, output=self.output, transport=transport)


if __name__ == "__main__":
    unittest.main()
