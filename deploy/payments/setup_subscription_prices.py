#!/usr/bin/env python3
"""
setup_subscription_prices.py — unblock the seats funnel (checkout_ready: 0).

Found 2026-07-15: the seats front door had 2 accounts + 5 page views but
checkout_ready_plans == 0 — every would-be buyer dead-ends at the last click
because no plan has a Stripe Price. This script closes that gap as pure data:

  1. For each plan in the catalog, ensure a Stripe Product + recurring Price
     exist (idempotent: keyed on metadata.viridis_plan_id + amount + interval;
     re-running NEVER creates duplicates).
  2. Emit plan_catalog.v0.3.0.json with stripe_price_id filled and — only
     with --approve — approval_status="approved", checkout_enabled=true.
  3. Print the deploy line: docker cp the new catalog + set
     VIRIDIS_PLAN_CATALOG=<container path> (loader override added 2026-07-15).

Run ON a machine holding the Stripe key (droplet or Justin's):
  STRIPE_API_KEY=rk_live_... python3 setup_subscription_prices.py            # dry-run
  STRIPE_API_KEY=rk_live_... python3 setup_subscription_prices.py --apply
  STRIPE_API_KEY=rk_live_... python3 setup_subscription_prices.py --apply --approve

--- INVARIANTS ---
SP1  Dry-run by default: no Stripe mutation without --apply.
SP2  Idempotent: an existing active Price with matching
     metadata.viridis_plan_id, unit_amount, currency and interval is reused.
SP3  Catalog integrity: the emitted catalog changes ONLY stripe_price_id,
     approval_status, checkout_enabled, pack_version, effective_as_of —
     prices, coverage, quotas and lifecycle policy are byte-preserved.
SP4  approval_status/checkout_enabled flip ONLY with --approve (owner gate).
SP5  The key is never printed; errors are scrubbed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

STRIPE = "https://api.stripe.com/v1"


def _scrub(msg: object, key: str) -> str:
    return str(msg).replace(key, "***")[:400]


def _req(method: str, path: str, key: str, params: dict | None = None) -> dict:
    data = urllib.parse.urlencode(params or {}, doseq=True).encode() \
        if method == "POST" else None
    url = f"{STRIPE}/{path}"
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec - fixed host
        return json.loads(resp.read().decode())


def find_existing_price(key: str, plan: dict, currency: str,
                        _req=_req) -> str | None:
    """SP2: reuse an active recurring Price tagged with this plan id."""
    listing = _req("GET", "prices", key,
                   {"limit": 100, "active": "true", "type": "recurring"})
    for p in listing.get("data", []):
        md = p.get("metadata") or {}
        rec = p.get("recurring") or {}
        if (md.get("viridis_plan_id") == plan["id"]
                and p.get("unit_amount") == plan["price_minor"]
                and p.get("currency") == currency
                and rec.get("interval") == plan["interval"]):
            return p["id"]
    return None


def ensure_price(key: str, plan: dict, currency: str, apply: bool,
                 _req=_req) -> tuple[str | None, str]:
    existing = find_existing_price(key, plan, currency, _req=_req)
    if existing:
        return existing, "reused"
    if not apply:
        return None, "would-create (dry-run)"
    product = _req("POST", "products", key, {
        "name": f"Viridis {plan['name']}",
        "metadata[viridis_plan_id]": plan["id"],
        "metadata[covered_agents]": ",".join(plan["covered_agents"]),
    })
    price = _req("POST", "prices", key, {
        "product": product["id"],
        "unit_amount": plan["price_minor"],
        "currency": currency,
        "recurring[interval]": plan["interval"],
        "metadata[viridis_plan_id]": plan["id"],
    })
    return price["id"], "created"


def build_catalog(catalog: dict, price_ids: dict, approve: bool) -> dict:
    """SP3/SP4: data-only transformation of the catalog."""
    out = json.loads(json.dumps(catalog))          # deep copy
    out["pack_version"] = "0.3.0"
    out["effective_as_of"] = date.today().isoformat()
    for plan in out["plans"]:
        pid = price_ids.get(plan["id"])
        if pid:
            plan["stripe_price_id"] = pid
            if approve:
                plan["approval_status"] = "approved"
                plan["checkout_enabled"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="create missing Stripe objects (SP1)")
    ap.add_argument("--approve", action="store_true", help="flip approval/checkout flags (SP4)")
    ap.add_argument("--catalog", default=None, help="input catalog path")
    args = ap.parse_args()

    key = os.environ.get("STRIPE_API_KEY", "")
    if not key:
        print("STRIPE_API_KEY not set — aborting (nothing attempted).")
        return 2

    here = Path(__file__).resolve()
    default_cat = (here.parents[2] / "subscriptions-agent" / "data" /
                   "plan_catalog.v0.2.0.json")
    cat_path = Path(args.catalog) if args.catalog else default_cat
    catalog = json.loads(cat_path.read_text())
    currency = catalog.get("currency", "usd")

    price_ids, report = {}, []
    for plan in catalog["plans"]:
        try:
            pid, how = ensure_price(key, plan, currency, args.apply)
        except Exception as e:                      # SP5
            report.append((plan["id"], "ERROR", _scrub(e, key)))
            continue
        if pid:
            price_ids[plan["id"]] = pid
        report.append((plan["id"], how, pid or "-"))

    for pid_, how, val in report:
        print(f"  {pid_:<18} {how:<24} {val}")

    if not args.apply:
        print("\nDry-run complete (SP1). Re-run with --apply to create.")
        return 0

    out = build_catalog(catalog, price_ids, args.approve)
    out_path = cat_path.parent / "plan_catalog.v0.3.0.json"
    out_path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nWrote {out_path}")
    if not args.approve:
        print("Flags NOT flipped (SP4) — re-run with --approve, or approve by hand.")
    print("\nDeploy (droplet):")
    print("  docker cp plan_catalog.v0.3.0.json <gateway>:/app/subscriptions-agent/data/")
    print("  add env VIRIDIS_PLAN_CATALOG=/app/subscriptions-agent/data/plan_catalog.v0.3.0.json")
    print("  restart gateway; verify /healthz checkout_ready_plans == number of approved plans")
    return 0


if __name__ == "__main__":
    sys.exit(main())
