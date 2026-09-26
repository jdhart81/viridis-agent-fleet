"""O7-O9: digest-only registration for third-party ORC issuers."""
import asyncio
import hashlib
import json
import sys
import unittest
from pathlib import Path

from src.core import build

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fleet_utils import orc  # noqa: E402

ISSUER = {"id": "did:web:example.com", "name": "Example"}


def receipt():
    return orc.seal({"tool": "double", "result": {"v": 42}}, issuer=ISSUER,
                    subject={"agent": "demo", "tool": "double"})


def body(r, **kw):
    b = {"commitment": r["commitment"]["value"], "salt": r["commitment"]["salt"],
         "digest": r["digest"]["value"], "profile": r["profile"], "issuer": r["issuer"],
         "subject": r["subject"], "issued_at": r["issued_at"]}
    b.update(kw)
    return b


class TestExternal(unittest.TestCase):
    def setUp(self):
        self.core = build()

    def test_o7_registers_and_lookup_confirms_l2(self):
        r = receipt()
        out = self.core.register_external(body(r), "key:acme")
        self.assertEqual(out["status"], "ok", out)
        got = asyncio.run(self.core.process({"action": "get_commitment",
                                             "commitment": r["commitment"]["value"]}))
        rec = got["data"]
        self.assertEqual(rec["digest"], r["digest"]["value"])
        self.assertEqual(rec["issuer"], ISSUER)
        lvl = orc.verify(r, issuer_resolver=lambda x: rec["commitment"] == x["commitment"]["value"]
                         and rec["digest"] == x["digest"]["value"])
        self.assertEqual(lvl["label"], "ISSUED")

    def test_o7_rejects_outputs_and_arguments(self):
        r = receipt()
        for k in ("output", "arguments", "args", "result"):
            out = self.core.register_external(body(r, **{k: {"secret": 1}}), "k")
            self.assertEqual(out["status"], "error", k)
            self.assertNotIn(r["commitment"]["value"], self.core._orc_registry)

    def test_o7_commitment_must_bind(self):
        r = receipt()
        out = self.core.register_external(body(r, digest="0" * 64), "k")
        self.assertEqual(out["error_type"], "ValidationError")
        out = self.core.register_external(body(r, salt="z" * 64), "k")
        self.assertEqual(out["error_type"], "ValidationError")

    def test_o8_attestation_registrant_and_no_viridis_impersonation(self):
        r = receipt()
        rec = self.core.register_external(body(r), "key:acme")["data"]["record"]
        self.assertEqual(rec["attestation"], "registered")
        self.assertEqual(rec["registrant"], "key:acme")
        self.assertNotIn("output", json.dumps(rec))
        v = orc.seal({"a": 1}, issuer={"id": "did:web:viridisconservation.com"}, subject={})
        out = self.core.register_external(body(v), "k")
        self.assertEqual(out["status"], "error")
        self.assertIn("reserved", out["message"])

    def test_o4_idempotent_and_no_rebinding(self):
        r = receipt()
        self.assertFalse(self.core.register_external(body(r), "k")["data"]["idempotent"])
        self.assertTrue(self.core.register_external(body(r), "k")["data"]["idempotent"])
        other = dict(body(r), issuer={"id": "did:web:evil.example"})
        self.assertEqual(self.core.register_external(other, "k2")["status"], "error")

    def test_o9_not_reachable_through_process(self):
        r = receipt()
        out = asyncio.run(self.core.process({"action": "register_external", **body(r)}))
        self.assertEqual(out["status"], "error")
        self.assertNotIn("register_external", self.core.describe()["capabilities"])

    def test_never_raises_on_garbage(self):
        for junk in (None, [], "x", {"commitment": 5}):
            self.assertEqual(self.core.register_external(junk, "k")["status"], "error")


if __name__ == "__main__":
    unittest.main()
