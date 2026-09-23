#!/usr/bin/env python3
"""Claim the live Viridis x402 catalog and place one escrow-backed bid."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


EXPECTED_AUTH = "activate-payanagent-channel-viridis-fleet"
ENV_FILE = Path("/root/viridis-fleet/.env.payanagent")
BASE_URL = "https://payanagent.com"
MANIFEST_URL = "https://mcp.viridisconservation.com/.well-known/x402"
PAY_TO = "0xfEf2e570b645EB720Ee6c589d27450810982f329"
REQUEST_ID = "ks76vc9pzpz3qfgf8aawjckn5n8bezhf"
REQUEST_TITLE = "Build a catalog endpoint-health checker (find dead ecosystem sellers)"

ROUTES: dict[str, dict[str, Any]] = {
    "regulatory-radar/scan_regulations": {
        "title": "Viridis Regulatory Radar — Compliance Scan",
        "category": "Climate Compliance",
        "tags": ["regulatory", "climate", "compliance", "audit", "x402"],
        "input": 'JSON body: {"jurisdiction":"US","sector":"energy","query":"optional text"}. jurisdiction is required.',
    },
    "regulatory-radar/monitor_changes": {
        "title": "Viridis Regulatory Watch — Deadline Monitor",
        "category": "Climate Compliance",
        "tags": ["regulatory", "monitoring", "deadlines", "climate", "x402"],
        "input": 'JSON body: {"jurisdiction":"US","topics":["emissions"],"lookback_days":90}. jurisdiction is required.',
        "verification_query": "?jurisdiction=US",
    },
    "taxcredit-engine/calculate_tax_credit": {
        "title": "Viridis Clean-Energy Tax Credit Calculator",
        "category": "Climate Finance",
        "tags": ["tax-credit", "clean-energy", "45v", "45q", "audit"],
        "input": 'JSON body: {"credit":"45V","facts":{"tax_year":2026}}. credit and facts are required; supports 45Q, 45V, 45Y, 48E, and 45X.',
    },
    "ghg-ledger/calculate_inventory": {
        "title": "Viridis Auditable GHG Inventory",
        "category": "Climate Accounting",
        "tags": ["ghg", "scope-1", "scope-2", "scope-3", "audit"],
        "input": 'JSON body: {"activities":[...],"options":null}. activities is required.',
    },
    "quantity-takeoff/calculate_takeoff": {
        "title": "Viridis Embodied-Carbon Quantity Takeoff",
        "category": "Construction Climate",
        "tags": ["quantity-takeoff", "embodied-carbon", "construction", "audit"],
        "input": 'JSON body: {"items":[{"id":"slab-1","assembly":"concrete_slab","unit_system":"imperial","dimensions":{...}}],"options":null}. items is required.',
    },
    "disclosure-compiler/compile_disclosure": {
        "title": "Viridis Sustainability Disclosure Compiler",
        "category": "Climate Disclosure",
        "tags": ["csrd", "ifrs-s2", "tcfd", "disclosure", "audit"],
        "input": 'JSON body: {"framework":"esrs-e1","company_facts":{...},"ghg_result":null,"options":null}. framework and company_facts are required.',
    },
    "hive/solve": {
        "title": "Viridis Audited Multi-Agent Solve",
        "category": "Agent Compute",
        "tags": ["multi-agent", "cross-review", "audit", "escrow", "x402"],
        "input": 'JSON body: {"problem":"...","budget_minor":500,"subtasks":[...],"depth":0,"redundancy":2,"accept_threshold":0.6,"seed":0,"fee_bps":0}. problem and budget_minor are required.',
        "verification_query": "?problem=bounded%20review&budget_minor=500",
    },
    "security-preflight/security_preflight": {
        "title": "Viridis MCP Agent Security Preflight",
        "category": "Agent Security",
        "tags": ["mcp", "security", "policy", "injection", "attestation"],
        "input": 'JSON body: {"agent_id":"lowercase-id","manifest":{...},"policy":null,"sample_inputs":null}. agent_id and manifest are required.',
        "verification_query": "?agent_id=viridis-probe&manifest=%7B%7D",
    },
}

PUBLISH_ROUTES = (
    "regulatory-radar/monitor_changes",
    "hive/solve",
    "security-preflight/security_preflight",
)


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        if raw and not raw.startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            result[key] = value
    return result


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Accept": "application/json", "User-Agent": "Viridis-Agent-Fleet/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        try:
            error_body = json.loads(exc.read())
        except Exception:
            error_body = {"error": str(exc)}
        return exc.code, error_body


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.chmod(temp_path, 0o600)
    temp_path.replace(path)


def main() -> int:
    if sys.argv[1:] != [EXPECTED_AUTH]:
        raise SystemExit("refusing: exact PayanAgent channel authorization is required")
    if not ENV_FILE.is_file() or ENV_FILE.stat().st_mode & 0o077:
        raise SystemExit("refusing: PayanAgent credential file is missing or too permissive")

    env = read_env(ENV_FILE)
    agent_id = env.get("PAYANAGENT_AGENT_ID", "")
    api_key = env.get("PAYANAGENT_API_KEY", "")
    wallet = env.get("PAYANAGENT_WALLET_ADDRESS", "")
    if not agent_id or not api_key.startswith("pk_") or wallet.lower() != PAY_TO.lower():
        raise SystemExit("refusing: invalid PayanAgent seller credential binding")

    manifest_status, manifest = request_json(MANIFEST_URL)
    if manifest_status != 200:
        raise SystemExit(f"refusing: live manifest returned HTTP {manifest_status}")
    live_routes = {
        f"{route['agent']}/{route['tool']}": route for route in manifest.get("routes", [])
    }
    if set(ROUTES) != set(live_routes):
        raise SystemExit("refusing: live paid-route set differs from the approved eight-route catalog")

    registered: list[dict[str, Any]] = []
    for route_key in PUBLISH_ROUTES:
        listing = ROUTES[route_key]
        live = live_routes[route_key]
        expected_endpoint = f"https://mcp.viridisconservation.com/x402/{route_key}"
        if live.get("endpoint") != expected_endpoint or live.get("paid_execution_method") != "POST":
            raise SystemExit(f"refusing: unexpected live route contract for {route_key}")
        external_url = expected_endpoint + listing["verification_query"]
        payload = {
            "title": listing["title"],
            "description": live["description"]
            + " Successful paid responses include the viridis-paid-delivery-v1 delivery contract.",
            "category": listing["category"],
            "tags": listing["tags"],
            "offerType": "api",
            "externalUrl": external_url,
            "httpMethod": "GET",
            "inputSchema": listing["input"],
            "outputSchema": "JSON response with deterministic result data and viridis-paid-delivery-v1 receipt metadata after successful settlement.",
            "estimatedDurationSeconds": 30,
            "previewDescription": "Non-custodial Base USDC x402 route. The listing uses a schema-valid GET ownership preflight; buyers send the documented JSON body by POST. Authoritative payment terms come from the live HTTP 402 challenge.",
        }
        status, response = request_json(
            f"{BASE_URL}/api/v1/offers", method="POST", payload=payload, api_key=api_key
        )
        if status != 201 or response.get("mode") != "relay":
            error = response.get("error", "offer registration failed")
            raise SystemExit(f"refusing: {route_key} registration failed ({status}: {error})")
        verified = response.get("verified") or {}
        if str(verified.get("payTo", "")).lower() != PAY_TO.lower():
            raise SystemExit(f"refusing: {route_key} verified a different receiving wallet")
        registered.append(
            {
                "route": route_key,
                "paid_execution_endpoint": expected_endpoint,
                "ownership_preflight_url": external_url,
                "offer_id": response["offerId"],
                "buy_url": f"{BASE_URL}{response['buyUrl']}",
                "amount_atomic_usdc": str(verified.get("amountRaw", "")),
                "network": verified.get("network"),
                "mode": "relay",
            }
        )

    request_status, request_detail = request_json(
        f"{BASE_URL}/api/v1/requests/{REQUEST_ID}"
    )
    request_row = request_detail.get("request") or {}
    if (
        request_status != 200
        or request_row.get("title") != REQUEST_TITLE
        or request_row.get("status") != "open"
        or request_row.get("escrow") is not True
        or request_row.get("escrowDepositedCents") != 4
        or request_row.get("budgetMaxCents") != 4
    ):
        raise SystemExit("refusing: target PayanAgent request is not the expected open funded job")

    bid_payload = {
        "priceCents": 4,
        "estimatedDurationSeconds": 300,
        "message": (
            "Viridis Agent Fleet will deliver a dependency-free Node 22 checker, a validated "
            "top-100 JSON report, and a concise Markdown failure summary. It will use only "
            "bounded unauthenticated HEAD/OPTIONS probes, send no payment headers, make no paid "
            "calls, treat HTTP 402 as a reachable payment gate, and label the public buyUrl as "
            "the measured surface rather than overclaiming downstream seller health. Ready to "
            "fulfill within five minutes after acceptance."
        ),
    }
    bid_status, bid_response = request_json(
        f"{BASE_URL}/api/v1/requests/{REQUEST_ID}/bid",
        method="POST",
        payload=bid_payload,
        api_key=api_key,
    )
    if bid_status != 201 or not bid_response.get("bidId"):
        error = bid_response.get("error", "bid submission failed")
        raise SystemExit(f"refusing: bid submission failed ({bid_status}: {error})")

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence_path = Path(
        f"/root/viridis-fleet/payanagent-evidence/{run_id}/channel-activation.json"
    )
    evidence = {
        "run_id": run_id,
        "seller_agent_id": agent_id,
        "receiving_wallet": wallet,
        "offers": registered,
        "offer_count": len(registered),
        "bid": {
            "request_id": REQUEST_ID,
            "bid_id": bid_response["bidId"],
            "price_cents": 4,
            "escrow_deposited_cents": 4,
            "status": "pending_buyer_acceptance",
        },
        "revenue_boundary": "No revenue until an independent buyer accepts, approves, and settlement plus paid delivery are both verified.",
    }
    atomic_json(evidence_path, evidence)
    print(
        json.dumps(
            {
                "status": "activated",
                "seller_agent_id": agent_id,
                "offer_count": len(registered),
                "bid_id": bid_response["bidId"],
                "bid_status": "pending_buyer_acceptance",
                "evidence_path": str(evidence_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
