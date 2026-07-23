"""
x402_http.py — HTTP-402-native surface over the gated tools (H402 invariants).

The bridge from "an agent CAN pay us" to "any off-the-shelf x402 client
finds and pays us with zero custom code". A standard x402 client (the x402
CLI, x402-fetch, x402+requests) GETs the challenge or POSTs a tool's args,
gets a REAL HTTP 402
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
H402-8 DISCOVERY: each shipped endpoint carries a natural-language
       description, input/output schema, exact price, MCP pointer, and the
       v1 outputSchema field CDP Bazaar indexes after a successful settle.
       The settlement adapter binds paymentPayload.resource to the endpoint.
H402-9 BUYER SIGNAL: every new HTTP-v2 settlement durably records its payer,
       route, amount, transaction, timestamp, and allowlist-based self/external
       classification before execution. Pre-instrumentation records are never
       inferred as external, so seed traffic cannot fake the first-dollar flag.
H402-10 INTRO PRICE: when the default-off x402-intro-v1 switch is enabled,
       an unseen signed payer receives one 10000-atomic-USDC call across the
       entire HTTP fleet. The payer is marked seen in the same durable commit
       as the settlement receipt; persistence failure reverts both records.
       A caller may send X402-Payer-Address on the unpaid preflight for an
       exact returning-payer quote, but the signed authorization is always the
       authority and prevents hint spoofing.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

logger = logging.getLogger("viridis.x402_http")

# (agent_path, http_tool_name) -> core action. Extend as tools are exposed.
# Verified mappings only — an entry here makes a real paid endpoint.
X402_HTTP_TOOLS: Dict[Tuple[str, str], str] = {
    ("regulatory-radar", "scan_regulations"): "scan",
    ("taxcredit-engine", "calculate_tax_credit"): "calculate",
    ("ghg-ledger", "calculate_inventory"): "calculate_inventory",
    ("quantity-takeoff", "calculate_takeoff"): "calculate_takeoff",
    ("disclosure-compiler", "compile_disclosure"): "compile_disclosure",
}

AGENT402_FIXED_ROUTE = ("regulatory-radar", "scan_regulations_agent402")
AGENT402_HTTP_TOOLS: Dict[Tuple[str, str], str] = {
    AGENT402_FIXED_ROUTE: "scan",
}

X402_HTTP_METADATA: Dict[Tuple[str, str], dict] = {
    ("regulatory-radar", "scan_regulations"): {
        "description": ("Energy and climate compliance regulation scan across "
                        "a curated 14-regulation database, with jurisdiction, "
                        "urgency, and effective-date signals. The scan step "
                        "pairs with Viridis GHG inventory, sustainability "
                        "disclosure, and clean-energy tax-credit engines."),
        "input_schema": {
            "type": "object",
            "properties": {
                "jurisdiction": {"type": "string", "description": "EU, US, UK, or another supported jurisdiction"},
                "sector": {"type": ["string", "null"]},
            },
            "required": ["jurisdiction"],
        },
        "input_example": {"jurisdiction": "EU", "sector": "energy"},
        "output_example": {"status": "success", "jurisdiction": "EU",
                           "matches": 3, "urgency": "high"},
    },
    ("taxcredit-engine", "calculate_tax_credit"): {
        "description": ("Auditable US clean-energy tax-credit calculator from "
                        "explicit credit-specific facts. The claim step pairs "
                        "with the Viridis GHG inventory and sustainability "
                        "disclosure engines for a chainable compliance workflow."),
        "input_schema": {
            "type": "object",
            "properties": {
                "credit": {"type": "string", "description": "45Q, 45V, 45Y, 48E, or 45X"},
                "facts": {"type": "object", "additionalProperties": True},
            },
            "required": ["credit", "facts"],
        },
        "input_example": {"credit": "45V", "facts": {"tax_year": 2026}},
        "output_example": {"status": "ok", "credit": "45V",
                           "estimated_credit_usd": 125000,
                           "audit_trace": ["eligible production", "tier rate"]},
    },
    ("ghg-ledger", "calculate_inventory"): {
        "description": ("Deterministic greenhouse gas inventory API for "
                        "auditable Scope 1, 2, and 3 accounting from explicit "
                        "activity records. The accounting step pairs with "
                        "Viridis embodied-carbon takeoff, disclosure, and "
                        "tax-credit engines."),
        "input_schema": {
            "type": "object",
            "properties": {
                "activities": {"type": "array", "items": {"type": "object"}},
                "options": {"type": ["object", "null"]},
            },
            "required": ["activities"],
        },
        "input_example": {"activities": []},
        "output_example": {"status": "ok", "total_tco2e": 0,
                           "scope_totals": {"scope_1": 0, "scope_2": 0,
                                            "scope_3": 0}},
    },
    ("quantity-takeoff", "calculate_takeoff"): {
        "description": ("Embodied carbon quantity takeoff from a bill of "
                        "materials or explicit construction geometry, producing "
                        "auditable material quantities for carbon accounting. "
                        "The measure step pairs with the Viridis GHG inventory "
                        "and sustainability disclosure engines."),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array", "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "assembly": {"type": "string"},
                            "unit_system": {"type": "string",
                                            "enum": ["imperial", "SI"]},
                            "dimensions": {"type": "object"},
                        },
                        "required": ["assembly", "unit_system", "dimensions"],
                        "additionalProperties": True,
                    },
                },
                "options": {"type": ["object", "null"]},
            },
            "required": ["items"],
        },
        "input_example": {
            "items": [{
                "id": "slab-1", "assembly": "concrete_slab",
                "unit_system": "imperial",
                "dimensions": {
                    "length": {"value": "20", "unit": "ft"},
                    "width": {"value": "30", "unit": "ft"},
                    "thickness": {"value": "4", "unit": "in"},
                },
            }],
            "options": {"project_id": "buyer-project-1"},
        },
        "output_example": {
            "status": "ok",
            "data": {"takeoff_status": "complete_for_supplied_items",
                     "line_items": [{"assembly": "concrete_slab",
                                     "purchase_qty": "7.78",
                                     "unit": "yd3"}]},
        },
    },
    ("disclosure-compiler", "compile_disclosure"): {
        "description": ("CSRD / IFRS S2 (TCFD-aligned) sustainability "
                        "disclosure compiler from supplied company facts and "
                        "optional verified emissions data. The disclose step "
                        "pairs with Viridis GHG inventory, regulation-scan, and "
                        "clean-energy tax-credit engines."),
        "input_schema": {
            "type": "object",
            "properties": {
                "framework": {"type": "string",
                              "enum": ["esrs-e1", "ifrs-s2",
                                       "sec-climate", "tnfd"]},
                "company_facts": {"type": "object"},
                "ghg_result": {"type": ["object", "null"]},
                "options": {"type": ["object", "null"]},
            },
            "required": ["framework", "company_facts"],
        },
        "input_example": {
            "framework": "esrs-e1",
            "company_facts": {
                "company_name": "Example Climate Works",
                "reporting_period": "2026",
                "transition_plan": {"status": "board-approved",
                                    "target_year": 2035},
                "climate_targets": {"scope": "Scopes 1-3",
                                    "target": "50% by 2035"},
            },
            "options": {
                "applicability": {"framework": "esrs-e1", "applies": True,
                                  "reason": "buyer-supplied applicability",
                                  "source": "buyer"},
            },
        },
        "output_example": {
            "status": "ok",
            "data": {"draft_status": "partial", "framework": "esrs-e1",
                     "filled_datapoints": [], "gaps": [],
                     "audit_sha256": "content-addressed-draft-digest"},
        },
    },
}

# Agent402 native listings advertise one static per-call price.  Keep this
# compatibility alias at Regulatory Radar's $0.25 list price so the amount in
# Agent402's PAYMENT-SIGNATURE always matches the Viridis challenge.  The
# public scan_regulations route retains its one-time $0.01 intro schedule.
X402_HTTP_METADATA[AGENT402_FIXED_ROUTE] = {
    **X402_HTTP_METADATA[("regulatory-radar", "scan_regulations")],
    "service_name": "Viridis Regulatory Radar",
    "category": "Search",
    "icon_url": (
        "https://mcp.viridisconservation.com/brand/viridis-mark.svg"),
    "tags": ["climate", "energy", "compliance", "regulation", "CSRD"],
}
INTRO_EXEMPT_ROUTES = frozenset({AGENT402_FIXED_ROUTE})

OUTPUT_SCHEMA = {"type": "object", "additionalProperties": True}
SETTLEMENT_CLASSIFICATION_VERSION = 1
INTRO_SEEN_KEY = "x402_intro_seen_payers"
INTRO_PAYER_HEADER = "x402-payer-address"
INTRO_SCHEDULE = {
    "version": "x402-intro-v1",
    "price_minor": 1,
    "amount_atomic": "10000",
    "scope": "one successful HTTP x402 v2 settlement per payer wallet",
    "sybil_posture": ("intentionally light friction: wallet-level only; "
                       "no identity collection or cross-wallet linkage"),
}


def intro_enabled() -> bool:
    """Default-off activation flag; no partial or implicit enablement."""
    return os.environ.get("X402_INTRO_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on"}


def _gate_states(cores: Dict[str, Any]) -> Dict[str, dict]:
    """Read gate state without importing payment_gate at module import time."""
    try:
        from payment_gate import GATE_ATTR
    except Exception:
        return {}
    return {name: getattr(core, GATE_ATTR, {})
            for name, core in cores.items()}


def _seen_payers(cores: Dict[str, Any]) -> set:
    """Fleet-wide payer history, including pre-schedule v2 settlements."""
    seen = set()
    for gate in _gate_states(cores).values():
        if not isinstance(gate, dict):
            continue
        recorded = gate.get(INTRO_SEEN_KEY, {})
        if isinstance(recorded, dict):
            seen.update(str(item).strip().lower() for item in recorded if item)
        elif isinstance(recorded, (set, list, tuple)):
            seen.update(str(item).strip().lower() for item in recorded if item)
        for settlement in gate.get("consumed_x402", {}).values():
            if not isinstance(settlement, dict):
                continue
            payer = str(settlement.get("payer_wallet", "")).strip().lower()
            if payer:
                seen.add(payer)
    return seen


def _payer_seen(cores: Dict[str, Any], payer: str) -> bool:
    return bool(payer) and payer.strip().lower() in _seen_payers(cores)


def intro_status(cores: Dict[str, Any]) -> dict:
    """Health-ready policy state; never exposes more than public wallets."""
    return {
        "enabled": intro_enabled(),
        "schedule": dict(INTRO_SCHEDULE),
        "seen_payers": len(_seen_payers(cores)),
        "payer_hint_header": "X402-Payer-Address",
        "note": ("The hint improves preflight quoting only; signed payment "
                 "authorization determines eligibility."),
    }


def _payer_wallet(payload: dict) -> str:
    """Extract the public payer address from the signed v2 authorization."""
    inner = payload.get("payload") if isinstance(payload, dict) else None
    if not isinstance(inner, dict):
        return ""
    authorization = (inner.get("authorization") or
                     inner.get("permit2Authorization"))
    if not isinstance(authorization, dict):
        return ""
    return str(authorization.get("from", "")).strip()


def _self_wallets() -> set:
    """Configured Viridis wallets; empty means every new payer is external."""
    return {item.strip().lower() for item in
            os.environ.get("VIRIDIS_X402_SELF_WALLETS", "").split(",")
            if item.strip()}


def _classified_settlement(payload: dict, agent: str, tool: str,
                           result: dict, identifier: str, *,
                           intro_applied: bool = False,
                           list_price_minor: int | None = None,
                           surface: str = "http-402-v2") -> dict:
    payer = _payer_wallet(payload)
    record = {
        "payment_identifier": identifier,
        "tx_hash": result["tx_hash"],
        "network": result["network"],
        "amount_atomic": result["amount_atomic"],
        "credits": 1,
        "at": time.strftime("%Y-%m-%d", time.gmtime()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "surface": surface,
        "route": f"{agent}/{tool}",
        "payer_wallet": payer,
        "self_settle": payer.lower() in _self_wallets(),
        "classification_version": SETTLEMENT_CLASSIFICATION_VERSION,
        "settlement_receipt": result.get("settlement_receipt"),
        "extension_responses": result.get("extension_responses", {}),
    }
    if intro_enabled():
        record.update({
            "pricing_schedule_version": INTRO_SCHEDULE["version"],
            "intro_price_applied": bool(intro_applied),
            "list_price_minor": list_price_minor,
        })
    return record


def _empty_settlement_metrics() -> dict:
    return {
        "settlements_total": 0,
        "self_settlements": 0,
        "external_settlements": 0,
        "distinct_external_payers": 0,
        "external_revenue_atomic": 0,
        "first_external_settlement": None,
    }


def settlement_metrics(gate_states: Dict[str, dict]) -> dict:
    """Aggregate only versioned records; legacy seeds cannot fake a stranger."""
    routes = {f"{agent}/{tool}": _empty_settlement_metrics()
              for agent, tool in X402_HTTP_TOOLS}
    total = _empty_settlement_metrics()
    payer_sets = {route: set() for route in routes}
    total_payers = set()
    for gate in gate_states.values():
        if not isinstance(gate, dict):
            continue
        for record in gate.get("consumed_x402", {}).values():
            if (not isinstance(record, dict)
                    or record.get("surface") not in {
                        "http-402-v2", "a2a-x402-v2"}
                    or record.get("classification_version")
                    != SETTLEMENT_CLASSIFICATION_VERSION):
                continue
            route = str(record.get("route", ""))
            if route not in routes:
                routes[route] = _empty_settlement_metrics()
                payer_sets[route] = set()
            route_metrics = routes[route]
            for metrics in (route_metrics, total):
                metrics["settlements_total"] += 1
            if record.get("self_settle") is True:
                route_metrics["self_settlements"] += 1
                total["self_settlements"] += 1
                continue
            route_metrics["external_settlements"] += 1
            total["external_settlements"] += 1
            try:
                amount = int(str(record.get("amount_atomic", "0")))
            except (TypeError, ValueError):
                amount = 0
            route_metrics["external_revenue_atomic"] += amount
            total["external_revenue_atomic"] += amount
            payer = str(record.get("payer_wallet", "")).strip().lower()
            if payer:
                payer_sets[route].add(payer)
                total_payers.add(payer)
            first = {"tx_hash": record.get("tx_hash"),
                     "timestamp": record.get("timestamp")}
            for metrics in (route_metrics, total):
                current = metrics["first_external_settlement"]
                if (current is None or str(first["timestamp"] or "")
                        < str(current.get("timestamp") or "")):
                    metrics["first_external_settlement"] = first
    for route, metrics in routes.items():
        metrics["distinct_external_payers"] = len(payer_sets[route])
    total["distinct_external_payers"] = len(total_payers)
    return {"total": total, "per_route": routes}


def discovery_entries(public_base: str) -> list:
    """ARD/health-ready inventory of the payable HTTP front door."""
    from payment_gate import PRICE_MINOR, DEFAULT_PRICE_MINOR
    import x402_rail
    base = public_base.rstrip("/")
    try:
        import x402_v2
        v2_status = x402_v2.status()
    except Exception:
        v2_status = {"requested": False, "enabled": False,
                     "active_protocol": 1,
                     "bazaar_extension_responses": {}}
    entries = []
    for agent, tool in X402_HTTP_TOOLS:
        route_key = f"{agent}/{tool}"
        entries.append({
            "agent": agent,
            "tool": tool,
            "endpoint": f"{base}/x402/{agent}/{tool}",
            "mcp_endpoint": f"{base}/{agent}/mcp",
            "methods": ["GET", "POST"],
            "paid_execution_method": "POST",
            "price_minor": PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR),
            "amount_atomic_usdc": x402_rail.price_atomic(
                PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)),
            "description": X402_HTTP_METADATA[(agent, tool)]["description"],
            "x402_version": v2_status["active_protocol"],
            "v2_enabled": v2_status["enabled"],
            "bazaar_extension_responses":
                v2_status["bazaar_extension_responses"].get(route_key, {}),
        })
    return entries


def _decode_query_value(value: Any) -> Any:
    """GET convenience: JSON-decode objects/arrays/bools/numbers, keep text."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


