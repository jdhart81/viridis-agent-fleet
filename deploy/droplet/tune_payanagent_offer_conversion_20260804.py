#!/usr/bin/env python3
"""Make the three live Viridis Payan offers machine-readable and truthful."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


EXPECTED_AUTH = "tune-payanagent-offer-conversion-viridis-fleet"
BASE_URL = "https://payanagent.com"
ENV_FILE = Path("/root/viridis-fleet/.env.payanagent")
EVIDENCE_ROOT = Path("/root/viridis-fleet/payanagent-evidence")
SELLER_AGENT_ID = "j5778erynrcpbmxpd9y5bj3t998btdbk"
SELLER_WALLET = "0xfEf2e570b645EB720Ee6c589d27450810982f329"


def schema(properties: dict[str, Any], required: list[str]) -> str:
    return json.dumps(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": required,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


OUTPUT_SCHEMA = json.dumps(
    {
        "type": "object",
        "additionalProperties": True,
        "description": (
            "Deterministic result plus viridis-paid-delivery-v1 delivery metadata "
            "after successful Base USDC settlement."
        ),
    },
    separators=(",", ":"),
    sort_keys=True,
)


OFFER_UPDATES: dict[str, dict[str, Any]] = {
    "kh73cke3f40zjen52w3eqxh9mh8btpp7": {
        "expected": {
            "amountRaw": "10000",
            "priceCents": 1,
            "title": "Viridis Regulatory Watch — Deadline Monitor",
        },
        "patch": {
            "title": "1¢ Regulatory Deadline Watch — Source-Linked",
            "description": (
                "Check recently effective requirements and approaching compliance "
                "deadlines in the curated Viridis regulatory dataset. Returns dated, "
                "source-linked requirements, alert levels, and review actions. This is "
                "a deterministic calendar over curated records, not a live external "
                "regulatory feed. Eligible first-time Viridis payer wallets receive the "
                "1¢ x402-intro-v1 price; every live 402 challenge is authoritative."
            ),
            "tags": [
                "regulatory", "deadlines", "climate", "compliance", "x402",
            ],
            "inputSchema": schema(
                {
                    "jurisdiction": {
                        "type": "string",
                        "enum": [
                            "AU", "CA", "EU", "GLOBAL", "JP", "SG", "UK", "US",
                            "CALIFORNIA", "US-CA",
                        ],
                    },
                    "topics": {
                        "type": ["array", "null"],
                        "items": {"type": "string", "minLength": 1, "maxLength": 100},
                        "maxItems": 10,
                    },
                    "lookback_days": {"type": "integer", "minimum": 1, "maximum": 365},
                },
                ["jurisdiction"],
            ),
            "outputSchema": OUTPUT_SCHEMA,
            "estimatedDurationSeconds": 10,
            "previewDescription": (
                "First eligible Viridis purchase per payer wallet can settle at 0.01 "
                "USDC under x402-intro-v1. Inspect the fresh 402 before signing. "
                "Curated deadline evidence only; not a live external feed."
            ),
        },
    },
    "kh7cd063t5aca333vz0br4wsz18btp2f": {
        "expected": {
            "amountRaw": "5000000",
            "priceCents": 500,
            "title": "Viridis Audited Multi-Agent Solve",
        },
        "patch": {
            "title": "Audited Multi-Agent Solve — 3 Workers + Cross-Review",
            "description": (
                "Run one cost-bounded solve with three independent worker lanes, "
                "reviewer-not-author cross-review, trust outcomes, compute accounting, "
                "and a content-addressed audit. The fixed 5.00 USDC profile supports at "
                "most four subtasks and redundancy up to three. Every live 402 challenge "
                "is authoritative; no recurring payment is created."
            ),
            "tags": ["multi-agent", "cross-review", "audit", "reasoning", "x402"],
            "inputSchema": schema(
                {
                    "problem": {"type": "string", "minLength": 1, "maxLength": 12000},
                    "budget_minor": {"type": "integer", "const": 500},
                    "subtasks": {
                        "type": ["array", "null"],
                        "items": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "minItems": 1,
                        "maxItems": 4,
                    },
                    "depth": {"type": "integer", "const": 0},
                    "redundancy": {"type": "integer", "minimum": 1, "maximum": 3},
                    "accept_threshold": {
                        "type": "number", "exclusiveMinimum": 0, "maximum": 1,
                    },
                    "seed": {"type": "integer"},
                    "fee_bps": {"type": "integer", "const": 0},
                },
                ["problem", "budget_minor"],
            ),
            "outputSchema": OUTPUT_SCHEMA,
            "estimatedDurationSeconds": 30,
            "previewDescription": (
                "One fixed 5.00 USDC Base x402 solve. Up to four subtasks, three "
                "independent worker lanes, cross-review, and a content-addressed audit."
            ),
        },
    },
    "kh752yv6c7b8ndnnha1n12mz2n8bvw7a": {
        "expected": {
            "amountRaw": "10000",
            "priceCents": 1,
            "title": "Viridis MCP Agent Security Preflight",
        },
        "patch": {
            "title": "1¢ MCP Agent Security Preflight + Signed Receipt",
            "description": (
                "Statically check caller-supplied MCP agent metadata for endpoint and "
                "auth declarations, closed tool schemas, high-impact approval policy, "
                "policy conflicts, and prompt-injection indicators. Returns a signed, "
                "input-redacted receipt. It never fetches or certifies the deployed "
                "runtime. Eligible first-time Viridis payer wallets receive the 1¢ "
                "x402-intro-v1 price; every live 402 challenge is authoritative."
            ),
            "tags": ["mcp", "security", "policy", "injection", "attestation"],
            "inputSchema": schema(
                {
                    "agent_id": {"type": "string", "minLength": 1, "maxLength": 120},
                    "manifest": {"type": "object"},
                    "policy": {"type": ["object", "null"]},
                    "sample_inputs": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "maxItems": 50,
                    },
                    "subject_profile_sha256": {
                        "type": ["string", "null"], "pattern": "^[0-9a-f]{64}$",
                    },
                },
                ["agent_id", "manifest"],
            ),
            "outputSchema": OUTPUT_SCHEMA,
            "estimatedDurationSeconds": 10,
            "previewDescription": (
                "First eligible Viridis purchase per payer wallet can settle at 0.01 "
                "USDC under x402-intro-v1. Static buyer-supplied metadata only; no "
                "runtime fetch, secret storage, or automatic market import."
            ),
        },
    },
}


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
    headers = {"Accept": "application/json", "User-Agent": "Viridis-Payan-Offer-Tuner/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        try:
            error_body = json.loads(exc.read())
        except Exception:
            error_body = {"error": f"HTTP {exc.code}"}
        return exc.code, error_body


def validate_current(offer_id: str, row: dict[str, Any]) -> None:
    spec = OFFER_UPDATES[offer_id]
    expected = spec["expected"]
    if (
        row.get("_id") != offer_id
        or row.get("sellerId") != SELLER_AGENT_ID
        or row.get("isActive") is not True
        or str(row.get("payTo", "")).lower() != SELLER_WALLET.lower()
        or row.get("network") != "eip155:8453"
        or row.get("amountRaw") != expected["amountRaw"]
        or row.get("priceCents") != expected["priceCents"]
        or row.get("title") not in (expected["title"], spec["patch"]["title"])
    ):
        raise RuntimeError(f"offer {offer_id} no longer matches the exact Viridis listing")


def validate_updated(offer_id: str, row: dict[str, Any]) -> None:
    validate_current(offer_id, row)
    patch = OFFER_UPDATES[offer_id]["patch"]
    for key, value in patch.items():
        if row.get(key) != value:
            raise RuntimeError(f"offer {offer_id} did not persist {key}")


def tune_offers(
    api_key: str,
    requester: Callable[..., tuple[int, dict[str, Any]]] = request_json,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for offer_id, spec in OFFER_UPDATES.items():
        url = f"{BASE_URL}/api/v1/offers/{offer_id}"
        status, detail = requester(url)
        if status != 200:
            raise RuntimeError(f"offer {offer_id} returned HTTP {status}")
        validate_current(offer_id, detail.get("offer") or {})

        patch_status, patch_response = requester(
            url, method="PATCH", payload=spec["patch"], api_key=api_key
        )
        if patch_status != 200 or patch_response.get("ok") is not True:
            raise RuntimeError(f"offer {offer_id} update failed closed")

        # The public detail route advertises a one-hour cache. Use a unique
        # query key after mutation so verification observes the authoritative
        # updated row instead of a cached pre-update projection.
        verify_status, verified = requester(f"{url}?verify={time.time_ns()}")
        if verify_status != 200:
            raise RuntimeError(f"offer {offer_id} post-update readback failed")
        row = verified.get("offer") or {}
        validate_updated(offer_id, row)
        results.append(
            {
                "offer_id": offer_id,
                "title": row["title"],
                "price_cents": row["priceCents"],
                "amount_atomic_usdc": row["amountRaw"],
                "input_schema_sha256": hashlib.sha256(
                    row["inputSchema"].encode()
                ).hexdigest(),
            }
        )
    return results


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
        raise SystemExit("refusing: exact Payan offer-tuning authorization is required")
    if not ENV_FILE.is_file() or ENV_FILE.stat().st_mode & 0o077:
        raise SystemExit("refusing: PayanAgent credential file is missing or too permissive")
    env = read_env(ENV_FILE)
    api_key = env.get("PAYANAGENT_API_KEY", "")
    if (
        not api_key.startswith("pk_")
        or env.get("PAYANAGENT_AGENT_ID") != SELLER_AGENT_ID
        or env.get("PAYANAGENT_WALLET_ADDRESS", "").lower() != SELLER_WALLET.lower()
    ):
        raise SystemExit("refusing: invalid PayanAgent seller credential binding")

    results = tune_offers(api_key)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence = {
        "run_id": run_id,
        "status": "offer_metadata_tuned",
        "offers": results,
        "offer_count": len(results),
        "seller_agent_id": SELLER_AGENT_ID,
        "seller_wallet": SELLER_WALLET,
        "boundaries": {
            "changed_price": False,
            "changed_payment_terms": False,
            "changed_endpoint": False,
            "signed": False,
            "moved_money": False,
            "accepted_bid": False,
        },
        "revenue_boundary": (
            "Buyer-facing conversion metadata improved; no revenue exists until an "
            "independent settlement and successful paid delivery receipt are verified."
        ),
    }
    evidence_path = EVIDENCE_ROOT / run_id / "offer-conversion-tuning.json"
    atomic_json(evidence_path, evidence)
    print(json.dumps({**evidence, "evidence_path": str(evidence_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
