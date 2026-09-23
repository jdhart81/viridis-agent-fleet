#!/usr/bin/env python3
"""Claim five existing Payan catalog rows as verified Viridis seller offers.

The five routes were ingested before the Viridis Payan seller existed.  They
are buyable, but their public rows have generic titles, no seller binding and
the catalog rank floor.  Payan's seller-claim contract upserts by the exact
external URL after verifying that the live x402 payTo matches the seller
wallet.  This script requires every expected row and live payment term to
match before the first authenticated write, so it cannot create duplicates or
silently reprice an offer.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


APPLY_AUTH = "claim-payanagent-legacy-catalog-viridis-fleet"
PREVIEW_AUTH = "preview"
BASE_URL = "https://payanagent.com"
MANIFEST_URL = "https://mcp.viridisconservation.com/.well-known/x402"
ENV_FILE = Path("/root/viridis-fleet/.env.payanagent")
EVIDENCE_ROOT = Path("/root/viridis-fleet/payanagent-evidence")
SELLER_ID = "j5778erynrcpbmxpd9y5bj3t998btdbk"
PAY_TO = "0xfEf2e570b645EB720Ee6c589d27450810982f329"
NETWORK = "eip155:8453"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


@dataclass(frozen=True)
class Claim:
    route: str
    offer_id: str
    title: str
    category: str
    tags: tuple[str, ...]
    input_schema: str
    example_input: dict[str, Any]

    @property
    def endpoint(self) -> str:
        return f"https://mcp.viridisconservation.com/x402/{self.route}"


CLAIMS = (
    Claim(
        route="regulatory-radar/scan_regulations",
        offer_id="kh71jvk21hyvzpvy37hxkh99f18b9cvs",
        title="Viridis Regulatory Radar — Compliance Scan",
        category="Climate Compliance",
        tags=("regulatory", "climate", "compliance", "audit", "x402"),
        input_schema=(
            'JSON body: {"jurisdiction":"US","sector":"energy",'
            '"query":"optional text"}. jurisdiction is required.'
        ),
        example_input={
            "jurisdiction": "US",
            "sector": "energy",
            "query": "45V clean energy tax credit emissions disclosure",
        },
    ),
    Claim(
        route="taxcredit-engine/calculate_tax_credit",
        offer_id="kh7an3kg5qr1tzxsta05tw5yth8b9edd",
        title="Viridis Clean-Energy Tax Credit Calculator",
        category="Climate Finance",
        tags=("tax-credit", "clean-energy", "45v", "45q", "audit"),
        input_schema=(
            'JSON body: {"credit":"45V","facts":{"tax_year":2026}}. '
            "credit and facts are required; supports 45Q, 45V, 45Y, 48E, and 45X."
        ),
        example_input={"credit": "45V", "facts": {"tax_year": 2026}},
    ),
    Claim(
        route="ghg-ledger/calculate_inventory",
        offer_id="kh71yv0d9y9t1stx2gfx5gtz818b9czp",
        title="Viridis Auditable GHG Inventory",
        category="Climate Accounting",
        tags=("ghg", "scope-1", "scope-2", "scope-3", "audit"),
        input_schema=(
            'JSON body: {"activities":[],"options":null}. activities is required.'
        ),
        example_input={"activities": [], "options": None},
    ),
    Claim(
        route="quantity-takeoff/calculate_takeoff",
        offer_id="kh7fas3xbj5cvj1e0ekvc9qjd18b8kc8",
        title="Viridis Embodied-Carbon Quantity Takeoff",
        category="Construction Climate",
        tags=("quantity-takeoff", "embodied-carbon", "construction", "audit"),
        input_schema=(
            'JSON body: {"items":[{"id":"slab-1","assembly":"concrete_slab",'
            '"unit_system":"imperial","dimensions":{...}}],"options":null}. '
            "items is required."
        ),
        example_input={
            "items": [
                {
                    "id": "slab-1",
                    "assembly": "concrete_slab",
                    "unit_system": "imperial",
                    "dimensions": {
                        "length": {"value": "20", "unit": "ft"},
                        "width": {"value": "30", "unit": "ft"},
                        "thickness": {"value": "4", "unit": "in"},
                    },
                }
            ],
            "options": {"project_id": "buyer-project-1"},
        },
    ),
    Claim(
        route="disclosure-compiler/compile_disclosure",
        offer_id="kh719baytv7nvzcf4ksj4dnrsd8b93av",
        title="Viridis Sustainability Disclosure Compiler",
        category="Climate Disclosure",
        tags=("csrd", "ifrs-s2", "tcfd", "disclosure", "audit"),
        input_schema=(
            'JSON body: {"framework":"esrs-e1","company_facts":{...},'
            '"ghg_result":null,"options":null}. framework and company_facts '
            "are required."
        ),
        example_input={
            "framework": "esrs-e1",
            "company_facts": {
                "company_name": "Example Climate Works",
                "reporting_period": "2026",
            },
            "ghg_result": None,
            "options": {
                "applicability": {
                    "framework": "esrs-e1",
                    "applies": True,
                    "reason": "buyer-supplied applicability",
                    "source": "buyer",
                }
            },
        },
    ),
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
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Accept": "application/json", "User-Agent": "Viridis-Payan-Claim/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        try:
            error_body = json.loads(exc.read())
        except Exception:
            error_body = {"error": f"HTTP {exc.code}"}
        return exc.code, error_body


def probe_terms(url: str, example_input: dict[str, Any], timeout: int = 30) -> dict[str, str]:
    body = json.dumps(example_input, separators=(",", ":")).encode()
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Viridis-Payan-Claim/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raise RuntimeError(f"{url} returned HTTP {response.status}, expected 402")
    except HTTPError as exc:
        if exc.code != 402:
            raise RuntimeError(f"{url} returned HTTP {exc.code}, expected 402") from exc
        encoded = exc.headers.get("payment-required")
        raw_body = exc.read()
        challenge: dict[str, Any]
        if encoded:
            try:
                challenge = json.loads(base64.b64decode(encoded))
            except Exception as parse_exc:
                raise RuntimeError(f"{url} carried an invalid PAYMENT-REQUIRED header") from parse_exc
        else:
            try:
                challenge = json.loads(raw_body)
            except Exception as parse_exc:
                raise RuntimeError(f"{url} carried no parseable payment challenge") from parse_exc
    accepts = challenge.get("accepts")
    if not isinstance(accepts, list):
        raise RuntimeError(f"{url} payment challenge has no accepts list")
    matches = [
        item
        for item in accepts
        if isinstance(item, dict)
        and item.get("scheme") == "exact"
        and item.get("network") == NETWORK
        and str(item.get("asset", "")).lower() == USDC.lower()
    ]
    if len(matches) != 1:
        raise RuntimeError(f"{url} did not expose one exact Base USDC payment term")
    term = matches[0]
    amount = term.get("amount", term.get("maxAmountRequired"))
    if not str(amount or "").isdigit():
        raise RuntimeError(f"{url} payment amount is invalid")
    return {
        "payTo": str(term.get("payTo", "")),
        "asset": str(term.get("asset", "")),
        "network": str(term.get("network", "")),
        "amountRaw": str(amount),
    }


def validate_existing_offer(
    claim: Claim,
    offer: dict[str, Any],
    terms: dict[str, str],
    *,
    nominal_amount: str | None = None,
    intro_amount: str | None = None,
) -> None:
    if offer.get("_id") != claim.offer_id or offer.get("isActive") is not True:
        raise RuntimeError(f"{claim.route}: expected active offer {claim.offer_id}")
    seller_id = offer.get("sellerId")
    if seller_id not in (None, SELLER_ID):
        raise RuntimeError(f"{claim.route}: existing offer belongs to another seller")
    stored_amount = str(offer.get("amountRaw", ""))
    live_amount = terms["amountRaw"]
    if stored_amount != live_amount:
        is_exact_intro_correction = (
            nominal_amount is not None
            and intro_amount is not None
            and stored_amount == nominal_amount
            and live_amount == intro_amount
        )
        if not is_exact_intro_correction:
            raise RuntimeError(
                f"{claim.route}: unapproved catalog quote change "
                f"({stored_amount} -> {live_amount})"
            )
    if terms["payTo"].lower() != PAY_TO.lower():
        raise RuntimeError(f"{claim.route}: live route pays a different wallet")
    if terms["network"] != NETWORK or terms["asset"].lower() != USDC.lower():
        raise RuntimeError(f"{claim.route}: live route is not canonical Base USDC")


def is_exact_claimed(
    claim: Claim, offer: dict[str, Any], terms: dict[str, str]
) -> bool:
    return (
        offer.get("sellerId") == SELLER_ID
        and offer.get("title") == claim.title
        and offer.get("httpMethod") == "POST"
        and offer.get("isActive") is True
        and int(offer.get("rankScore", 0)) >= 1000
        and str(offer.get("amountRaw", "")) == terms["amountRaw"]
    )


def offer_detail_url(offer_id: str) -> str:
    # Public offer details advertise a one-hour cache. Every launch decision
    # and post-write proof must observe a fresh projection.
    return f"{BASE_URL}/api/v1/offers/{offer_id}?verify={time.time_ns()}"


def claim_payload(claim: Claim, description: str) -> dict[str, Any]:
    return {
        "title": claim.title,
        "description": description
        + " Successful paid responses include the viridis-paid-delivery-v1 delivery contract.",
        "category": claim.category,
        "tags": list(claim.tags),
        "offerType": "api",
        "externalUrl": claim.endpoint,
        "httpMethod": "POST",
        "verificationBody": claim.example_input,
        "inputSchema": claim.input_schema,
        "outputSchema": (
            "JSON response with deterministic result data and "
            "viridis-paid-delivery-v1 receipt metadata after successful settlement."
        ),
        "estimatedDurationSeconds": 30,
        "previewDescription": (
            "Non-custodial Base USDC x402 route. Send the documented JSON body by POST. "
            "Authoritative payment terms come from the live HTTP 402 challenge."
        ),
    }


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
    if len(sys.argv) != 2 or sys.argv[1] not in (PREVIEW_AUTH, APPLY_AUTH):
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} preview|{APPLY_AUTH}")
    apply = sys.argv[1] == APPLY_AUTH

    status, manifest = request_json(MANIFEST_URL)
    if status != 200:
        raise SystemExit(f"refusing: live manifest returned HTTP {status}")
    live_routes = {
        f"{route.get('agent')}/{route.get('tool')}": route
        for route in manifest.get("routes", [])
        if isinstance(route, dict)
    }
    if len(live_routes) != 8 or any(claim.route not in live_routes for claim in CLAIMS):
        raise SystemExit("refusing: live eight-route fleet catalog is incomplete or changed")
    intro = manifest.get("intro_pricing") or {}
    intro_schedule = intro.get("schedule") or {}
    intro_amount = str(intro_schedule.get("amount_atomic", ""))
    if (
        intro.get("enabled") is not True
        or intro_schedule.get("scope")
        != "one successful HTTP x402 v2 settlement per payer wallet"
        or not intro_amount.isdigit()
    ):
        raise SystemExit("refusing: live intro-pricing contract is incomplete or changed")

    prepared: list[dict[str, Any]] = []
    for claim in CLAIMS:
        live = live_routes[claim.route]
        if live.get("endpoint") != claim.endpoint or live.get("paid_execution_method") != "POST":
            raise SystemExit(f"refusing: {claim.route} live execution contract changed")
        detail_status, detail = request_json(offer_detail_url(claim.offer_id))
        offer = detail.get("offer") or {}
        if detail_status != 200:
            raise SystemExit(f"refusing: {claim.offer_id} returned HTTP {detail_status}")
        terms = probe_terms(claim.endpoint, claim.example_input)
        nominal_amount = str(live.get("amount_atomic_usdc", ""))
        if not nominal_amount.isdigit():
            raise SystemExit(f"refusing: {claim.route} has no nominal live amount")
        validate_existing_offer(
            claim,
            offer,
            terms,
            nominal_amount=nominal_amount,
            intro_amount=intro_amount,
        )
        prepared.append(
            {
                "claim": claim,
                "description": str(live.get("description", "")),
                "terms": terms,
                "prior_seller_id": offer.get("sellerId"),
                "prior_rank_score": offer.get("rankScore"),
                "prior_amount_raw": str(offer.get("amountRaw", "")),
                "catalog_quote_correction": (
                    str(offer.get("amountRaw", "")) != terms["amountRaw"]
                ),
                "already_claimed": is_exact_claimed(claim, offer, terms),
            }
        )

    if all(row["already_claimed"] for row in prepared):
        print(
            json.dumps(
                {
                    "status": "already_claimed",
                    "writes_performed": 0,
                    "offer_ids": [row["claim"].offer_id for row in prepared],
                },
                sort_keys=True,
            )
        )
        return 0

    if not apply:
        print(
            json.dumps(
                {
                    "status": "ready",
                    "writes_performed": 0,
                    "offers": [
                        {
                            "route": row["claim"].route,
                            "offer_id": row["claim"].offer_id,
                            "amount_raw": row["terms"]["amountRaw"],
                            "prior_amount_raw": row["prior_amount_raw"],
                            "catalog_quote_correction": row["catalog_quote_correction"],
                            "prior_seller_id": row["prior_seller_id"],
                            "prior_rank_score": row["prior_rank_score"],
                        }
                        for row in prepared
                    ],
                },
                sort_keys=True,
            )
        )
        return 0

    if not ENV_FILE.is_file() or ENV_FILE.stat().st_mode & 0o077:
        raise SystemExit("refusing: PayanAgent credential file is missing or too permissive")
    env = read_env(ENV_FILE)
    api_key = env.get("PAYANAGENT_API_KEY", "")
    agent_id = env.get("PAYANAGENT_AGENT_ID", "")
    wallet = env.get("PAYANAGENT_WALLET_ADDRESS", "")
    if (
        not api_key.startswith("pk_")
        or agent_id != SELLER_ID
        or wallet.lower() != PAY_TO.lower()
    ):
        raise SystemExit("refusing: invalid PayanAgent seller credential binding")

    claimed: list[dict[str, Any]] = []
    for row in prepared:
        claim: Claim = row["claim"]
        write_status, response = request_json(
            f"{BASE_URL}/api/v1/offers",
            method="POST",
            payload=claim_payload(claim, row["description"]),
            api_key=api_key,
        )
        if write_status != 201 or response.get("offerId") != claim.offer_id:
            raise SystemExit(
                f"refusing: {claim.route} claim did not preserve exact offer id "
                f"({write_status}: {response.get('error', 'unexpected response')})"
            )
        verify_status, verify_detail = request_json(offer_detail_url(claim.offer_id))
        verified = verify_detail.get("offer") or {}
        if (
            verify_status != 200
            or verified.get("sellerId") != SELLER_ID
            or verified.get("title") != claim.title
            or verified.get("httpMethod") != "POST"
            or verified.get("isActive") is not True
            or int(verified.get("rankScore", 0)) < 1000
            or str(verified.get("amountRaw", "")) != row["terms"]["amountRaw"]
        ):
            raise SystemExit(f"refusing: {claim.route} claim did not verify")
        claimed.append(
            {
                "route": claim.route,
                "offer_id": claim.offer_id,
                "title": claim.title,
                "amount_raw": row["terms"]["amountRaw"],
                "prior_amount_raw": row["prior_amount_raw"],
                "catalog_quote_correction": row["catalog_quote_correction"],
                "rank_score": verified.get("rankScore"),
                "seller_id": verified.get("sellerId"),
            }
        )

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence = {
        "schema": "viridis-payan-catalog-claim-v1",
        "run_id": run_id,
        "seller_id": SELLER_ID,
        "wallet": PAY_TO,
        "claimed_offer_count": len(claimed),
        "offers": claimed,
        "funds_moved": False,
        "payments_signed": False,
        "new_offer_ids_created": False,
        "revenue_boundary": (
            "Catalog ownership and discovery rank are distribution evidence, not a sale, "
            "settlement, delivery receipt, repeat purchase, or revenue."
        ),
    }
    evidence_path = EVIDENCE_ROOT / run_id / "catalog-claim.json"
    atomic_json(evidence_path, evidence)
    print(
        json.dumps(
            {
                "status": "claimed",
                "claimed_offer_count": len(claimed),
                "offer_ids": [row["offer_id"] for row in claimed],
                "evidence_path": str(evidence_path),
                "funds_moved": False,
                "payments_signed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
