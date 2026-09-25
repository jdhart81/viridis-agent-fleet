"""B9: ORC v0.1 -> ERC-8004 validationResponse export."""
import asyncio
import json
import sys
import unittest
from pathlib import Path

from src.core import build

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fleet_utils import orc  # noqa: E402

RH = "11" * 32


def run(core, d):
    return asyncio.run(core.process(d))


class TestValidationResponse(unittest.TestCase):
    def setUp(self):
        self.core = build()
        self.r = json.loads(json.dumps(orc.seal(
            {"amount_usd": "720000.00"}, issuer={"id": "did:web:x"},
            subject={"agent": "demo"}, salt="ab" * 32,
            issued_at="2026-09-24T00:00:00+00:00")))

    def export(self, **kw):
        d = {"action": "export_validation_response", "receipt": self.r,
             "request_hash": "0x" + RH, "response_uri": "https://x/r.json",
             "replay_ok": True}
        d.update(kw)
        return run(self.core, d)

    def test_pass_matches_reference_mapping(self):
        out = self.export()
        self.assertEqual(out["status"], "ok", out)
        ref = orc.erc8004_validation_response(self.r, request_hash=RH,
                                              response_uri="https://x/r.json",
                                              passed=True)
        self.assertEqual(out["data"]["args"], ref)
        self.assertFalse(out["data"]["signed"])

    def test_zero_when_replay_fails_or_receipt_tampered(self):
        self.assertEqual(self.export(replay_ok=False)["data"]["args"]["response"], 0)
        t = json.loads(json.dumps(self.r)); t["output"]["amount_usd"] = "1.00"
        out = self.export(receipt=t)
        self.assertEqual(out["data"]["args"]["response"], 0)
        self.assertFalse(out["data"]["orc_check"]["digest_recomputes"])

    def test_content_addressed_and_verifiable(self):
        payload = self.export()["data"]
        v = run(self.core, {"action": "verify", "payload": payload})
        self.assertTrue(v["data"]["valid"])
        payload["args"]["response"] = 100 if payload["args"]["response"] == 0 else 0
        self.assertFalse(run(self.core, {"action": "verify", "payload": payload})["data"]["valid"])

    def test_bad_inputs_are_structured_errors(self):
        for kw in ({"receipt": "x"}, {"request_hash": "0x12"},
                   {"response_uri": "http://insecure"}, {"replay_ok": "yes"}):
            out = self.export(**kw)
            self.assertEqual(out["status"], "error", kw)
        self.assertEqual(self.export(private_key="k")["error_type"], "KeyMaterialRefused")

    def test_malformed_receipt_never_raises(self):
        out = self.export(receipt={"orc": "0.1", "digest": 5})
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["args"]["response"], 0)


if __name__ == "__main__":
    unittest.main()
