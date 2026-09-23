#!/usr/bin/env python3
"""Fulfill the exact membership-site review only after its bid is accepted."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from bid_payan_membership_review_20260804 import (
    BASE_URL,
    BID_MESSAGE,
    EXPECTED_BUYER_ID,
    EXPECTED_DURATION_SECONDS,
    EXPECTED_PRICE_CENTS,
    EXPECTED_TITLE,
    REQUEST_ID,
    read_env,
)


EXPECTED_AUTH = "fulfill-payan-membership-review-viridis-fleet"
ENV_FILE = Path("/root/viridis-fleet/.env.payanagent")
STATE_DIR = Path("/root/viridis-fleet/payanagent-state/membership-review")
DELIVERABLE = Path("/root/viridis-fleet/payanagent/proof-first-membership-review.md")
DELIVERABLE_SHA256 = "ba20af029a51180e3da4b75c60adc2d95caf486780b900a12a294f65e1e96d32"


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    api_key: str | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Accept": "application/json", "User-Agent": "Viridis-Payan-Review-Fulfiller/1.0"}
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


def exact_bid(detail: dict[str, Any], agent_id: str) -> dict[str, Any]:
    request_row = detail.get("request") or {}
    if (
        request_row.get("_id") != REQUEST_ID
        or request_row.get("title") != EXPECTED_TITLE
        or request_row.get("buyerId") != EXPECTED_BUYER_ID
        or request_row.get("escrow") is not False
        or request_row.get("budgetMaxCents") != EXPECTED_PRICE_CENTS
    ):
        raise RuntimeError("exact membership-review request is no longer verifiable")
    bids = detail.get("bids") or []
    candidates = [
        bid
        for bid in bids
        if bid.get("bidderId") == agent_id
        and bid.get("priceCents") == EXPECTED_PRICE_CENTS
        and bid.get("estimatedDurationSeconds") == EXPECTED_DURATION_SECONDS
        and bid.get("message") == BID_MESSAGE
    ]
    if len(candidates) != 1 or not candidates[0].get("_id"):
        raise RuntimeError("exact Viridis review bid is not uniquely verifiable")
    return candidates[0]


def fulfillment_action(
    detail: dict[str, Any], agent_id: str, bid: dict[str, Any]
) -> str:
    request_row = detail.get("request") or {}
    request_status = str(request_row.get("status") or "")
    bid_status = str(bid.get("status") or "")
    if request_status in {"fulfilled", "approved", "completed"}:
        if request_row.get("providerId") != agent_id:
            raise RuntimeError("completed request is assigned to a different provider")
        return "already_fulfilled"
    if request_status == "open" and bid_status == "pending":
        return "pending_buyer_acceptance"
    if request_status == "accepted" and bid_status == "accepted":
        if (
            request_row.get("providerId") != agent_id
            or request_row.get("agreedPriceCents") != EXPECTED_PRICE_CENTS
        ):
            raise RuntimeError("accepted request is not assigned at the exact bid price")
        return "fulfill"
    return f"inactive:{request_status}:{bid_status}"


def build_output(deliverable: str, bid_id: str) -> str:
    return f"""# Viridis delivery — proof-first membership and artifact-readiness review

Request: `{REQUEST_ID}`  
Accepted bid: `{bid_id}`  
Review SHA-256: `{DELIVERABLE_SHA256}`

This is a public, read-only review. It involved no wallet connection, signature, transaction, purchase, or investment analysis. The Fuji checks prove successful testnet transactions only; they do not prove a mainnet deployment, sale, market, value, or buyer demand.

---

{deliverable}
"""


def main() -> int:
    if sys.argv[1:] != [EXPECTED_AUTH]:
        raise SystemExit("refusing: exact membership-review fulfillment authorization is required")
    if not ENV_FILE.is_file() or ENV_FILE.stat().st_mode & 0o077:
        raise SystemExit("refusing: PayanAgent credential file is missing or too permissive")
    if not DELIVERABLE.is_file():
        raise SystemExit("refusing: reviewed membership deliverable is missing")
    deliverable = DELIVERABLE.read_text()
    if hashlib.sha256(deliverable.encode()).hexdigest() != DELIVERABLE_SHA256:
        raise SystemExit("refusing: membership deliverable digest changed")

    env = read_env(ENV_FILE)
    api_key = env.get("PAYANAGENT_API_KEY", "")
    agent_id = env.get("PAYANAGENT_AGENT_ID", "")
    if not api_key.startswith("pk_") or not agent_id:
        raise SystemExit("refusing: invalid PayanAgent credential")

    status, detail = request_json(f"{BASE_URL}/api/v1/requests/{REQUEST_ID}")
    if status != 200:
        raise SystemExit(f"refusing: review request returned HTTP {status}")
    bid = exact_bid(detail, agent_id)
    action = fulfillment_action(detail, agent_id, bid)
    if action != "fulfill":
        print(
            json.dumps(
                {
                    "status": action,
                    "request_id": REQUEST_ID,
                    "bid_id": bid["_id"],
                },
                sort_keys=True,
            )
        )
        return 0

    output_payload = build_output(deliverable, bid["_id"])
    fulfill_status, response = request_json(
        f"{BASE_URL}/api/v1/requests/{REQUEST_ID}/fulfill",
        method="POST",
        payload={"outputPayload": output_payload},
        api_key=api_key,
        timeout=60,
    )
    if fulfill_status != 200 or response.get("ok") is not True:
        raise SystemExit(f"membership-review fulfillment failed with HTTP {fulfill_status}")

    verify_status, verified = request_json(f"{BASE_URL}/api/v1/requests/{REQUEST_ID}")
    verified_request = verified.get("request") or {}
    if (
        verify_status != 200
        or verified_request.get("status") != "fulfilled"
        or verified_request.get("providerId") != agent_id
    ):
        raise SystemExit("membership-review fulfillment was not independently visible")
    receipt = {
        "request_id": REQUEST_ID,
        "bid_id": bid["_id"],
        "status": "fulfilled_pending_buyer_approval_and_payment",
        "deliverable_sha256": DELIVERABLE_SHA256,
        "fulfilled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "revenue_boundary": (
            "No revenue until buyer approval completes the direct x402 payment and a public "
            "receipt plus wallet settlement are independently verified."
        ),
    }
    atomic_json(STATE_DIR / "delivery.json", receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
