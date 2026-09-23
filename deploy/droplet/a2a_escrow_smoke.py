#!/usr/bin/env python3
"""Live smoke: the a2a escrow payment rail (PG13-PG16), end to end, in prod.

Flow (all against https://mcp.viridisconservation.com):
  1. Exhaust regulatory-radar's free tier (cheapest gated agent, $0.25/call)
     until a payment_required envelope arrives (PG2).
  2. Open + fund a real escrow payable to viridis:regulatory-radar for one
     call's price via /escrow/mcp.
  3. Retry the gated call with payment_ref=<escrow_id> -> must succeed (PG13).
  4. Replay the same payment_ref -> must be refused, no double credit (PG16).
  5. Confirm the escrow is RELEASED and /healthz reports the consumption
     under payment_gate.a2a_escrow (non-cash internal ledger).

Requires VIRIDIS_INTERNAL_SECRET in the environment (classifies this traffic
internal/is_test so it never pollutes external demand stats — G6/PG12).

NOTE: settlement here is a closed-loop internal ledger (PG17 deferred).
Nothing in this smoke represents cash.
"""
import json
import os
import sys
import urllib.request

BASE = "https://mcp.viridisconservation.com"
SECRET = os.environ["VIRIDIS_INTERNAL_SECRET"]
AGENT = "regulatory-radar"
PRICE_MINOR = 25


def call(mount, tool, **args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": args}}).encode()
    req = urllib.request.Request(
        f"{BASE}/{mount}/mcp", data=body,
        headers={"content-type": "application/json",
                 "accept": "application/json, text/event-stream",
                 "x-viridis-internal": SECRET + ":a2a-escrow-smoke"})
    raw = urllib.request.urlopen(req, timeout=35).read().decode()
    data = [l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg = json.loads(data[-1] if data else raw)
    if "error" in msg:
        return {"status": "error", "error_type": "jsonrpc",
                "message": str(msg["error"])[:200]}
    return json.loads(msg["result"]["content"][0]["text"])


def scan(**extra):
    return call(AGENT, "scan_regulations", jurisdiction="EU",
                sector="energy", **extra)


def fail(msg):
    print(f"SMOKE FAIL: {msg}")
    sys.exit(1)


# ---- 1. hit the paywall (PG2) ------------------------------------------
refused = None
for i in range(12):
    r = scan()
    if r.get("error_type") == "payment_required":
        refused = r
        print(f"paywall reached after {i} free call(s) today")
        break
if refused is None:
    fail("never hit payment_required in 12 calls — gate not engaged?")
assert refused["amount_minor"] == PRICE_MINOR, refused["amount_minor"]
assert "payment_ref" in refused["payment"]["a2a"]["note"]

# ---- 2. open + fund a real escrow --------------------------------------
opened = call("escrow", "open_escrow", payer="agent:a2a-smoke",
              payee=f"viridis:{AGENT}", amount_minor=PRICE_MINOR,
              currency="USD", terms="1 regulatory-radar scan (a2a smoke)")
if opened.get("status") != "ok":
    fail(f"escrow open: {opened}")
eid = opened["data"]["escrow_id"]
funded = call("escrow", "fund_escrow", escrow_id=eid,
              payment_ref="a2a-smoke-funding")
if funded["data"]["state"] != "FUNDED":
    fail(f"escrow fund: {funded}")
print(f"escrow {eid} FUNDED for {PRICE_MINOR} minor -> viridis:{AGENT}")

# ---- 3. paid retry (PG13) ----------------------------------------------
paid = scan(payment_ref=eid)
if paid.get("error_type") == "payment_required":
    fail(f"paid call refused: {paid.get('a2a')}")
if paid.get("status") not in ("ok", "success"):
    fail(f"paid call errored: {paid}")
print(f"PG13 OK — escrow-paid call served (status={paid.get('status')})")

# ---- 4. replay (PG16) ---------------------------------------------------
replay = scan(payment_ref=eid)
if replay.get("error_type") != "payment_required":
    fail(f"replayed escrow granted a second call: {replay.get('status')}")
print("PG16 OK — replayed payment_ref refused, no double credit")

# ---- 5. escrow terminal + healthz reporting -----------------------------
status = call("escrow", "escrow_status", escrow_id=eid)
if status["data"]["state"] != "RELEASED":
    fail(f"escrow not RELEASED: {status['data']['state']}")
hz = json.loads(urllib.request.urlopen(
    BASE + "/healthz?smoke=a2a", timeout=20).read().decode())
a2a = hz["payment_gate"].get("a2a_escrow", {})
consumed = a2a.get("consumed", {}).get(AGENT, {})
if not a2a.get("enabled"):
    fail("healthz: a2a_escrow not enabled")
if consumed.get("escrows", 0) < 1:
    fail(f"healthz: consumption not reported: {consumed}")
print(f"escrow RELEASED; healthz a2a_escrow[{AGENT}]: {consumed}")
print("note:", a2a.get("note"))
print("\nA2A ESCROW SMOKE: ALL GREEN (internal ledger — not cash)")
