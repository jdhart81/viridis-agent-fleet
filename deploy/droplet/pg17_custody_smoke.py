#!/usr/bin/env python3
"""Live smoke: PG17 escrow custody bridge — fail-closed proof, no card.

1. Open a real escrow payable to viridis:regulatory-radar ($0.25).
2. escrow_checkout -> real Stripe Checkout session + URL (EC1).
3. confirm_escrow_funding WITHOUT paying -> must refuse not_paid (EC2) and
   the escrow must still be OPEN (never funded on ambiguity).
4. settlement_instruction on the unfunded escrow -> not_custody_funded.
5. healthz reports the escrow_custody section with pending checkout.

The positive path (pay the URL, confirm, spend via payment_ref, see
cash_minor in reconcile_revenue) requires a real card — Justin can run it
end-to-end for $0.25 whenever he wants the first live cash escrow.
"""
import json
import os
import sys
import urllib.request

BASE = "https://mcp.viridisconservation.com"
SECRET = os.environ["VIRIDIS_INTERNAL_SECRET"]


def call(mount, tool, **args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": args}}).encode()
    req = urllib.request.Request(
        f"{BASE}/{mount}/mcp", data=body,
        headers={"content-type": "application/json",
                 "accept": "application/json, text/event-stream",
                 "x-viridis-internal": SECRET + ":pg17-custody-smoke"})
    raw = urllib.request.urlopen(req, timeout=35).read().decode()
    data = [l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg = json.loads(data[-1] if data else raw)
    if "error" in msg:
        return {"status": "error", "error_type": "jsonrpc",
                "message": str(msg["error"])[:200]}
    return json.loads(msg["result"]["content"][0]["text"])


def fail(msg):
    print(f"SMOKE FAIL: {msg}")
    sys.exit(1)


# $1.00 = 4 prepaid regulatory-radar credits (Stripe minimum charge is
# $0.50, so a single 25-minor escrow can't be cash-funded — batch prepay).
opened = call("escrow", "open_escrow", payer="agent:pg17-smoke",
              payee="viridis:regulatory-radar", amount_minor=100,
              currency="USD", terms="pg17 custody smoke — 4 prepaid scans")
if opened.get("status") != "ok":
    fail(f"open: {opened}")
eid = opened["data"]["escrow_id"]
print("escrow opened:", eid)

co = call("payments", "escrow_checkout", escrow_id=eid)
if co.get("status") != "ok":
    fail(f"escrow_checkout: {co}")
if not str(co.get("url", "")).startswith("https://checkout.stripe.com"):
    fail(f"no hosted checkout url: {co}")
print(f"EC1 OK — real checkout {co['session_id']} for {co['amount_minor']} "
      f"minor (livemode={co.get('livemode')})")

unpaid = call("payments", "confirm_escrow_funding", escrow_id=eid)
if unpaid.get("error_type") != "not_paid":
    fail(f"unpaid session was not refused: {unpaid}")
esc = call("escrow", "escrow_status", escrow_id=eid)
if esc["data"]["state"] != "OPEN":
    fail(f"escrow mutated without payment: {esc['data']['state']}")
print("EC2 OK — unpaid session refused fail-closed; escrow still OPEN")

inst = call("payments", "escrow_settlement_instruction", escrow_id=eid)
if inst.get("error_type") != "not_custody_funded":
    fail(f"instruction issued without cash: {inst}")
print("EC5/PG17 OK — no cash, no settlement paperwork")

hz = json.loads(urllib.request.urlopen(
    BASE + "/healthz?smoke=pg17", timeout=20).read().decode())
cust = hz.get("escrow_custody")
if not cust or cust.get("pending_checkouts", 0) < 1:
    fail(f"healthz custody section missing/empty: {cust}")
print("healthz escrow_custody:", {k: cust[k] for k in
      ("cash_funded_escrows", "cash_funded_minor", "pending_checkouts")})
print("note:", cust.get("note"))
print("\nPG17 CUSTODY SMOKE: ALL GREEN (fail-closed proven; positive path "
      "awaits a real $1.00 payment by Justin = 4 prepaid scans)")
print("pay-to-complete URL:", co["url"])
