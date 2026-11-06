#!/usr/bin/env python3
"""
The circular lane, end to end on one planting: a pay-for-success restoration milestone settled on a survival count.

A watershed fund pays a neighborhood coop (VergeCommon) on the verified outcome "at least 80% of the 120 planted
riparian stems alive at month 12", verified by Viridis (D-Score field record). Each stem is one slot (0 dead / 1 alive)
and the aggregate is the share. The published part is the stems already surveyed this round. The strike is decided the
moment the arithmetic says the remaining stems cannot change the answer - before the survey is complete - and the
settlement lists every field record hash it used, so the fund (or anyone) can recompute it.

  python3 examples/restoration_survival.py examples/restoration_survival_sample.csv
CSV columns: stem_id, alive(0/1), record_url, record_sha256, observed_at
"""
import asyncio
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core import build  # noqa: E402


def main(path: str):
    rows = list(csv.DictReader(open(path)))
    obs = [{"slot": r["stem_id"], "value": int(r["alive"]), "source_url": r["record_url"], "source_sha256": r["record_sha256"],
            "observed_at": r["observed_at"]} for r in rows]
    a = build()
    P = lambda **p: asyncio.run(a.process(p))  # noqa: E731
    sid = P(action="register_series", name="Mad River riparian planting - stems alive at month 12", unit="alive (0/1)", aggregate="share",
            n_expected=120, source="https://vergecommon.com/d-score/mad-river-plot-3", period_start="2026-05-01T00:00:00Z",
            period_end="2027-05-01T00:00:00Z", strikes=[0.8], meta={"stems_planted": 120, "verifier": "Viridis D-Score"})["series_id"]
    cid = P(action="compile_contract", series_id=sid, strike=0.8, rule="above", closes_at="2027-05-15T00:00:00Z",
            parties={"buyer": "Mad River Watershed Fund", "steward": "VergeCommon coop", "verifier": "Viridis LLC"},
            terms="Pays $9,600 on YES; verification fee $480 (5%) to the verifier on any settlement; UNDECIDED re-settles after the full survey.")["contract_id"]
    ing = P(action="ingest", series_id=sid, observations=obs)
    st = P(action="period_status", series_id=sid)
    s = P(action="settle_contract", contract_id=cid, now="2026-11-06T00:00:00Z")
    v = P(action="verify_settlement", settlement_id=s["settlement_id"])
    print(json.dumps({"series_id": sid, "contract_id": cid, "ingest": {k: ing[k] for k in ("added", "rejected", "published")},
                      "facts": st["facts"], "strike": st["strikes"][0], "explanation": P(action="explain", series_id=sid)["explanation"],
                      "settlement": {"result": s["result"], "basis": s["basis"], "evidence_hashes": len(s["settlement"]["evidence"]),
                                     "settlement_id": s["settlement_id"]}, "verify": v}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).with_name("restoration_survival_sample.csv")))