async def _request_args(request) -> dict:
    if str(getattr(request, "method", "POST")).upper() == "GET":
        query = getattr(request, "query_params", {})
        return {str(k): _decode_query_value(v) for k, v in query.items()}
    try:
        args = await request.json()
    except Exception:
        args = {}
    if not isinstance(args, dict):
        return {}
    return args


def _resp(payload, status=200, headers=None):
    from starlette.responses import JSONResponse
    return JSONResponse(payload, status_code=status, headers=headers or {})


def make_x402_http_route(cores, store, public_base, tools=None):
    """Factory: build the GET/POST /x402/{agent}/{tool} handler, closing over the
    gateway's cores + StateStore. `tools` overrides the registered allowlist
    (test hook). Import-guarded so the gateway still serves if x402 absent."""
    import x402_rail
    from payment_gate import PRICE_MINOR, DEFAULT_PRICE_MINOR, GATE_ATTR
    registry = (tools if tools is not None else
                {**X402_HTTP_TOOLS, **AGENT402_HTTP_TOOLS})

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
        list_price = PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)
        intro_for_route = (intro_enabled()
                           and (agent, tool) not in INTRO_EXEMPT_ROUTES)
        payer_hint = str(request.headers.get(INTRO_PAYER_HEADER, "")).strip()
        price = list_price
        resource = f"{public_base}/x402/{agent}/{tool}"
        # X2-1/X2-7: a separate, default-off v2 lane.  Flag off continues at
        # the byte-stable Wave-6 v1 behavior below; flag on never falls back.
        try:
            import x402_v2
            if x402_v2.requested():
                if not x402_v2.is_enabled():
                    return _resp({"error": "x402 v2 rail disabled or "
                                           "incompletely configured"}, 503)
                price = (INTRO_SCHEDULE["price_minor"]
                         if intro_for_route
                         and not _payer_seen(cores, payer_hint)
                         else list_price)
                meta = X402_HTTP_METADATA[(agent, tool)]
                payment_required = x402_v2.build_payment_required(
                    agent, tool, price, resource,
                    str(getattr(request, "method", "POST")).upper(), meta)
                required_headers = x402_v2.response_headers(payment_required)
                signature = request.headers.get("payment-signature")
                if not signature:
                    body = (payment_required
                            if (agent, tool) == AGENT402_FIXED_ROUTE
                            else {"error": "PAYMENT-SIGNATURE required"})
                    return _resp(body, 402, required_headers)
                payload = x402_v2.parse_header(signature)
                if payload is None:
                    return _resp({"error": "malformed PAYMENT-SIGNATURE"},
                                 402, required_headers)
                payer = _payer_wallet(payload)
                if intro_for_route:
                    if not payer:
                        return _resp({"error": "signed payer address required "
                                              "for intro-price eligibility"},
                                     402, required_headers)
                    expected_price = (list_price if _payer_seen(cores, payer)
                                      else INTRO_SCHEDULE["price_minor"])
                    if expected_price != price:
                        payment_required = x402_v2.build_payment_required(
                            agent, tool, expected_price, resource,
                            str(getattr(request, "method", "POST")).upper(),
                            meta)
                        required_headers = x402_v2.response_headers(
                            payment_required)
                        return _resp({
                            "error": ("intro price already used; retry with "
                                      "the full-price PAYMENT-REQUIRED"
                                      if expected_price == list_price else
                                      "payer is eligible for the intro price; "
                                      "retry with this PAYMENT-REQUIRED"),
                            "pricing_schedule": INTRO_SCHEDULE["version"],
                        }, 402, required_headers)
                gate_state = getattr(core, GATE_ATTR, None)
                inner = getattr(core, "_gate_inner", None)
                if gate_state is None or inner is None:
                    return _resp({"error": "agent is not gated"}, 500)
                identifier = x402_v2.payment_identifier(payload, signature)
                key = "v2:" + hashlib.sha256(identifier.encode()).hexdigest()
                consumed = gate_state.setdefault("consumed_x402", {})
                if key in consumed:
                    prior = consumed[key]
                    replay_headers = x402_v2.settlement_headers({
                        "settled": True,
                        "tx_hash": prior.get("tx_hash", ""),
                        "network": prior.get("network", ""),
                        "settlement_receipt":
                            prior.get("settlement_receipt")})
                    return _resp({"error": "payment already consumed",
                                  "idempotent": True,
                                  "transaction": prior.get("tx_hash")},
                                 402, replay_headers)
                result = x402_v2.verify_and_settle(
                    payload, payment_required, agent, tool)
                if not result.get("settled"):
                    return _resp({"error": "settlement failed: "
                                           f"{result.get('reason')}",
                                  "extension_responses":
                                      result.get("extension_responses", {})},
                                 402, required_headers)
                consumed[key] = _classified_settlement(
                    payload, agent, tool, result, identifier,
                    intro_applied=(intro_for_route and
                                   price == INTRO_SCHEDULE["price_minor"]),
                    list_price_minor=list_price)
                intro_seen = gate_state.get(INTRO_SEEN_KEY, {})
                if intro_for_route and not isinstance(intro_seen, dict):
                    intro_seen = {}
                if intro_for_route and INTRO_SEEN_KEY not in gate_state:
                    gate_state[INTRO_SEEN_KEY] = intro_seen
                seen_key = payer.strip().lower() if intro_for_route else ""
                seen_added = False
                if seen_key and isinstance(intro_seen, dict):
                    seen_added = seen_key not in intro_seen
                    intro_seen[seen_key] = {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "route": f"{agent}/{tool}",
                        "tx_hash": result["tx_hash"],
                        "pricing_schedule_version": INTRO_SCHEDULE["version"],
                    }
                persisted = False
                try:
                    persisted = bool(store.save(agent, core))
                except Exception:
                    logger.critical("x402_v2[%s]: persistence raised after "
                                    "settled tx=%s", agent, result["tx_hash"])
                paid_headers = x402_v2.settlement_headers(result)
                if not persisted:
                    consumed.pop(key, None)
                    if seen_added:
                        intro_seen.pop(seen_key, None)
                    return _resp({"error": "payment settled but durable "
                                           "receipt persistence failed; tool "
                                           "not executed",
                                  "transaction": result["tx_hash"]},
                                 500, paid_headers)
                if not result.get("serve", True):
                    return _resp({"error": result.get("reason"),
                                  "transaction": result["tx_hash"],
                                  "extension_responses":
                                      result.get("extension_responses", {})},
                                 502, paid_headers)
                args = await _request_args(request)
                args = {k: v for k, v in args.items() if k != "action"}
                try:
                    out = inner({"action": action, **args})
                    if asyncio.iscoroutine(out):
                        out = await out
                    try:
                        store.save(agent, core)
                    except Exception:
                        pass
                except Exception as exc:
                    logger.exception("x402_v2[%s]: tool failed after settle",
                                     agent)
                    out = {"status": "error", "error_type": "tool_error",
                           "message": "paid call errored: "
                                      f"{type(exc).__name__} (payment settled; "
                                      "contact support with the transaction)",
                           "tx_hash": result["tx_hash"]}
                return _resp(out, 200, paid_headers)
        except Exception as exc:
            logger.exception("x402 v2 route failed closed")
            return _resp({"error": f"x402 v2 error: {type(exc).__name__}"},
                         500)
        reqs = dict(x402_rail.build_accepts(agent, price, resource))
        meta = X402_HTTP_METADATA.get((agent, tool), {
            "description": f"Viridis {agent} {tool} tool call",
            "input_schema": {"type": "object", "additionalProperties": True},
            "input_example": {},
        })
        reqs["description"] = (f"{meta['description']} MCP pointer: "
                               f"{public_base}/{agent}/mcp tool={tool}")
        # CDP Bazaar's backwards-compatible v1 discovery hook. It indexes
        # this after a successful settle; no dashboard registration exists.
        reqs["outputSchema"] = OUTPUT_SCHEMA
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
        args = await _request_args(request)
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
