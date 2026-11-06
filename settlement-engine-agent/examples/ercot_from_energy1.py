#!/usr/bin/env python3
"""
Ingestion adapter: ERCOT real-time settlement point prices from the ENERGY-1 store (Viridis research droplet,
/opt/energy1/state/energy1.sqlite, table spp(hub, ts, price), 15-minute intervals in America/Chicago) into
settlement-engine series — one series per hub per Kalshi contract period.

Usage (read-only on the store):
  python3 examples/ercot_from_energy1.py --db /opt/energy1/state/energy1.sqlite --hub HB_NORTH \
      --start 2026-11-03T00:00 --end 2026-11-10T00:00 --strikes 25,30,35,40 [--emit observations.json]

The adapter is the only place that touches a data source; the core receives observations as data (S3/S4).
source_sha256 here is the sha256 of the canonical (hub, ts, price, listing URL) row from the ENERGY-1 store, which
persists ERCOT's NP6-905-CD documents; a per-document hash can replace it when the store records one.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core import build, canon  # noqa: E402

LISTING = "https://www.ercot.com/mp/data-products/data-product-details?id=NP6-905-CD"
SPP_MIN, SPP_MAX = -251.0, 5000.0          # ERCOT's price floor and system-wide offer cap


def n_intervals(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 900)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True); ap.add_argument("--hub", default="HB_NORTH")
    ap.add_argument("--start", required=True); ap.add_argument("--end", required=True)
    ap.add_argument("--strikes", default="25,30,35,40"); ap.add_argument("--emit", default=None)
    a = ap.parse_args()
    start, end = datetime.fromisoformat(a.start), datetime.fromisoformat(a.end)
    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    rows = db.execute("select hub, ts, price from spp where hub=? and ts>=? and ts<? order by ts", (a.hub, a.start, a.end)).fetchall()
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    obs = []
    for hub, ts, price in rows:
        row = {"hub": hub, "ts": ts, "price": price, "listing": LISTING}
        obs.append({"slot": ts, "value": price, "source_url": LISTING, "source_sha256": hashlib.sha256(canon(row).encode()).hexdigest(),
                    "observed_at": now})
    agent = build()
    import asyncio
    reg = asyncio.run(agent.process({"action": "register_series", "name": f"ERCOT {a.hub} RT avg {a.start}..{a.end}", "unit": "$/MWh",
                                     "aggregate": "mean", "n_expected": n_intervals(start, end), "source": LISTING,
                                     "period_start": a.start + "-06:00", "period_end": a.end + "-06:00",
                                     "strikes": [float(x) for x in a.strikes.split(",")], "value_min": SPP_MIN, "value_max": SPP_MAX,
                                     "meta": {"adapter": "ercot_from_energy1", "interval_s": 900, "tz": "America/Chicago"}}))
    sid = reg["series_id"]
    ing = asyncio.run(agent.process({"action": "ingest", "series_id": sid, "observations": obs}))
    st = asyncio.run(agent.process({"action": "period_status", "series_id": sid}))
    ex = asyncio.run(agent.process({"action": "explain", "series_id": sid}))
    print(json.dumps({"series_id": sid, "ingest": {k: ing[k] for k in ("added", "replaced", "published", "n_expected")},
                      "facts": st["facts"], "strikes": st["strikes"], "explanation": ex["explanation"]}, indent=1))
    if a.emit:
        Path(a.emit).write_text(json.dumps({"series": reg["series"], "observations": obs}, indent=1))


if __name__ == "__main__":
    main()
