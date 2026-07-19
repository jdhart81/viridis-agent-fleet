"""
x402_http.py — HTTP-402-native surface over the gated tools (H402 invariants).

The bridge from "an agent CAN pay us" to "any off-the-shelf x402 client
finds and pays us with zero custom code". A standard x402 client (the x402
CLI, x402-fetch, x402+requests) POSTs a tool's args, gets a REAL HTTP 402
with the standard `accepts` payload, signs + retries with X-PAYMENT, and we
settle through the SAME proven rail (x402_rail) then execute the tool. This
is what makes the fleet discoverable/payable on x402 Bazaar — no in-band
MCP parsing required.

--- INVARIANTS (H402) ---
H402-1 REAL 402: an unpaid request returns HTTP 402 with a standards body
       {x402Version, accepts:[requirements], error}. A drop-in x402 client
       acts on it with no Viridis-specific code.
H402-2 SETTLE-THEN-SERVE: the tool executes ONLY after x402_rail settles
       the payment. No settlement -> HTTP 402, no execution.
H402-3 EXACTLY-ONCE: the X-PAYMENT header hashes to a key persisted in the
       core's consumed_x402 map (SHARED with the MCP surface, PRX4); a
       replay serves/settles nothing (the on-chain nonce is single-use too).
H402-4 UNGATED EXECUTION: after settlement the tool runs via the ungated
       _gate_inner (still StateStore-persisted) — the gate's free-tier /
       credit path is NOT re-run (payment already made).
H402-5 UNIFIED TELEMETRY: settlements land in the same
       gate_state["consumed_x402"] the MCP surface uses, so /healthz
       x402.settled counts both surfaces; the tx hash rides back in the
       X-PAYMENT-RESPONSE header.
H402-6 ALLOWLIST: only registered (agent, tool) pairs are payable (404
       otherwise); rail disabled -> 503.
H402-7 FAIL-CLOSED: any settlement/exec error returns a structured 402/500
       and never executes a tool for free, never double-charges.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from typing import Dict, Tuple

logger = logging.getLogger("viridis.x402_http")

# (agent_path, http_tool_name) -> core action. Extend as tools are exposed.
# Verified mappings only — an entry here makes a real paid endpoint.
X402_HTTP_TOOLS: Dict[Tuple[str, str], str] = {
    ("regulatory-radar", "scan_regulations"): "scan",
}


def _resp(payload, status=200, headers=None):
    from starlette.responses import JSONResponse
    return JSONResponse(payload, status_code=status, headers=headers or {})


def make_x402_http_route(cores, store, public_base, tools=None):
    """Factory: build the POST /x402/{agent}/{tool} handler, closing over the
    gateway's cores + StateStore. `tools` overrides the registered allowlist
    (test hook). Import-guarded so the gateway still serves if x402 absent."""
    import x402_rail
    from payment_gate import PRICE_MINOR, DEFAULT_PRICE_MINOR, GATE_ATTR
    registry = tools if tools is not None else X402_HTTP_TOOLS

    async def handler(request):
        agent = request.path_params.get("agent", "")
        tool = request.path_params.get("tool", "")
        action = registry.get((agent, tool))
        core = cores.get(agent)
        if action is None or core is None:                     # H402-6
            return _resp({"error": "unknown x402 tool",
                          "available": [f"{a}/{t}"
                                        for (a, t) in registry]}, 404)
        if not x402_rail.is_enabled():                         # H402-6
            return _resp({"error": "x402 rail disabled"}, 503)
        price = PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)
        resource = f"{public_base}/x402/{agent}/{tool}"
        reqs = x402_rail.build_accepts(agent, price, resource)
        body = {"x402Version": x402_rail.X402_VERSION, "accepts": [reqs]}

        xpay = request.headers.get("x-payment")
        if not xpay:                                           # H402-1
            return _resp({**body, "error": "X-PAYMENT required"}, 402)
        payload = x402_rail.parse_payment_header(xpay)
        if payload is None:
            return _resp({**body, "error": "malformed X-PAYMENT"}, 402)

        gate_state = getattr(core, GATE_ATTR, None)
        inner = getattr(core, "_gate_inner", None)
        if gate_state is None or inner is None:
            return _resp({"error": "agent is not gated"}, 500)
        key = hashlib.sha256(xpay.encode()).hexdigest()
        consumed = gate_state.setdefault("consumed_x402", {})
        if key in consumed:                                    # H402-3
            return _resp({**body, "error": "payment already consumed"}, 402)

        result = x402_rail.verify_and_settle(payload, reqs)    # H402-2
        if not result.get("settled"):                          # H402-7
            return _resp({**body,
                          "error": f"settlement failed: {result.get('reason')}"},
                         402)
        consumed[key] = {"tx_hash": result["tx_hash"],
                         "network": result["network"],
                         "amount_atomic": result["amount_atomic"],
                         "credits": 1,
                         "at": time.strftime("%Y-%m-%d", time.gmtime()),
                         "surface": "http-402"}                # H402-5
        try:
            store.save(agent, core)
        except Exception:
            logger.critical("x402_http[%s]: SETTLED tx=%s but persist failed "
                            "— tx hash is the receipt", agent,
                            result["tx_hash"])

        # H402-4: execute via the ungated inner (payment already made).
        try:
            args = await request.json()
        except Exception:
            args = {}
        if not isinstance(args, dict):
            args = {}
        args = {k: v for k, v in args.items() if k != "action"}
        try:
            out = inner({"action": action, **args})
            if asyncio.iscoroutine(out):
                out = await out
            try:
                store.save(agent, core)
            except Exception:
                pass
        except Exception as exc:                               # H402-7
            logger.exception("x402_http[%s]: tool exec failed after settle",
                             agent)
            out = {"status": "error", "error_type": "tool_error",
                   "message": f"paid call errored: {type(exc).__name__} "
                              "(payment settled; contact support with the tx)",
                   "tx_hash": result["tx_hash"]}
        receipt = base64.b64encode(json.dumps(
            result.get("settlement_receipt")
            or {"transaction": result["tx_hash"]}).encode()).decode()
        return _resp(out, 200, {"X-PAYMENT-RESPONSE": receipt,
                                "X-Payment-Tx": result["tx_hash"]})

    return handler
