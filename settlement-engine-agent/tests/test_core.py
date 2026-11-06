"""settlement-engine-agent tests — one or more per invariant S1–S10, plus the arithmetic."""
import asyncio
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.core import (build, canon, sha256_hex, published_aggregate, required_remainder, decided, bounds_aggregate,  # noqa: E402
                      verify_settlement_record, MAX_STRIKES)

SRC = "a" * 64


def run(agent, **payload):
    return asyncio.get_event_loop().run_until_complete(agent.process(payload))


def obs(slot, value, src=SRC, at="2026-11-03T12:00:00Z"):
    return {"slot": slot, "value": value, "source_url": "https://example.org/doc", "source_sha256": src, "observed_at": at}


def ercot_series(agent, n=8, strikes=(30, 35), vmin=-251, vmax=5000):
    r = run(agent, action="register_series", name="ERCOT North weekly RT avg", unit="$/MWh", aggregate="mean", n_expected=n,
            value_min=vmin, value_max=vmax, source="https://www.ercot.com/mp/data-products/np6-905-cd",
            period_start="2026-11-03T00:00:00-06:00", period_end="2026-11-10T00:00:00-06:00", strikes=list(strikes))
    assert r["ok"], r
    return r["series_id"]


class Arithmetic(unittest.TestCase):
    def test_required_remainder_mean(self):
        vals = [Decimal(40)] * 4                      # 4 of 8 published at 40; strike 30 -> remainder must average 20
        self.assertEqual(required_remainder("mean", Decimal(30), vals, 8), Decimal(20))

    def test_required_remainder_sum_and_share(self):
        self.assertEqual(required_remainder("sum", Decimal(100), [Decimal(30), Decimal(30)], 4), Decimal(40))
        # share: 10 slots, strike 0.8 -> 8 hits needed; 5 published with 4 hits -> remaining 5 must hit at 0.8
        self.assertEqual(required_remainder("share", Decimal("0.8"), [Decimal(1)] * 4 + [Decimal(0)], 10), Decimal("0.8"))

    def test_decided_yes_by_bounds(self):          # S5
        vals = [Decimal(100)] * 6                     # 6 of 8 at 100; min -251: worst = (600 - 502)/8 = 12.25 > 10 -> YES at 10
        self.assertEqual(decided("mean", Decimal(10), vals, 8, Decimal(-251), Decimal(5000))[0], "YES")
        self.assertIsNone(decided("mean", Decimal(13), vals, 8, Decimal(-251), Decimal(5000))[0])   # worst 12.25 <= 13

    def test_decided_no_by_bounds(self):
        vals = [Decimal(0)] * 7                       # 7 of 8 at 0; max 5000: best = 625 -> NO at strike 700
        self.assertEqual(decided("mean", Decimal(700), vals, 8, Decimal(-251), Decimal(5000))[0], "NO")

    def test_no_bounds_means_undecided_until_complete(self):   # S5
        vals = [Decimal(100)] * 7
        self.assertIsNone(decided("mean", Decimal(1), vals, 8, None, None)[0])
        self.assertEqual(decided("mean", Decimal(1), vals + [Decimal(100)], 8, None, None)[0], "YES")

    def test_complete_period_strict_above(self):
        self.assertEqual(decided("mean", Decimal(30), [Decimal(30)] * 2, 2, None, None)[0], "NO")   # equal is not above

    def test_share_bounds(self):
        vals = [Decimal(1)] * 9                       # 9 of 10 survived; strike 0.8: worst 0.9 > 0.8 -> YES
        self.assertEqual(decided("share", Decimal("0.8"), vals, 10, None, None)[0], "YES")


