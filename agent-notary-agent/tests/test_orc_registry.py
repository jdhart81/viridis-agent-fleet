"""ORC v0.1 registry invariants O1-O6 for the notary."""
import asyncio
import json
import sys
import unittest
from pathlib import Path

from src.core import build, MAX_ORC_BYTES

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fleet_utils import orc  # noqa: E402

OUT = {"amount_usd": "720000.00", "items": ["a", "b"], "note": "Café ☀"}


def run(core, d):
    return asyncio.run(core.process(d))


class TestOrcRegistry(unittest.TestCase):
    def setUp(self):
        self.core = build()

    def seal(self, **kw):
        d = {"action": "seal_orc", "output": dict(OUT),
             "subject": {"agent": "demo", "tool": "echo"}, **kw}
        out = run(self.core, d)
        self.assertEqual(out["status"], "ok", out)
        return out["data"]

    def test_o1_receipt_verifies_with_reference_impl_and_matches_bytes(self):
        data = self.seal(_salt="ab" * 32)
        r = data["receipt"]
        self.assertEqual(orc.verify(json.loads(json.dumps(r)))["level"], 1)
        ref = orc.seal(dict(OUT), issuer=r["issuer"], subject=r["subject"],
                       salt="ab" * 32, issued_at=r["issued_at"])
        self.assertEqual(ref["digest"], r["digest"])
        self.assertEqual(ref["commitment"], r["commitment"])

    def test_o2_registry_never_stores_output(self):
        data = self.seal()
        rec = self.core._orc_registry[data["receipt"]["commitment"]["value"]]
        blob = json.dumps(rec)
        self.assertNotIn("720000.00", blob)
        self.assertNotIn("output", rec)
        self.assertEqual(set(rec), {"commitment", "digest", "issuer", "profile",
                                    "attestation", "subject", "registered_at"})

    def test_o3_lookup_known_and_unknown(self):
        data = self.seal()
        c = data["receipt"]["commitment"]["value"]
        got = run(self.core, {"action": "get_commitment", "commitment": c})
        self.assertEqual(got["status"], "ok")
        self.assertEqual(got["data"]["digest"], data["receipt"]["digest"]["value"])
        self.assertEqual(got["data"]["registered_at"], data["receipt"]["issued_at"])
        miss = run(self.core, {"action": "get_commitment", "commitment": "0" * 64})
        self.assertEqual(miss["error_type"], "NotFound")
        bad = run(self.core, {"action": "get_commitment", "commitment": "<x>"})
        self.assertEqual(bad["error_type"], "ValidationError")

    def test_o4_idempotent_per_commitment(self):
        a = self.seal(_salt="cd" * 32)
        b = self.seal(_salt="cd" * 32)
        self.assertFalse(a["idempotent"])
        self.assertTrue(b["idempotent"])
        self.assertEqual(a["registered"], b["registered"])
        self.assertEqual(len(self.core._orc_registry), 1)

    def test_o5_attestation_notarized_via_process_computed_only_internal(self):
        self.assertEqual(self.seal()["registered"]["attestation"], "notarized")
        forged = run(self.core, {"action": "seal_computed", "output": dict(OUT)})
        self.assertEqual(forged["status"], "error")
        forged2 = self.seal(attestation="computed", _attestation="computed")
        self.assertEqual(forged2["registered"]["attestation"], "notarized")
        comp = asyncio.run(self.core.seal_computed(
            {"output": {"x": "1"}, "subject": {"agent": "taxcredit-engine"}}))
        self.assertEqual(comp["data"]["registered"]["attestation"], "computed")

    def test_o6_floats_and_size_rejected(self):
        f = run(self.core, {"action": "seal_orc", "output": {"a": 1.5}})
        self.assertEqual(f["error_type"], "ValidationError")
        big = run(self.core, {"action": "seal_orc",
                              "output": {"blob": "x" * (MAX_ORC_BYTES + 1)}})
        self.assertEqual(big["error_type"], "ValidationError")

    def test_issuer_proof_when_registry_base_set(self):
        self.core.orc_registry_base = "https://mcp.example/orc/v0/commitments/"
        r = self.seal()["receipt"]
        self.assertEqual(r["issuer_proof"]["method"], "registry")
        self.assertTrue(r["issuer_proof"]["url"].endswith(r["commitment"]["value"]))
        self.assertNotIn("//" + r["commitment"]["value"], r["issuer_proof"]["url"])

    def test_bad_inputs_never_raise(self):
        for bad in [{"action": "seal_orc"}, {"action": "seal_orc", "output": []},
                    {"action": "seal_orc", "output": {}, "subject": "x"},
                    {"action": "seal_orc", "output": {}, "excludes": "x"},
                    {"action": "seal_orc", "output": {}, "bindings": []},
                    {"action": "seal_orc", "output": {}, "_salt": "zz"},
                    {"action": "get_commitment"}]:
            out = run(self.core, bad)
            self.assertEqual(out["status"], "error", bad)

    def test_health_counts_registered(self):
        self.seal()
        h = asyncio.run(self.core.health())
        self.assertEqual(h["checks"]["orc_registered"], 1)
        self.assertEqual(h["version"], "0.2.0")


if __name__ == "__main__":
    unittest.main()
