"""IB1-IB6: the Intelligence Bound action (pure, read-only)."""
import asyncio
import math
import unittest

from src.core import build, KB, LN2


def run(core, **kw):
    return asyncio.run(core.process({"action": "intelligence_bound", **kw}))


class TestIntelligenceBound(unittest.TestCase):
    def test_IB1_landauer_ceiling_matches_physics(self):
        d = run(build(), power_w=1.0)["data"]
        self.assertAlmostEqual(d["landauer_j_per_bit"], 2.870978e-21, delta=1e-26)  # k_B*300*ln2
        self.assertAlmostEqual(d["landauer_bits_per_s"] / 3.4831e20, 1.0, places=3)
        self.assertEqual(d["inputs"]["temperature_k"], 300.0)
        d2 = run(build(), power_w=1000.0, temperature_k=77.0)["data"]
        self.assertAlmostEqual(d2["landauer_bits_per_s"], 1000.0 / (KB * 77.0 * LN2), delta=1e8)

    def test_IB2_min_of_bandwidth_and_power(self):
        power_bound = run(build(), power_w=1.0)["data"]["landauer_bits_per_s"]
        narrow = run(build(), power_w=1.0, bandwidth_bits_per_s=1e9)["data"]
        self.assertEqual((narrow["bound_bits_per_s"], narrow["binding_term"]), (1e9, "bandwidth"))
        wide = run(build(), power_w=1.0, bandwidth_bits_per_s=1e30)["data"]
        self.assertEqual(wide["binding_term"], "power")
        self.assertEqual(wide["bound_bits_per_s"], power_bound)

    def test_IB3_IB4_measured_rate(self):
        d = run(build(), power_w=700.0, measured_bits_per_s=1e12)["data"]
        self.assertTrue(0 < d["efficiency_vs_bound"] <= 1)
        self.assertAlmostEqual(d["orders_below_bound"],
                               math.log10(d["bound_bits_per_s"] / 1e12), places=9)
        at_bound = run(build(), power_w=1.0, bandwidth_bits_per_s=5e9,
                       measured_bits_per_s=5e9)["data"]
        self.assertEqual(at_bound["efficiency_vs_bound"], 1.0)
        self.assertEqual(at_bound["orders_below_bound"], 0.0)

    def test_IB3_above_bound_is_physically_impossible(self):
        out = run(build(), power_w=1.0, bandwidth_bits_per_s=1e9, measured_bits_per_s=2e9)
        self.assertEqual(out["status"], "error")
        self.assertEqual(out.get("field"), "measured_bits_per_s")

    def test_invalid_inputs_are_errors_not_crashes(self):
        for kw in ({}, {"power_w": 0}, {"power_w": -5}, {"power_w": float("inf")},
                   {"power_w": True}, {"power_w": "1"}, {"power_w": 1, "temperature_k": 0},
                   {"power_w": 1, "bandwidth_bits_per_s": -1},
                   {"power_w": 1, "measured_bits_per_s": 0}):
            out = run(build(), **kw)
            self.assertEqual(out["status"], "error", kw)

    def test_IB5_pure_and_deterministic(self):
        core = build()
        asyncio.run(core.process({"action": "record_work", "agent_id": "a", "entry_id": "e1",
                                  "power_w": 10, "duration_s": 1}))
        before = (repr(core._ledgers), repr(core._entry_index), repr(core._inventories))
        a = run(core, power_w=5.0, bandwidth_bits_per_s=1e15, measured_bits_per_s=1e10)
        b = run(core, power_w=5.0, bandwidth_bits_per_s=1e15, measured_bits_per_s=1e10)
        self.assertEqual(a["data"], b["data"])
        self.assertEqual(before, (repr(core._ledgers), repr(core._entry_index),
                                  repr(core._inventories)))

    def test_IB6_honest_caveat_always_present(self):
        d = run(build(), power_w=1.0)["data"]
        self.assertIn("irreversible", d["note"])
        self.assertIn("far below the bound", d["note"])
        self.assertIn("min(rho*B", d["formula"])
        self.assertIn("established physics", d["status"])
        self.assertIn("conjecture, not a proved law", d["status"])


if __name__ == "__main__":
    unittest.main()