class Agent(unittest.TestCase):
    def setUp(self):
        self.a = build()

    def test_never_raises_and_errors_teach(self):           # S6
        for bad in (None, 3, "x", {}, {"action": "nope"}, {"action": "_a_ingest"}, {"action": "ingest", "series_id": 5}):
            r = run(self.a, **(bad if isinstance(bad, dict) else {"action": bad}))
            self.assertFalse(r["ok"]); self.assertIn("fix", r["error"])

    def test_register_validates(self):
        r = run(self.a, action="register_series", name="x", unit="u", source="s", n_expected=0, period_start="2026-01-01T00:00:00Z",
                period_end="2026-01-02T00:00:00Z")
        self.assertEqual(r["error"]["code"], "bad_n_expected")
        r = run(self.a, action="register_series", name="x", unit="u", source="s", n_expected=2, period_start="2026-01-02T00:00:00Z",
                period_end="2026-01-01T00:00:00Z")
        self.assertEqual(r["error"]["code"], "bad_period")
        r = run(self.a, action="register_series", name="x", unit="u", source="s", n_expected=2, period_start="2026-01-01T00:00:00Z",
                period_end="2026-01-02T00:00:00Z", strikes=[1] * (MAX_STRIKES + 1))
        self.assertEqual(r["error"]["code"], "bad_strikes")

    def test_register_idempotent(self):
        s1, s2 = ercot_series(self.a), ercot_series(self.a)
        self.assertEqual(s1, s2); self.assertEqual(len(self.a.store.series), 1)

    def test_ingest_evidence_and_bounds(self):              # S4, S9
        sid = ercot_series(self.a)
        r = run(self.a, action="ingest", series_id=sid, observations=[obs("t1", 31.5), obs("t2", 99999), {"slot": "t3", "value": 1},
                                                                       obs("t4", "abc"), obs("t5", 20, src="zz")])
        self.assertEqual(r["added"], 1); self.assertEqual(len(r["rejected"]), 4)
        self.assertEqual(self.a.store.series[sid].obs["t1"]["obs_sha256"], sha256_hex(canon({k: v for k, v in self.a.store.series[sid].obs["t1"].items() if k != "obs_sha256"})))

    def test_revisions_visible(self):                       # S7
        sid = ercot_series(self.a)
        run(self.a, action="ingest", series_id=sid, observations=[obs("t1", 30)])
        h1 = self.a.store.series[sid].head
        r = run(self.a, action="ingest", series_id=sid, observations=[obs("t1", 30)])        # identical re-post
        self.assertEqual((r["added"], r["replaced"]), (0, 0)); self.assertEqual(self.a.store.series[sid].head, h1)
        r = run(self.a, action="ingest", series_id=sid, observations=[obs("t1", 31)])        # correction
        self.assertEqual(r["replaced"], 1); self.assertNotEqual(self.a.store.series[sid].head, h1)
        st = run(self.a, action="period_status", series_id=sid)
        self.assertEqual(st["facts"]["revisions"], 1); self.assertEqual(st["facts"]["published_aggregate"], "31.000000")

    def test_status_facts_vs_model(self):                   # S1
        sid = ercot_series(self.a, n=8, strikes=(10, 30, 1400))
        run(self.a, action="ingest", series_id=sid, observations=[obs(f"t{i}", 100 + i) for i in range(6)])
        st = run(self.a, action="period_status", series_id=sid)
        rows = {r["strike"]: r for r in st["strikes"]}
        self.assertEqual(rows["10"]["decided"], "YES"); self.assertEqual(rows["1400"]["decided"], "NO"); self.assertIsNone(rows["30"]["decided"])
        self.assertIn("version", rows["30"]["model"]); self.assertIsNotNone(rows["30"]["model"]["p"])
        self.assertEqual(st["facts"]["published_share"], "0.7500")
        # the model is absent from every "facts" block
        self.assertNotIn("p", st["facts"])

    def test_determinism(self):                             # S2
        a1, a2 = build(), build()
        for a in (a1, a2):
            sid = ercot_series(a)
            run(a, action="ingest", series_id=sid, observations=[obs(f"t{i}", 30 + i) for i in range(5)])
        self.assertEqual(canon(run(a1, action="period_status", series_id=sid)), canon(run(a2, action="period_status", series_id=sid)))

    def test_required_remainder_action_and_explain(self):
        sid = ercot_series(self.a)
        run(self.a, action="ingest", series_id=sid, observations=[obs(f"t{i}", 40) for i in range(4)])
        r = run(self.a, action="required_remainder", series_id=sid, strike=30)
        self.assertEqual(r["facts"]["required_remainder"], "20.000000"); self.assertIsNone(r["facts"]["decided"])
        e = run(self.a, action="explain", series_id=sid)["explanation"]
        self.assertIn("4 of 8", e); self.assertIn("20.000000", e); self.assertIn("never decide", e)

    def test_decided_strikes_across_series(self):
        s1 = ercot_series(self.a, strikes=(10,)); s2 = ercot_series(self.a, strikes=(2000,), n=4)
        run(self.a, action="ingest", series_id=s1, observations=[obs(f"t{i}", 100) for i in range(6)])
        run(self.a, action="ingest", series_id=s2, observations=[obs(f"t{i}", 0) for i in range(3)])
        r = run(self.a, action="decided_strikes")
        self.assertEqual({(x["series_id"], x["decided"]) for x in r["decided"]}, {(s1, "YES"), (s2, "NO")})

    def test_contract_settle_verify_roundtrip(self):        # S8, S10
        sid = ercot_series(self.a)
        c = run(self.a, action="compile_contract", series_id=sid, strike=30, rule="above", closes_at="2026-11-10T06:00:00Z",
                parties={"buyer": "X", "verifier": "Viridis"})
        self.assertTrue(c["ok"]); cid = c["contract_id"]
        self.assertEqual(run(self.a, action="compile_contract", series_id=sid, strike=30, rule="above", closes_at="2026-11-10T06:00:00Z",
                             parties={"buyer": "X", "verifier": "Viridis"})["existing"], True)
        # nothing published, before closure -> UNDECIDED
        r = run(self.a, action="settle_contract", contract_id=cid, now="2026-11-05T00:00:00Z")
        self.assertEqual(r["result"], "UNDECIDED")
        # closed but incomplete and undecided -> UNDECIDED (never a guess)
        run(self.a, action="ingest", series_id=sid, observations=[obs("t0", 31)])
        r = run(self.a, action="settle_contract", contract_id=cid, now="2026-11-11T00:00:00Z")
        self.assertEqual(r["result"], "UNDECIDED"); self.assertIn("never a guess", r["basis"])
        # complete -> settles; verify matches; tamper -> mismatch
        run(self.a, action="ingest", series_id=sid, observations=[obs(f"t{i}", 31) for i in range(1, 8)])
        r = run(self.a, action="settle_contract", contract_id=cid, now="2026-11-11T00:00:00Z")
        self.assertEqual(r["result"], "YES"); self.assertEqual(len(r["settlement"]["evidence"]), 8)
        v = run(self.a, action="verify_settlement", settlement_id=r["settlement_id"])
        self.assertTrue(v["match"])
        bad = json.loads(json.dumps(r["settlement"])); bad["result"] = "NO"
        self.assertFalse(verify_settlement_record(bad)["match"])
        bad = json.loads(json.dumps(r["settlement"])); bad["evidence"][0]["value"] = "0"
        self.assertFalse(verify_settlement_record(bad)["match"])

    def test_decided_before_closure_settles(self):          # S10 + S5
        sid = ercot_series(self.a, strikes=(10,))
        cid = run(self.a, action="compile_contract", series_id=sid, strike=10, rule="above", closes_at="2026-11-10T06:00:00Z")["contract_id"]
        run(self.a, action="ingest", series_id=sid, observations=[obs(f"t{i}", 100) for i in range(6)])
        r = run(self.a, action="settle_contract", contract_id=cid, now="2026-11-05T00:00:00Z")
        self.assertEqual(r["result"], "YES"); self.assertIn("declared minimum", r["basis"])
        self.assertTrue(run(self.a, action="verify_settlement", settlement_id=r["settlement_id"])["match"])

    def test_rules_translate(self):
        sid = ercot_series(self.a)
        run(self.a, action="ingest", series_id=sid, observations=[obs(f"t{i}", 30) for i in range(8)])   # complete, mean exactly 30
        for rule, want in (("above", "NO"), ("at_or_above", "YES"), ("below", "NO"), ("at_or_below", "YES")):
            cid = run(self.a, action="compile_contract", series_id=sid, strike=30, rule=rule, closes_at="2026-11-10T06:00:00Z")["contract_id"]
            r = run(self.a, action="settle_contract", contract_id=cid, now="2026-11-11T00:00:00Z")
            self.assertEqual(r["result"], want, rule)
            self.assertTrue(run(self.a, action="verify_settlement", settlement_id=r["settlement_id"])["match"], rule)

    def test_settlement_immutable_and_model_free(self):     # S8, S1
        sid = ercot_series(self.a)
        cid = run(self.a, action="compile_contract", series_id=sid, strike=30, rule="above", closes_at="2026-11-10T06:00:00Z")["contract_id"]
        run(self.a, action="ingest", series_id=sid, observations=[obs(f"t{i}", 31) for i in range(8)])
        r1 = run(self.a, action="settle_contract", contract_id=cid, now="2026-11-11T00:00:00Z")
        r2 = run(self.a, action="settle_contract", contract_id=cid, now="2026-11-11T00:00:00Z")
        self.assertEqual(r1["settlement_id"], r2["settlement_id"]); self.assertEqual(len(self.a.store.settlements), 1)
        self.assertNotIn('"p":', canon(r1["settlement"])); self.assertNotIn("model", {k for k in r1["settlement"] if k != "model_version_note"})

    def test_restoration_share_series(self):                 # the circular lane: survival count as a settled series
        r = run(self.a, action="register_series", name="Moretown riparian planting survival, year 1", unit="survived (0/1)", aggregate="share",
                n_expected=10, source="https://vergecommon.com/d-score/plot-7", period_start="2026-05-01T00:00:00Z", period_end="2027-05-01T00:00:00Z",
                strikes=[0.8])
        sid = r["series_id"]
        run(self.a, action="ingest", series_id=sid, observations=[obs(f"tree{i}", 1) for i in range(9)])
        st = run(self.a, action="period_status", series_id=sid)
        self.assertEqual(st["strikes"][0]["decided"], "YES")        # 9/10 already > 0.8 whatever the last tree does
        cid = run(self.a, action="compile_contract", series_id=sid, strike=0.8, rule="above", closes_at="2027-05-01T00:00:00Z",
                  parties={"buyer": "watershed fund", "steward": "coop", "verifier": "Viridis D-Score"})["contract_id"]
        s = run(self.a, action="settle_contract", contract_id=cid, now="2026-11-06T00:00:00Z")
        self.assertEqual(s["result"], "YES")
        self.assertTrue(run(self.a, action="verify_settlement", settlement=s["settlement"])["match"])

    def test_health_describe(self):
        h = asyncio.get_event_loop().run_until_complete(self.a.health())
        self.assertTrue(h["ok"]); self.assertIn("S5 decided means decided", self.a.describe()["invariants"])


