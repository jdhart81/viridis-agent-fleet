#!/usr/bin/env python3
"""Read-only public-edge verifier for the Regulatory Radar gateway wedge.

This probe is deliberately separate from the non-serving candidate probe.
It accepts exactly the Viridis production HTTPS origin, requires the live
payment rail to remain enabled, and verifies that all four buyer instruction
surfaces reached the public edge. It has no write, payment, or model path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any

try:
    from deploy.droplet import regulatory_radar_wedge_probe as contract
except ImportError:  # Standalone execution beside the pinned candidate probe.
    import regulatory_radar_wedge_probe as contract


PUBLIC_GATEWAY_BASE = "https://mcp.viridisconservation.com"


def _surface_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def probe_public_gateway(
    base: str,
    intro_state: str,
) -> dict[str, Any]:
    contract.require(
        base == PUBLIC_GATEWAY_BASE,
        "public probe refuses every origin except the exact Viridis HTTPS "
        "gateway",
    )
    health = contract.get_json(base, "/healthz")
    contract.require(health.get("status") == "ok", "gateway health is not ok")
    contract.require(health.get("mount_errors") == {}, "gateway has mount errors")
    persistence = health.get("persistence", {})
    contract.require(
        persistence.get("available") is True,
        "persistence unavailable",
    )
    contract.require(
        persistence.get("errors") == {},
        "persistence has errors",
    )
    agents = health.get("agents", {})
    contract.require(
        isinstance(agents, dict),
        "health agents is not an object",
    )
    contract.require(
        len(agents) == 27,
        f"expected 27 agents, found {len(agents)}",
    )

    x402 = health.get("payment_gate", {}).get("x402", {})
    contract.require(
        x402.get("enabled") is True,
        "public payment rail is not enabled",
    )
    contract.require(
        x402.get("errors") == {},
        "public payment rail has errors",
    )
    routes = x402.get("http_front_door", [])
    radar = [
        item for item in routes
        if item.get("agent") == "regulatory-radar"
        and item.get("tool") == "scan_regulations"
    ]
    contract.require(
        len(radar) == 1,
        "Regulatory Radar route is missing or duplicated",
    )
    contract.require(
        str(radar[0].get("amount_atomic_usdc")) == "250000",
        "Regulatory Radar list price is not $0.25",
    )

    surfaces = {
        "agents": contract.get_text(base, "/agents"),
        "quickstart": contract.get_text(base, "/quickstart"),
        "llms": contract.get_text(base, "/llms.txt"),
        "buyer_skill": contract.get_text(
            base,
            "/.well-known/skills/viridis-paid-tools/SKILL.md",
        ),
    }
    expected_intro = (
        contract.INTRO_ENABLED
        if intro_state == "enabled"
        else contract.INTRO_DISABLED
    )
    for name in ("agents", "quickstart", "llms"):
        page = surfaces[name]
        contract.require(
            "{{INTRO_STATUS}}" not in page,
            f"{name} has raw placeholder",
        )
        contract.require(
            expected_intro in page,
            f"{name} intro state is wrong",
        )
    for name in ("agents", "quickstart"):
        contract._require_bazaar_claims(name, surfaces[name])
    contract._require_repeat_machine_surface("llms", surfaces["llms"])
    contract._require_repeat_machine_surface(
        "buyer skill",
        surfaces["buyer_skill"],
    )

    agents_page = surfaces["agents"]
    quickstart = surfaces["quickstart"]
    contract.require(
        "Start here · Regulatory Radar" in agents_page,
        "agents page does not lead with Regulatory Radar",
    )
    contract.require(
        "The live unpaid 402 is authoritative" in agents_page,
        "agents page omits authoritative-quote boundary",
    )
    contract.require(
        "A repeat is never automatic" in agents_page,
        "agents page omits explicit repeat authorization",
    )
    contract.require(
        'href="/quickstart#radar-first-call"' in agents_page,
        "agents page does not link to the bounded first call",
    )
    contract.require(
        'href="/quickstart#radar-repeat-call"' in agents_page,
        "agents page does not link to the bounded repeat call",
    )
    contract.require(
        "Recommended first purchase" in quickstart,
        "quickstart does not lead with the recommended purchase",
    )
    contract.require(
        "fresh unsigned quote" in quickstart,
        "quickstart omits the fresh quote",
    )
    contract.require(
        "Viridis never treats a prior purchase as permission to spend again."
        in quickstart,
        "quickstart omits the no-recurring-authority boundary",
    )
    contract.require(
        'id="official-client"' in quickstart,
        "quickstart paid-client anchor is missing",
    )
    contract.require(
        'id="radar-repeat-call"' in quickstart,
        "quickstart repeat-client anchor is missing",
    )
    contract.require(
        "--route regulatory-radar --max-payment-usdc 0.25" in quickstart,
        "quickstart omits the returning-buyer $0.25 ceiling",
    )
    contract.require(
        "This is exactly one new paid attempt." in quickstart
        and "authorize any later purchase" in quickstart,
        "quickstart omits bounded repeat-attempt authority",
    )
    contract.require(
        ".card code{display:block;overflow-wrap:anywhere;"
        "word-break:break-word}" in quickstart,
        "quickstart endpoint cards are not overflow-safe",
    )
    return {
        "status": "ok",
        "mode": "public_gateway",
        "base": base,
        "agent_count": len(agents),
        "payment_enabled": True,
        "intro_state": intro_state,
        "radar_amount_atomic_usdc": 250000,
        "surface_sha256": {
            name: _surface_sha256(value)
            for name, value in surfaces.items()
        },
        "state_mutation": "none_probe_is_read_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=PUBLIC_GATEWAY_BASE)
    parser.add_argument(
        "--intro-state",
        choices=("enabled", "disabled"),
        required=True,
    )
    args = parser.parse_args()
    try:
        result = probe_public_gateway(args.base.rstrip("/"), args.intro_state)
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "mode": "public_gateway",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
