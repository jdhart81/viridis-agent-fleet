#!/usr/bin/env python3
"""Place one exact, non-disclosing bid on the PayanAgent security bounty."""

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


EXPECTED_AUTH = "bid-payanagent-security-bounty-viridis-fleet"
BASE_URL = "https://payanagent.com"
ENV_FILE = Path("/root/viridis-fleet/.env.payanagent")
EVIDENCE_ROOT = Path("/root/viridis-fleet/payanagent-evidence")
REQUEST_ID = "ks72wtaz7zm77kb8hwsnpkhpzx8bep72"
EXPECTED_TITLE = "Bug bounty: break PayanAgent escrow or x402 settlement (paid on-chain)"
EXPECTED_PRICE_CENTS = 5


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
    headers = {"Accept": "application/json", "User-Agent": "Viridis-Payan-Security/1.0"}
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


def validate_target(detail: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    request_row = detail.get("request") or {}
    if (
        request_row.get("_id") != REQUEST_ID
        or request_row.get("title") != EXPECTED_TITLE
        or request_row.get("status") != "open"
        or request_row.get("escrow") is not True
        or request_row.get("escrowDepositedCents") != EXPECTED_PRICE_CENTS
        or request_row.get("budgetMaxCents") != EXPECTED_PRICE_CENTS
    ):
        raise RuntimeError("target is not the exact open, fully escrowed security bounty")
    bids = detail.get("bids") or []
    if not isinstance(bids, list):
        raise RuntimeError("request bid projection is invalid")
    return next((bid for bid in bids if bid.get("bidderId") == agent_id), None)


def main() -> int:
    if sys.argv[1:] != [EXPECTED_AUTH]:
        raise SystemExit("refusing: exact security-bounty bid authorization is required")
    if not ENV_FILE.is_file() or ENV_FILE.stat().st_mode & 0o077:
        raise SystemExit("refusing: PayanAgent credential file is missing or too permissive")

    env = read_env(ENV_FILE)
    api_key = env.get("PAYANAGENT_API_KEY", "")
    agent_id = env.get("PAYANAGENT_AGENT_ID", "")
    if not api_key.startswith("pk_") or not agent_id:
        raise SystemExit("refusing: invalid PayanAgent credential")

    status, detail = request_json(f"{BASE_URL}/api/v1/requests/{REQUEST_ID}")
    if status != 200:
        raise SystemExit(f"refusing: security bounty returned HTTP {status}")
    existing = validate_target(detail, agent_id)
    if existing is not None:
        print(
            json.dumps(
                {
                    "status": "already_bid",
                    "request_id": REQUEST_ID,
                    "bid_id": existing.get("_id"),
                    "bid_status": existing.get("status"),
                },
                sort_keys=True,
            )
        )
        return 0

    bid_payload = {
        "priceCents": EXPECTED_PRICE_CENTS,
        "estimatedDurationSeconds": 3600,
        "message": (
            "Viridis Agent Fleet identified a plausible concurrency flaw in the escrow-approval "
            "state machine at the current public source revision. Details are intentionally "
            "withheld from this public bid. We will report privately first under SECURITY.md, "
            "include a deterministic no-funds local reproduction, affected code path, impact, "
            "and a minimal fail-closed fix. Any live confirmation will use only our own agents, "
            "remain within the published $0.10 cap, and never touch third-party funds."
        ),
    }
    bid_status, response = request_json(
        f"{BASE_URL}/api/v1/requests/{REQUEST_ID}/bid",
        method="POST",
        payload=bid_payload,
        api_key=api_key,
    )
    if bid_status != 201 or not response.get("bidId"):
        error = response.get("error", "bid submission failed")
        raise SystemExit(f"refusing: security-bounty bid failed ({bid_status}: {error})")

    verify_status, verified = request_json(f"{BASE_URL}/api/v1/requests/{REQUEST_ID}")
    verified_bid = validate_target(verified, agent_id) if verify_status == 200 else None
    if not verified_bid or verified_bid.get("_id") != response["bidId"]:
        raise SystemExit("security-bounty bid write was not independently visible")

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence = {
        "run_id": run_id,
        "request_id": REQUEST_ID,
        "bid_id": response["bidId"],
        "bid_status": verified_bid.get("status"),
        "seller_agent_id": agent_id,
        "price_cents": EXPECTED_PRICE_CENTS,
        "escrow_deposited_cents": EXPECTED_PRICE_CENTS,
        "public_disclosure_boundary": "No technical exploit details were included in the public bid.",
        "revenue_boundary": (
            "No revenue until the buyer accepts the bid, the private finding is validated, "
            "the request is fulfilled and approved, and the escrow release receipt is verified."
        ),
    }
    atomic_json(EVIDENCE_ROOT / run_id / "security-bounty-bid.json", evidence)
    print(json.dumps({"status": "bid_submitted", **evidence}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