class Boundaries(unittest.TestCase):
    """Equality edges of S5 and each check of S8 on its own."""

    def test_worst_equal_to_strike_is_undecided(self):
        vals = [Decimal(100)] * 6                 # worst = (600 + 2*-251)/8 = 12.25 exactly
        self.assertIsNone(decided("mean", Decimal("12.25"), vals, 8, Decimal(-251), Decimal(5000))[0])
        self.assertEqual(decided("mean", Decimal("12.24"), vals, 8, Decimal(-251), Decimal(5000))[0], "YES")

    def test_best_equal_to_strike_is_no(self):
        vals = [Decimal(0)] * 7                   # best = 5000/8 = 625 exactly: can at most equal, never exceed
        self.assertEqual(decided("mean", Decimal(625), vals, 8, Decimal(-251), Decimal(5000))[0], "NO")
        self.assertIsNone(decided("mean", Decimal("624.99"), vals, 8, Decimal(-251), Decimal(5000))[0])

    def test_share_best_case_counts_remaining_hits(self):
        vals = [Decimal(1)] * 7 + [Decimal(0)] * 0   # 7 of 10 hit, 3 remaining: best 1.0, worst 0.7 -> strike 0.75 undecided
        self.assertIsNone(decided("share", Decimal("0.75"), vals, 10, None, None)[0])
        self.assertEqual(bounds_aggregate("share", vals, 10, Decimal(1)), Decimal(1))

    def _settled(self):
        a = build(); sid = ercot_series(a)
        cid = run(a, action="compile_contract", series_id=sid, strike=30, rule="above", closes_at="2026-11-10T06:00:00Z")["contract_id"]
        run(a, action="ingest", series_id=sid, observations=[obs(f"t{i}", 31) for i in range(8)])
        return a, run(a, action="settle_contract", contract_id=cid, now="2026-11-11T00:00:00Z")

    def test_verify_each_check_separately(self):
        a, r = self._settled(); rec = r["settlement"]
        def rehash(x):
            y = {k: v for k, v in x.items() if k != "settlement_sha256"}; x["settlement_sha256"] = sha256_hex(canon(y)); return x
        t = json.loads(json.dumps(rec)); t["settlement_sha256"] = "0" * 64
        v = verify_settlement_record(t); self.assertFalse(v["hash_ok"]); self.assertTrue(v["aggregate_ok"]); self.assertTrue(v["result_ok"])
        t = rehash(dict(json.loads(json.dumps(rec)), published_aggregate="99.000000"))
        v = verify_settlement_record(t); self.assertTrue(v["hash_ok"]); self.assertFalse(v["aggregate_ok"]); self.assertFalse(v["match"])
        t = rehash(dict(json.loads(json.dumps(rec)), result="NO"))
        v = verify_settlement_record(t); self.assertTrue(v["hash_ok"]); self.assertTrue(v["aggregate_ok"]); self.assertFalse(v["result_ok"])

    def test_settlement_record_is_never_overwritten(self):
        a, r = self._settled(); sid = r["settlement_id"]
        a.store.settlements[sid]["marker"] = "first"
        run(a, action="settle_contract", contract_id=r["settlement"]["contract_id"], now="2026-11-11T00:00:00Z")
        self.assertEqual(a.store.settlements[sid].get("marker"), "first")


if __name__ == "__main__":
    unittest.main()
