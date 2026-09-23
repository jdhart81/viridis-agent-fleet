#!/usr/bin/env python3
"""Fail-closed verifier for the two Regulatory Radar wedge candidates.

Gateway mode reads only loopback HTTP surfaces. Growth mode is offline: it
validates a captured one-cycle JSON result and the copied audit database
digest. Neither mode can send a message, invoke a model, sign a payment, or
call a paid route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any


INTRO_ENABLED = (
    "First paid call from every new wallet on eligible carbon/compliance "
    "routes is $0.01 USDC; Hive stays at its fixed $5.00 price and "
    "subsequent eligible calls use the unchanged list price."
)
INTRO_DISABLED = "Intro pricing is currently disabled; list prices apply."
GROWTH_INTRO_ENABLED = "First paid call from a new wallet is $0.01."
REPEAT_BUYER_CTA = (
    "Returning buyer? Put your public signing address in "
    "X402-Payer-Address on the unpaid preflight to receive the exact "
    "returning-wallet quote the first time. The hint never authorizes "
    "payment—never send a private key."
)
EXPECTED_ROUTE_PRICES = {
    "quantity-takeoff": "$0.50",
    "ghg-ledger": "$1.00",
    "disclosure-compiler": "$2.00",
    "taxcredit-engine": "$2.00",
    "regulatory-radar": "$0.25",
    "hive": "$5.00",
}
EXPECTED_PRICE_SET = {
    "$0.01", "$0.25", "$0.50", "$1.00", "$2.00", "$5.00",
}
PROOF_RE = re.compile(
    r"Live external proof: ([1-9][0-9]*) settlement\(s\) from "
    r"([1-9][0-9]*) distinct payer\(s\)\."
)
BAZAAR_MERCHANT_URL = (
    "https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant"
    "?payTo=0xfEf2e570b645EB720Ee6c589d27450810982f329"
)
STALE_BAZAAR_CLAIMS = (
    "Every live route was indexed",
    "The five deterministic carbon/compliance routes are settlement-indexed",
    "All five routes are settlement-indexed",
)


class ProbeFailure(RuntimeError):
    """A release invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def _request(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/json,text/html",
            "user-agent": "viridis-regulatory-radar-wedge-probe/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, response.read()


def get_json(base: str, path: str) -> dict[str, Any]:
    status, raw = _request(base + path)
    require(status == 200, f"{path} returned HTTP {status}")
    payload = json.loads(raw)
    require(isinstance(payload, dict), f"{path} did not return an object")
    return payload


def get_text(base: str, path: str) -> str:
    status, raw = _request(base + path)
    require(status == 200, f"{path} returned HTTP {status}")
    return raw.decode("utf-8")


def _loopback(base: str) -> bool:
    return (
        base.startswith("http://127.0.0.1:")
        or base.startswith("http://localhost:")
    )


def _require_bazaar_claims(name: str, page: str) -> None:
    require(
        BAZAAR_MERCHANT_URL in page,
        f"{name} omits the live Bazaar inventory link",
    )
    require(
        "authoritative" in page and "currently indexes" in page
        or "authoritative current list" in page,
        f"{name} does not make live Bazaar inventory authoritative",
    )
    require(
        "Hive can become Bazaar-indexed only after its first successful "
        "buyer settlement." in page,
        f"{name} omits the Hive settlement-indexing boundary",
    )
    for stale in STALE_BAZAAR_CLAIMS:
        require(stale not in page, f"{name} contains stale Bazaar claim")


def _require_repeat_machine_surface(name: str, surface: str) -> None:
    require(
        "--route regulatory-radar --max-payment-usdc 0.25" in surface,
        f"{name} omits the returning-buyer $0.25 ceiling",
    )
    require(
        "exactly one new paid attempt" in surface,
        f"{name} omits the one-attempt repeat boundary",
    )
    require(
        "authorize any later purchase" in surface,
        f"{name} grants or omits later-purchase authority",
    )


def probe_gateway(base: str, intro_state: str) -> dict[str, Any]:
    require(_loopback(base), "gateway probe refuses non-loopback URLs")
    health = get_json(base, "/healthz")
    require(health.get("status") == "ok", "gateway health is not ok")
    require(health.get("mount_errors") == {}, "gateway has mount errors")
    persistence = health.get("persistence", {})
    require(persistence.get("available") is True, "persistence unavailable")
    require(persistence.get("errors") == {}, "persistence has errors")
    agents = health.get("agents", {})
    require(isinstance(agents, dict), "health agents is not an object")
    require(len(agents) == 27, f"expected 27 agents, found {len(agents)}")

    x402 = health.get("payment_gate", {}).get("x402", {})
    require(x402.get("enabled") is False, "candidate payment rail is enabled")
    require(x402.get("errors") == {}, "candidate payment rail has errors")
    routes = x402.get("http_front_door", [])
    radar = [
        item for item in routes
        if item.get("agent") == "regulatory-radar"
        and item.get("tool") == "scan_regulations"
    ]
    require(len(radar) == 1, "Regulatory Radar route is missing or duplicated")
    require(
        str(radar[0].get("amount_atomic_usdc")) == "250000",
        "Regulatory Radar list price is not $0.25",
    )

    agents_page = get_text(base, "/agents")
    quickstart = get_text(base, "/quickstart")
    llms = get_text(base, "/llms.txt")
    buyer_skill = get_text(
        base, "/.well-known/skills/viridis-paid-tools/SKILL.md")
    expected_intro = (
        INTRO_ENABLED if intro_state == "enabled" else INTRO_DISABLED
    )
    for name, page in (
        ("agents", agents_page),
        ("quickstart", quickstart),
        ("llms", llms),
    ):
        require("{{INTRO_STATUS}}" not in page, f"{name} has raw placeholder")
        require(expected_intro in page, f"{name} intro state is wrong")
    for name, page in (("agents", agents_page), ("quickstart", quickstart)):
        _require_bazaar_claims(name, page)
    _require_repeat_machine_surface("llms", llms)
    _require_repeat_machine_surface("buyer skill", buyer_skill)
    require(
        "Start here · Regulatory Radar" in agents_page,
        "agents page does not lead with Regulatory Radar",
    )
    require(
        "The live unpaid 402 is authoritative" in agents_page,
        "agents page omits authoritative-quote boundary",
    )
    require(
        "A repeat is never automatic" in agents_page,
        "agents page omits explicit repeat authorization",
    )
    require(
        'href="/quickstart#radar-first-call"' in agents_page,
        "agents page does not link to the bounded first call",
    )
    require(
        'href="/quickstart#radar-repeat-call"' in agents_page,
        "agents page does not link to the bounded repeat call",
    )
    require(
        "Recommended first purchase" in quickstart,
        "quickstart does not lead with the recommended purchase",
    )
    require(
        "fresh unsigned quote" in quickstart,
        "quickstart omits the fresh quote",
    )
    require(
        "Viridis never treats a prior purchase as permission to spend again."
        in quickstart,
        "quickstart omits the no-recurring-authority boundary",
    )
    require(
        'id="official-client"' in quickstart,
        "quickstart paid-client anchor is missing",
    )
    require(
        'id="radar-repeat-call"' in quickstart,
        "quickstart repeat-client anchor is missing",
    )
    require(
        "--route regulatory-radar --max-payment-usdc 0.25" in quickstart,
        "quickstart omits the returning-buyer $0.25 ceiling",
    )
    require(
        "This is exactly one new paid attempt." in quickstart
        and "authorize any later purchase" in quickstart,
        "quickstart omits bounded repeat-attempt authority",
    )
    require(
        ".card code{display:block;overflow-wrap:anywhere;"
        "word-break:break-word}" in quickstart,
        "quickstart endpoint cards are not overflow-safe",
    )
    return {
        "status": "ok",
        "mode": "gateway",
        "base": base,
        "agent_count": len(agents),
        "payment_enabled": False,
        "intro_state": intro_state,
        "radar_amount_atomic_usdc": 250000,
        "pages": {
            "agents": "ok",
            "quickstart": "ok",
            "llms": "ok",
            "buyer_skill": "ok",
        },
        "state_mutation": "expected_metering_only_checked_by_runbook",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_growth(
    result_path: Path,
    state_db: Path,
    expected_state_sha256: str,
    minimum_external_settlements: int,
    minimum_distinct_payers: int,
) -> dict[str, Any]:
    require(result_path.is_file(), "growth result file is missing")
    require(state_db.is_file(), "growth copied-state database is missing")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    require(isinstance(result, dict), "growth result is not an object")
    require(result.get("status") == "dry_run", "growth cycle is not dry-run")
    require(result.get("enabled") is True, "growth worker was not enabled")
    require(
        result.get("send_attempted") is False,
        "growth cycle attempted an outbound send",
    )
    require(
        result.get("model")
        == {"mode": "deterministic", "reason": "dry_run_no_api"},
        "growth cycle did not prove dry-run/no-model mode",
    )
    target = result.get("target")
    require(isinstance(target, dict), "growth result has no target decision")
    require(
        target.get("policy_cleared") is True,
        "growth target is not policy-cleared",
    )

    content = result.get("content")
    require(isinstance(content, str), "growth content is not text")
    require(
        content.startswith(
            "Start here: Regulatory Radar — one bounded x402 compliance "
            "scan on Base."
        ),
        "growth content does not lead with the bounded wedge",
    )
    require(
        "the quote is authoritative for this buyer." in content,
        "growth content omits authoritative quote language",
    )
    for route, price in EXPECTED_ROUTE_PRICES.items():
        require(
            f"• {route} — {price}" in content,
            f"growth content omitted {route} at {price}",
        )
    require(
        GROWTH_INTRO_ENABLED in content,
        "growth content omitted active intro",
    )
    require(REPEAT_BUYER_CTA in content, "growth content omitted repeat CTA")
    require(
        "https://mcp.viridisconservation.com/quickstart" in content,
        "growth content omitted quickstart URL",
    )
    require(
        "https://mcp.viridisconservation.com/agents" in content,
        "growth content omitted agent-suite URL",
    )
    found_prices = set(re.findall(r"\$[0-9]+\.[0-9]{2}", content))
    require(
        found_prices == EXPECTED_PRICE_SET,
        f"growth content price set changed: {sorted(found_prices)}",
    )
    proof = PROOF_RE.search(content)
    require(proof is not None, "growth content omitted live external proof")
    settlements, payers = (int(proof.group(1)), int(proof.group(2)))
    require(
        settlements >= minimum_external_settlements,
        "external settlement proof regressed",
    )
    require(
        payers >= minimum_distinct_payers,
        "distinct payer proof regressed",
    )
    require(payers <= settlements, "distinct payers exceed settlements")

    actual_state_sha256 = _sha256(state_db)
    require(
        re.fullmatch(r"[0-9a-f]{64}", expected_state_sha256) is not None,
        "expected state SHA-256 is malformed",
    )
    require(
        actual_state_sha256 == expected_state_sha256,
        "growth copied-state database changed",
    )
    return {
        "status": "ok",
        "mode": "growth",
        "send_attempted": False,
        "model_called": False,
        "external_settlements": settlements,
        "distinct_external_payers": payers,
        "state_sha256": actual_state_sha256,
        "target_id": target.get("id"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)

    gateway = subparsers.add_parser("gateway")
    gateway.add_argument("--base", default="http://127.0.0.1:18402")
    gateway.add_argument(
        "--intro-state", choices=("enabled", "disabled"), required=True,
    )

    growth = subparsers.add_parser("growth")
    growth.add_argument("--result", type=Path, required=True)
    growth.add_argument("--state-db", type=Path, required=True)
    growth.add_argument("--expected-state-sha256", required=True)
    growth.add_argument("--minimum-external-settlements", type=int, default=3)
    growth.add_argument("--minimum-distinct-payers", type=int, default=3)

    args = parser.parse_args()
    try:
        if args.mode == "gateway":
            result = probe_gateway(args.base.rstrip("/"), args.intro_state)
        else:
            require(
                args.minimum_external_settlements >= 0,
                "minimum settlements cannot be negative",
            )
            require(
                args.minimum_distinct_payers >= 0,
                "minimum payers cannot be negative",
            )
            result = probe_growth(
                args.result,
                args.state_db,
                args.expected_state_sha256,
                args.minimum_external_settlements,
                args.minimum_distinct_payers,
            )
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "mode": args.mode,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
