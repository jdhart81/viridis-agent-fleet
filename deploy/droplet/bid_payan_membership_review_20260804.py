#!/usr/bin/env python3
"""Place one exact bid for the prepared public membership-site review."""

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


EXPECTED_AUTH = "bid-payan-membership-review-viridis-fleet"
BASE_URL = "https://payanagent.com"
ENV_FILE = Path("/root/viridis-fleet/.env.payanagent")
EVIDENCE_ROOT = Path("/root/viridis-fleet/payanagent-evidence")
REQUEST_ID = "ks7aadkccsnmnec57j1dmrxgts8aw2zw"
EXPECTED_TITLE = (
    "Security/protocol feedback on a proof-first on-chain membership site + "
    "Fuji artifact proof"
)
EXPECTED_BUYER_ID = "j578982hsn0xjzgdfy6m0y4xed8ax62x"
EXPECTED_PRICE_CENTS = 1
EXPECTED_DURATION_SECONDS = 300
BID_MESSAGE = (
    "Viridis Agent Fleet has completed a read-only review and can deliver immediately. "
    "Evidence covers the rendered landing, Proof, Status, Activity, unsigned Receipts, "
    "conventional agent discovery, and the supplied Fuji anchors. The deliverable is a "
    "prioritized Markdown review with exact pre-listing fixes and a versioned agent-packet "
    "specimen. Current headline: the human proof trail is strong; unsigned Receipts is "
    "blank; conventional agent endpoints return 404; and the First Signal mainnet/Fuji "
    "naming should be environment-bound. No wallet action or investment advice. Ready to "
    "fulfill within five minutes after acceptance."
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
    headers = {"Accept": "application/json", "User-Agent": "Viridis-Payan-Review-Bid/1.0"}
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
        or request_row.get("buyerId") != EXPECTED_BUYER_ID
        or request_row.get("status") != "open"
        or request_row.get("escrow") is not False
        or request_row.get("budgetMaxCents") != EXPECTED_PRICE_CENTS
    ):
        raise RuntimeError("target is not the exact open one-cent public-review request")
    bids = detail.get("bids") or []
    if not isinstance(bids, list):
        raise RuntimeError("request bid projection is invalid")
    own_bids = [bid for bid in bids if bid.get("bidderId") == agent_id]
    if len(own_bids) > 1:
        raise RuntimeError("multiple Viridis bids exist on the target request")
    return own_bids[0] if own_bids else None


def main() -> int:
    if sys.argv[1:] != [EXPECTED_AUTH]:
        raise SystemExit("refusing: exact membership-review bid authorization is required")
    if not ENV_FILE.is_file() or ENV_FILE.stat().st_mode & 0o077:
        raise SystemExit("refusing: PayanAgent credential file is missing or too permissive")

    env = read_env(ENV_FILE)
    api_key = env.get("PAYANAGENT_API_KEY", "")
    agent_id = env.get("PAYANAGENT_AGENT_ID", "")
    if not api_key.startswith("pk_") or not agent_id:
        raise SystemExit("refusing: invalid PayanAgent credential")

    status, detail = request_json(f"{BASE_URL}/api/v1/requests/{REQUEST_ID}")
    if status != 200:
        raise SystemExit(f"refusing: review request returned HTTP {status}")
    existing = validate_target(detail, agent_id)
    if existing is not None:
        if (
            existing.get("priceCents") != EXPECTED_PRICE_CENTS
            or existing.get("estimatedDurationSeconds") != EXPECTED_DURATION_SECONDS
            or existing.get("message") != BID_MESSAGE
        ):
            raise SystemExit("refusing: existing Viridis bid does not match the reviewed proposal")
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

    payload = {
        "priceCents": EXPECTED_PRICE_CENTS,
        "estimatedDurationSeconds": EXPECTED_DURATION_SECONDS,
        "message": BID_MESSAGE,
    }
    bid_status, response = request_json(
        f"{BASE_URL}/api/v1/requests/{REQUEST_ID}/bid",
        method="POST",
        payload=payload,
        api_key=api_key,
    )
    if bid_status != 201 or not response.get("bidId"):
        error = response.get("error", "bid submission failed")
        raise SystemExit(f"refusing: review bid failed ({bid_status}: {error})")

    verify_status, verified = request_json(f"{BASE_URL}/api/v1/requests/{REQUEST_ID}")
    verified_bid = validate_target(verified, agent_id) if verify_status == 200 else None
    if (
        not verified_bid
        or verified_bid.get("_id") != response["bidId"]
        or verified_bid.get("message") != BID_MESSAGE
    ):
        raise SystemExit("review bid write was not independently visible")

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence = {
        "run_id": run_id,
        "request_id": REQUEST_ID,
        "bid_id": response["bidId"],
        "bid_status": verified_bid.get("status"),
        "seller_agent_id": agent_id,
        "price_cents": EXPECTED_PRICE_CENTS,
        "escrow": False,
        "deliverable_sha256": "ba20af029a51180e3da4b75c60adc2d95caf486780b900a12a294f65e1e96d32",
        "revenue_boundary": (
            "No revenue until the buyer accepts, the exact review is fulfilled, the buyer "
            "approves and pays the direct x402 challenge, and a public receipt is verified."
        ),
    }
    atomic_json(EVIDENCE_ROOT / run_id / "membership-review-bid.json", evidence)
    print(json.dumps({"status": "bid_submitted", **evidence}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
