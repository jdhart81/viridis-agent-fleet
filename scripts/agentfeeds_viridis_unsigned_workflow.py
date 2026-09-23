#!/usr/bin/env python3
"""Emit an offline, unsigned sanctions-to-disclosure buyer workflow.

This command performs no network requests, loads no wallet, signs nothing, and
cannot submit a payment. It prepares buyer-owned inputs and explicit evidence
gates for three separately authorized x402 purchases:

1. agentfeeds.jp OFAC address screening;
2. Viridis Regulatory Radar; and
3. Viridis Disclosure Compiler.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


AGENTFEEDS_OPENAPI = "https://api.agentfeeds.jp/openapi.json"
AGENTFEEDS_OFAC = "https://api.agentfeeds.jp/v1/reg/sanctions/ofac/check"
VIRIDIS_CATALOG = "https://mcp.viridisconservation.com/x402/catalog"
VIRIDIS_RADAR = (
    "https://mcp.viridisconservation.com/"
    "x402/regulatory-radar/scan_regulations"
)
VIRIDIS_DISCLOSURE = (
    "https://mcp.viridisconservation.com/"
    "x402/disclosure-compiler/compile_disclosure"
)
FRAMEWORKS = ("esrs-e1", "ifrs-s2", "sec-climate", "tnfd")
JURISDICTIONS = {
    "AU", "CA", "EU", "GLOBAL", "JP", "SG", "UK", "US", "US-CA",
}
ADDRESS_RE = re.compile(r"^[A-Za-z0-9]{20,100}$")


def validate_address(value: str) -> str:
    """Validate the public crypto address without making a network request."""
    address = value.strip()
    if not ADDRESS_RE.fullmatch(address):
        raise ValueError(
            "address must contain 20-100 alphanumeric characters"
        )
    return address


def normalize_jurisdiction(value: str) -> str:
    """Normalize supported jurisdictions and preserve CA as Canada."""
    jurisdiction = value.strip().upper()
    if jurisdiction == "CALIFORNIA":
        jurisdiction = "US-CA"
    if jurisdiction not in JURISDICTIONS:
        raise ValueError(
            "jurisdiction must be one of "
            + ", ".join(sorted(JURISDICTIONS | {"CALIFORNIA"}))
        )
    return jurisdiction


def parse_company_facts(raw: str) -> dict[str, Any]:
    """Parse buyer-owned company facts from one JSON object."""
    value = json.loads(raw)
    if not isinstance(value, dict) or not value:
        raise ValueError("company facts must be a non-empty JSON object")
    return value


def build_plan(
    *,
    address: str,
    jurisdiction: str,
    sector: str | None,
    query: str | None,
    framework: str,
    company_facts: dict[str, Any],
) -> dict[str, Any]:
    """Build a non-executing plan with a fresh authorization before each call."""
    checked_address = validate_address(address)
    checked_jurisdiction = normalize_jurisdiction(jurisdiction)
    if framework not in FRAMEWORKS:
        raise ValueError(f"unsupported disclosure framework: {framework}")
    if not isinstance(company_facts, dict) or not company_facts:
        raise ValueError("company facts must be a non-empty object")

    radar_input: dict[str, Any] = {"jurisdiction": checked_jurisdiction}
    if sector:
        radar_input["sector"] = sector
    if query:
        radar_input["query"] = query

    return {
        "kind": "unsigned_buyer_workflow_plan",
        "version": "2026-07-28",
        "state": "local_draft_not_published",
        "purpose": (
            "screen a buyer-supplied crypto address, inspect applicable "
            "climate requirements, and prepare a disclosure from buyer facts"
        ),
        "execution": {
            "network_requests_performed": 0,
            "wallet_loaded": False,
            "payment_authorized": False,
            "paid_retry_allowed": False,
            "automatic_follow_on_allowed": False,
        },
        "contract_evidence": {
            "agentfeeds": {
                "source": AGENTFEEDS_OPENAPI,
                "openapi_specification": "3.1.0",
                "document_version": "1.0.0",
                "checked_at": "2026-07-28T20:17:00Z",
                "known_gap": (
                    "generated_at and freshness_sec are optional in the "
                    "published envelope; the OFAC example has no list date"
                ),
            },
            "viridis": {
                "source": VIRIDIS_CATALOG,
                "checked_at": "2026-07-28T20:18:00Z",
            },
        },
        "steps": [
            {
                "sequence": 1,
                "seller": "agentfeeds.jp",
                "product": "sanctions.ofac.check",
                "method": "GET",
                "url": AGENTFEEDS_OFAC,
                "request": {"query": {"address": checked_address}},
                "advertised_price_usdc_non_authoritative": "0.002",
                "required_result": {
                    "kind": "factual_data",
                    "product": "sanctions.ofac.check",
                    "data.address": checked_address,
                    "data.matched": "boolean",
                    "data.entries": "array",
                    "sources": "non-empty array",
                    "generated_at": "required by this workflow",
                    "freshness_sec": "required by this workflow",
                    "list_observed_at_or_equivalent": (
                        "required before publication"
                    ),
                },
                "stop_conditions": [
                    "the returned address differs from the buyer input",
                    "matched is true or ambiguous",
                    "sources are empty",
                    "freshness or list-observation time is absent or stale",
                    "the fresh unpaid x402 challenge exceeds the buyer mandate",
                ],
            },
            {
                "sequence": 2,
                "seller": "Viridis",
                "product": "regulatory-radar/scan_regulations",
                "method": "POST",
                "url": VIRIDIS_RADAR,
                "request": {"json": radar_input},
                "advertised_price_usdc_non_authoritative": "0.25",
                "requires": [
                    "step 1 passed",
                    "a new live unpaid HTTP 402",
                    "a separate buyer route-and-amount authorization",
                ],
                "stop_conditions": [
                    "the live challenge is not x402 v2 exact on Base USDC",
                    "resource, receiver, or amount exceeds the buyer mandate",
                    "the response lacks a PAYMENT-RESPONSE settlement receipt",
                ],
            },
            {
                "sequence": 3,
                "seller": "Viridis",
                "product": "disclosure-compiler/compile_disclosure",
                "method": "POST",
                "url": VIRIDIS_DISCLOSURE,
                "request": {
                    "json": {
                        "framework": framework,
                        "company_facts": company_facts,
                    }
                },
                "advertised_price_usdc_non_authoritative": "2.00",
                "requires": [
                    "the buyer reviews the Radar result for applicability",
                    "all company facts remain buyer supplied",
                    "a new live unpaid HTTP 402",
                    "a separate buyer route-and-amount authorization",
                ],
                "stop_conditions": [
                    "applicability would need to be inferred from missing facts",
                    "the live challenge is not x402 v2 exact on Base USDC",
                    "resource, receiver, or amount exceeds the buyer mandate",
                    "the response lacks a PAYMENT-RESPONSE settlement receipt",
                ],
            },
        ],
        "publication_gate": {
            "ready": False,
            "needs": [
                "agentfeeds confirms the canonical freshness and list "
                "observation fields for every sanctions result",
                "one buyer-owned real use case supplies the address and facts",
                "each paid call receives a fresh, separate authorization",
            ],
        },
        "commercial_boundary": (
            "this plan is not a purchase, integration, repeat customer, "
            "subscription, MRR, or revenue"
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Emit an offline unsigned agentfeeds-to-Viridis workflow plan; "
            "perform no network request and authorize no payment."
        )
    )
    parser.add_argument("--address", required=True)
    parser.add_argument("--jurisdiction", default="US")
    parser.add_argument("--sector", default="energy")
    parser.add_argument("--query", default="climate disclosure requirements")
    parser.add_argument("--framework", choices=FRAMEWORKS, default="ifrs-s2")
    parser.add_argument(
        "--company-facts-json",
        required=True,
        help="buyer-owned company facts as one JSON object",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        plan = build_plan(
            address=args.address,
            jurisdiction=args.jurisdiction,
            sector=args.sector,
            query=args.query,
            framework=args.framework,
            company_facts=parse_company_facts(args.company_facts_json),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
