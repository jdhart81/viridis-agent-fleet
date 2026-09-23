#!/usr/bin/env python3
"""Place exact Viridis bids on two escrow-backed Payan x402 example jobs."""

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


EXPECTED_AUTH = "bid-payan-x402-examples-viridis-fleet"
BASE_URL = "https://payanagent.com"
ENV_FILE = Path("/root/viridis-fleet/.env.payanagent")
EVIDENCE_ROOT = Path("/root/viridis-fleet/payanagent-evidence")
EXPECTED_BUYER_ID = "j5704astznyebbqjcr73ey3bx188q5e2"
PUBLIC_BUNDLE = (
    "https://github.com/jdhart81/viridis-agent-fleet/tree/"
    "codex/payan-x402-examples-20260804/examples/payanagent-x402"
)
PUBLIC_COMMIT = "19885a8308a1b91c95d881f5155ff3c02f2f765b"

JOBS: dict[str, dict[str, Any]] = {
    "ks797p4mww498ztv323mdd1vvh8bfzta": {
        "title": "Working example: an agent that discovers + buys via the PayanAgent MCP",
        "budget_cents": 4,
        "bid_cents": 1,
        "duration_seconds": 600,
        "message": (
            "Public tested bundle ready: " + PUBLIC_BUNDLE + ". It uses the official "
            "@payanagent/mcp server, live discovery, a hard $0.001 purchase cap, Viridis "
            "self-purchase exclusion, and public receipt/tx verification. A no-wallet live "
            "dry run selected the current 0.1-cent weather offer; npm audit is clean and all "
            "seven tests pass. After acceptance we can run one dedicated-wallet purchase and "
            "fulfill the repo plus resolving receipt within ten minutes."
        ),
    },
    "ks79bq5bjft533h785fp3sn5d58bf4dg": {
        "title": "Minimal Python x402 buy example against /x402/:offerId",
        "budget_cents": 3,
        "bid_cents": 1,
        "duration_seconds": 600,
        "message": (
            "Public tested single-file Python buyer ready: " + PUBLIC_BUNDLE + ". It pins the "
            "official x402 2.18.0 SDK, validates x402 v2/exact/Base/canonical USDC/recipient/"
            "amount before signing, caps the example at $0.001, prints body + X-Receipt-Id + "
            "X-Tx-Hash, and verifies the receipt publicly. Its live unpaid challenge test "
            "reached the current weather offer and failed closed before signing under an "
            "impossible cap. After acceptance we can return the file and real resolving receipt "
            "within ten minutes."
        ),
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
    headers = {"Accept": "application/json", "User-Agent": "Viridis-Payan-x402-Bids/1.0"}
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


def validate_target(
    request_id: str,
    detail: dict[str, Any],
    agent_id: str,
) -> dict[str, Any] | None:
    expected = JOBS[request_id]
    row = detail.get("request") or {}
    if (
        row.get("_id") != request_id
        or row.get("title") != expected["title"]
        or row.get("buyerId") != EXPECTED_BUYER_ID
        or row.get("status") != "open"
        or row.get("escrow") is not True
        or row.get("escrowDepositedCents") != expected["budget_cents"]
        or row.get("budgetMaxCents") != expected["budget_cents"]
    ):
        raise RuntimeError(f"{request_id} is not the exact open, fully escrowed job")
    bids = detail.get("bids") or []
    if not isinstance(bids, list):
        raise RuntimeError(f"{request_id} bid projection is invalid")
    own = [bid for bid in bids if bid.get("bidderId") == agent_id]
    if len(own) > 1:
        raise RuntimeError(f"{request_id} has multiple Viridis bids")
    return own[0] if own else None


def exact_bid_payload(expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "priceCents": expected["bid_cents"],
        "estimatedDurationSeconds": expected["duration_seconds"],
        "message": expected["message"],
    }


def verify_existing(existing: dict[str, Any], expected: dict[str, Any]) -> None:
    payload = exact_bid_payload(expected)
    for key, value in payload.items():
        if existing.get(key) != value:
            raise RuntimeError("existing Viridis bid differs from the reviewed proposal")
    if existing.get("status") not in {"pending", "accepted"}:
        raise RuntimeError("existing Viridis bid has an unexpected status")


def main() -> int:
    if sys.argv[1:] != [EXPECTED_AUTH]:
        raise SystemExit("refusing: exact Payan x402-example bid authorization is required")
    if not ENV_FILE.is_file() or ENV_FILE.stat().st_mode & 0o077:
        raise SystemExit("refusing: PayanAgent credential file is missing or too permissive")
    env = read_env(ENV_FILE)
    api_key = env.get("PAYANAGENT_API_KEY", "")
    agent_id = env.get("PAYANAGENT_AGENT_ID", "")
    if not api_key.startswith("pk_") or not agent_id:
        raise SystemExit("refusing: invalid PayanAgent seller credential")

    outcomes: list[dict[str, Any]] = []
    for request_id, expected in JOBS.items():
        status, detail = request_json(f"{BASE_URL}/api/v1/requests/{request_id}")
        if status != 200:
            raise SystemExit(f"refusing: {request_id} returned HTTP {status}")
        existing = validate_target(request_id, detail, agent_id)
        if existing is not None:
            verify_existing(existing, expected)
            outcomes.append(
                {
                    "request_id": request_id,
                    "bid_id": existing.get("_id"),
                    "bid_status": existing.get("status"),
                    "write": "already_present",
                }
            )
            continue

        payload = exact_bid_payload(expected)
        bid_status, response = request_json(
            f"{BASE_URL}/api/v1/requests/{request_id}/bid",
            method="POST",
            payload=payload,
            api_key=api_key,
        )
        if bid_status != 201 or not response.get("bidId"):
            error = response.get("error", "bid submission failed")
            raise SystemExit(f"refusing: {request_id} bid failed ({bid_status}: {error})")
        verify_status, verified = request_json(f"{BASE_URL}/api/v1/requests/{request_id}")
        verified_bid = validate_target(request_id, verified, agent_id) if verify_status == 200 else None
        if not verified_bid or verified_bid.get("_id") != response["bidId"]:
            raise SystemExit(f"refusing: {request_id} bid was not independently visible")
        verify_existing(verified_bid, expected)
        outcomes.append(
            {
                "request_id": request_id,
                "bid_id": response["bidId"],
                "bid_status": verified_bid.get("status"),
                "write": "submitted",
            }
        )

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence = {
        "run_id": run_id,
        "seller_agent_id": agent_id,
        "public_bundle": PUBLIC_BUNDLE,
        "public_commit": PUBLIC_COMMIT,
        "outcomes": outcomes,
        "bid_count": len(outcomes),
        "total_bid_cents": sum(JOBS[item["request_id"]]["bid_cents"] for item in outcomes),
        "external_purchase_cap_usd_per_job": "0.001",
        "revenue_boundary": (
            "Bids and artifact readiness are not revenue. Each job earns only after buyer "
            "acceptance, one separately authorized capped purchase, exact fulfillment, buyer "
            "approval, and a verified Payan escrow-release receipt."
        ),
    }
    evidence_path = EVIDENCE_ROOT / run_id / "x402-example-bids.json"
    atomic_json(evidence_path, evidence)
    print(json.dumps({"status": "bids_ready", **evidence, "evidence_path": str(evidence_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
