#!/usr/bin/env python3
"""Commercial margin gate for the paid Regulatory Radar scan.

The gate recomputes every claimed value, refuses stale facilitator pricing,
checks the live health contract when supplied, and audits the Radar source
tree for provider/network imports. It performs no payment or model call.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT / "regulatory-radar-agent/commercial_contract.json"
)
DEFAULT_SOURCE_DIR = ROOT / "regulatory-radar-agent/src"
FORBIDDEN_PROVIDER_IMPORTS = frozenset({
    "aiohttp",
    "anthropic",
    "boto3",
    "google",
    "httpx",
    "openai",
    "requests",
    "socket",
    "subprocess",
})
LIVE_HEALTH_URL = "https://mcp.viridisconservation.com/healthz"


class MarginGateFailure(RuntimeError):
    """The commercial contract cannot safely authorize distribution."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MarginGateFailure(message)


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{name} must be an integer",
    )
    require(value >= minimum, f"{name} is below {minimum}")
    return value


def _parse_time(value: Any, name: str) -> datetime:
    require(isinstance(value, str), f"{name} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarginGateFailure(f"{name} is malformed") from exc
    require(parsed.tzinfo is not None, f"{name} is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def _margin(price: int, cost: int) -> tuple[int, int]:
    require(price > 0, "price must be positive")
    require(cost <= price, "variable cost exceeds price")
    contribution = price - cost
    margin_bps = contribution * 10_000 // price
    return contribution, margin_bps


def audit_source_tree(source_dir: Path) -> dict[str, Any]:
    require(source_dir.is_dir(), "Radar source directory is missing")
    files = sorted(source_dir.rglob("*.py"))
    require(bool(files), "Radar source tree has no Python files")
    imported_roots: set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
    forbidden = sorted(imported_roots & FORBIDDEN_PROVIDER_IMPORTS)
    require(
        not forbidden,
        "Radar execution source imports provider/network modules: "
        + ", ".join(forbidden),
    )
    return {
        "python_files": len(files),
        "provider_network_imports": forbidden,
        "provider_model_cost_atomic": 0,
    }


def validate_contract(
    contract: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    require(
        contract.get("schema")
        == "viridis-regulatory-radar-commercial-contract-v1",
        "commercial contract schema changed",
    )
    require(contract.get("currency") == "USDC", "currency must be USDC")
    require(
        contract.get("network") == "eip155:8453",
        "network must be Base mainnet",
    )
    require(
        contract.get("atomic_per_usdc") == 1_000_000,
        "USDC atomic scale changed",
    )
    prices = contract.get("prices")
    costs = contract.get("variable_cost_ceiling")
    computed = contract.get("computed")
    evidence = contract.get("evidence")
    require(isinstance(prices, dict), "prices are missing")
    require(isinstance(costs, dict), "variable costs are missing")
    require(isinstance(computed, dict), "computed margin claims are missing")
    require(isinstance(evidence, dict), "cost evidence is missing")

    list_price = _integer(prices.get("list_atomic"), "list price", minimum=1)
    intro_price = _integer(
        prices.get("intro_atomic"),
        "intro price",
        minimum=1,
    )
    cost_fields = (
        "facilitator_atomic",
        "model_atomic",
        "external_data_atomic",
        "seller_gas_atomic",
        "marginal_compute_and_egress_reserve_atomic",
    )
    cost_values = {
        name: _integer(costs.get(name), name)
        for name in cost_fields
    }
    require(
        cost_values["facilitator_atomic"] == 1_000,
        "paid-tier facilitator ceiling is not $0.001",
    )
    for zero_cost in ("model_atomic", "external_data_atomic", "seller_gas_atomic"):
        require(cost_values[zero_cost] == 0, f"{zero_cost} must remain zero")
    require(
        cost_values["marginal_compute_and_egress_reserve_atomic"] >= 1_000,
        "marginal infrastructure reserve is below $0.001",
    )
    total_cost = sum(cost_values.values())
    require(
        costs.get("total_atomic") == total_cost,
        "variable-cost total is not recomputable",
    )
    minimum_margin = _integer(
        contract.get("minimum_contribution_margin_bps"),
        "minimum contribution margin",
        minimum=1,
    )
    require(
        minimum_margin >= 4_000,
        "minimum contribution margin is below 40%",
    )

    observed_at = _parse_time(
        evidence.get("facilitator_pricing_observed_at"),
        "facilitator pricing observed_at",
    )
    review_by = _parse_time(
        evidence.get("facilitator_pricing_review_by"),
        "facilitator pricing review_by",
    )
    require(review_by > observed_at, "pricing review window is invalid")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    require(now >= observed_at, "pricing evidence is from the future")
    require(now <= review_by, "facilitator pricing evidence is stale")
    require(
        str(evidence.get("facilitator_pricing_url") or "").startswith(
            "https://docs.cdp.coinbase.com/x402/"
        ),
        "facilitator evidence is not an official CDP x402 source",
    )

    intro_contribution, intro_margin = _margin(intro_price, total_cost)
    list_contribution, list_margin = _margin(list_price, total_cost)
    require(
        intro_margin >= minimum_margin,
        "intro price is below the contribution-margin floor",
    )
    require(
        list_margin >= minimum_margin,
        "list price is below the contribution-margin floor",
    )
    minimum_safe_price = math.ceil(
        total_cost * 10_000 / (10_000 - minimum_margin)
    )
    expected_computed = {
        "intro_contribution_atomic": intro_contribution,
        "intro_contribution_margin_bps": intro_margin,
        "list_contribution_atomic": list_contribution,
        "list_contribution_margin_bps": list_margin,
        "minimum_safe_price_atomic": minimum_safe_price,
    }
    require(
        computed == expected_computed,
        "computed margin claims do not match the cost contract",
    )
    return {
        "status": "ok",
        "total_variable_cost_atomic": total_cost,
        "minimum_contribution_margin_bps": minimum_margin,
        **expected_computed,
        "facilitator_pricing_review_by": review_by.isoformat(),
    }


def validate_health_contract(health: dict[str, Any]) -> dict[str, Any]:
    require(health.get("status") == "ok", "live health is not ok")
    x402 = health.get("payment_gate", {}).get("x402", {})
    require(x402.get("enabled") is True, "live x402 is not enabled")
    routes = x402.get("http_front_door", [])
    radar = [
        item for item in routes
        if isinstance(item, dict)
        and item.get("agent") == "regulatory-radar"
        and item.get("tool") == "scan_regulations"
    ]
    require(len(radar) == 1, "live Radar route is missing or duplicated")
    require(
        str(radar[0].get("amount_atomic_usdc")) == "250000",
        "live Radar list price is not $0.25",
    )
    intro = x402.get("intro_pricing", {})
    require(intro.get("enabled") is True, "live intro pricing is not enabled")
    schedule = intro.get("schedule", {})
    require(
        str(schedule.get("amount_atomic")) == "10000",
        "live Radar intro price is not $0.01",
    )
    return {
        "list_price_atomic": 250_000,
        "intro_price_atomic": 10_000,
        "x402_enabled": True,
    }


def fetch_live_health(
    url: str,
    *,
    opener: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    require(
        url == LIVE_HEALTH_URL,
        "live margin gate refuses every URL except the exact Viridis health "
        "endpoint",
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "viridis-regulatory-radar-margin-gate/1",
        },
    )
    with opener(request, timeout=20) as response:
        require(
            int(getattr(response, "status", 200)) == 200,
            "live health returned a non-200 response",
        )
        payload = json.loads(response.read(2_000_000))
    require(isinstance(payload, dict), "live health is not an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--health-json", type=Path)
    parser.add_argument("--health-url")
    args = parser.parse_args()
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        require(isinstance(contract, dict), "commercial contract is invalid")
        result = {
            **validate_contract(contract),
            "source_audit": audit_source_tree(args.source_dir),
        }
        require(
            not (args.health_json and args.health_url),
            "choose only one live health input",
        )
        if args.health_json:
            health = json.loads(args.health_json.read_text(encoding="utf-8"))
            require(isinstance(health, dict), "health capture is invalid")
            result["live_contract"] = validate_health_contract(health)
        elif args.health_url:
            result["live_contract"] = validate_health_contract(
                fetch_live_health(args.health_url)
            )
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
