"""One-entry adoption contract for external agent builders.

The fleet already exposes many specialist routes. This module deliberately
does not add another agent or payment rail. It turns the existing free value
decision into one stable integration plan: select a relevant route, show the
exact unpaid quote request, name the delivery proof, provide the buyer-feedback
contract, and identify the bounded repeat path.

ADOPT-1 READ ONLY: planning never signs, pays, executes, or persists.
ADOPT-2 ONE ROUTE: callers get one best-fit route, not a catalog dump.
ADOPT-3 LIVE PRICE AUTHORITY: the unpaid HTTP 402 remains authoritative.
ADOPT-4 HUMAN BUDGET: no payment is authorized by this response.
ADOPT-5 OUTCOME LOOP: delivery, usefulness, repeat intent, and settlement stay
        separate facts.
"""
from __future__ import annotations

import json
from typing import Any

from value_decision import build_value_decision


SPEC_VERSION = "viridis-adoption-v1"
ADOPTION_PATH = "/adopt"


def adoption_discovery(public_base: str) -> dict[str, Any]:
    base = public_base.rstrip("/")
    from preflight_watch import discovery as watch_discovery
    return {
        "spec_version": SPEC_VERSION,
        "name": "Viridis agent adoption planner",
        "description": (
            "Select one relevant paid Viridis capability and return its exact "
            "quote, delivery, feedback, and repeat-use integration contract."
        ),
        "endpoint": base + ADOPTION_PATH,
        "methods": ["GET", "POST"],
        "price_minor": 0,
        "state_changing": False,
        "security_change_check": watch_discovery(base),
        "input_schema": {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string", "minLength": 3, "maxLength": 1000,
                },
                "inputs": {"type": "object"},
                "max_price_minor": {
                    "type": ["integer", "null"], "minimum": 0,
                },
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
        "decisions": [
            "READY_FOR_QUOTE", "NEEDS_INPUT", "BUDGET_TOO_LOW", "NO_MATCH",
        ],
        "claim_boundary": (
            "A plan is not a purchase, delivery, usefulness signal, repeat "
            "purchase, subscription, or revenue event."
        ),
    }


def build_adoption_plan(
    public_base: str,
    objective: str,
    *,
    inputs: dict[str, Any] | None = None,
    max_price_minor: int | None = None,
) -> dict[str, Any]:
    base = public_base.rstrip("/")
    route = build_value_decision(
        base,
        objective,
        inputs=inputs,
        max_price_minor=max_price_minor,
    )
    decision_map = {
        "REQUEST_QUOTE": "READY_FOR_QUOTE",
        "NEEDS_INPUT": "NEEDS_INPUT",
        "BUDGET_TOO_LOW": "BUDGET_TOO_LOW",
        "NO_MATCH": "NO_MATCH",
    }
    result = {
        "spec_version": SPEC_VERSION,
        "decision": decision_map.get(route["decision"], route["decision"]),
        "reason": route["reason"],
        "money_moved": False,
        "payment_authorized": False,
        "tool_executed": False,
        "state_persisted": False,
        "route_decision": route,
        "claim_boundary": (
            "This free plan is integration guidance. Only a later settled call "
            "can be payment; only its delivery receipt can be transport proof; "
            "buyer feedback and repeat purchase remain separate events."
        ),
    }
    selected = route.get("selected")
    if not isinstance(selected, dict):
        result["next_action"] = {
            "action": "inspect_catalog_or_refine_objective",
            "catalog": base + "/x402/catalog",
        }
        return result

    supplied = dict(inputs or {})
    from x402_http import repeat_paid_route
    agent, tool = selected["route"].split("/", 1)
    repeat = repeat_paid_route(agent, tool, base)
    result["integration"] = {
        "route": selected["route"],
        "job_to_be_done": selected["value"]["job_to_be_done"],
        "quote_request": {
            "method": "POST",
            "url": selected["endpoint"],
            "headers": {
                "content-type": "application/json",
                "x-viridis-acquisition-source": (
                    "one finite caller-declared integration label"),
            },
            "body": supplied,
            "expected_unpaid_status": 402,
            "authoritative_price_source": "PAYMENT-REQUIRED response",
        },
        "payment_flow": {
            "protocol": "x402-v2-exact",
            "network": "Base mainnet",
            "asset": "USDC",
            "steps": [
                "Fetch the unpaid quote with the exact request body.",
                "Check amount, receiver, network, asset, method, resource, and budget.",
                "Obtain the operator's payment mandate.",
                "Retry once with PAYMENT-SIGNATURE and the unchanged body.",
            ],
            "auto_pay": False,
            "operator_budget_required": True,
        },
        "delivery_contract": {
            "response_field": "viridis_delivery",
            "version": "viridis-paid-delivery-v1",
            "result_digest": "result_sha256",
            "seller_transport_only": True,
            "buyer_acceptance_inferred": False,
            "usefulness_inferred": False,
        },
        "feedback_contract": {
            "endpoint": base + "/x402/feedback",
            "method": "POST",
            "authentication": (
                "one-time feedback_token returned inside viridis_delivery"),
            "required_fields": [
                "feedback_token", "outcome", "would_buy_again",
                "idempotency_key",
            ],
            "outcomes": ["USEFUL", "PARTIALLY_USEFUL", "NOT_USEFUL"],
            "exactly_once": True,
            "independently_verified": False,
        },
        "repeat_contract": repeat,
    }
    if agent == "security-preflight" and tool == "security_preflight":
        from preflight_watch import discovery as watch_discovery
        result["integration"]["change_check"] = watch_discovery(base)
    if result["decision"] == "READY_FOR_QUOTE":
        result["next_action"] = {
            "action": "fetch_unpaid_quote",
            "request": result["integration"]["quote_request"],
            "payment_authorized": False,
        }
    else:
        result["next_action"] = {
            "action": "supply_missing_inputs_or_change_budget",
            "missing_buyer_inputs": selected.get("missing_buyer_inputs", []),
            "payment_authorized": False,
        }
    return result


def make_adoption_route(public_base: str):
    from starlette.responses import JSONResponse

    async def handler(request):
        try:
            if str(getattr(request, "method", "GET")).upper() == "GET":
                payload = dict(getattr(request, "query_params", {}))
                raw_inputs = payload.get("inputs", "{}")
                if isinstance(raw_inputs, str):
                    raw_inputs = json.loads(raw_inputs)
                raw_max = payload.get("max_price_minor")
                if raw_max in {None, "", "null"}:
                    raw_max = None
                elif isinstance(raw_max, str):
                    raw_max = int(raw_max)
                payload["inputs"] = raw_inputs
                payload["max_price_minor"] = raw_max
            else:
                payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("request body must be an object")
            unknown = set(payload) - {
                "objective", "inputs", "max_price_minor",
            }
            if unknown:
                raise ValueError(
                    "unknown fields: " + ", ".join(sorted(unknown)))
            return JSONResponse(build_adoption_plan(
                public_base,
                payload.get("objective"),
                inputs=payload.get("inputs"),
                max_price_minor=payload.get("max_price_minor"),
            ))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return JSONResponse({
                "spec_version": SPEC_VERSION,
                "decision": "INVALID_REQUEST",
                "error": str(exc),
                "money_moved": False,
                "payment_authorized": False,
                "tool_executed": False,
            }, status_code=400)

    return handler


def make_adoption_discovery_route(public_base: str):
    from starlette.responses import JSONResponse

    async def handler(_request):
        return JSONResponse(adoption_discovery(public_base))

    return handler
