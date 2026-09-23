#!/usr/bin/env python3
"""Fail-closed acceptance monitor for the two Viridis x402-example bids."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from bid_payan_x402_examples_20260804 import (
    BASE_URL,
    EXPECTED_BUYER_ID,
    JOBS,
    exact_bid_payload,
)


SELLER_ID = "j5778erynrcpbmxpd9y5bj3t998btdbk"
EXPECTED_BID_IDS = {
    "ks797p4mww498ztv323mdd1vvh8bfzta": "jd767hxkjwvsbn6mhkwkbyrew98btyrr",
    "ks79bq5bjft533h785fp3sn5d58bf4dg": "jd77jka44dwxr94f5s182ed7198bvzgx",
}
LATEST_PATH = Path(
    "/root/viridis-fleet/payanagent-evidence/x402-examples-acceptance-latest.json"
)
EVENT_ROOT = Path(
    "/root/viridis-fleet/payanagent-evidence/x402-example-acceptance-events"
)


def request_json(url: str, timeout: int = 30) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Viridis-Payan-x402-Acceptance-Watch/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read())
        except Exception:
            payload = {"error": f"HTTP {exc.code}"}
        return exc.code, payload


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


def validate_exact_bid(request_id: str, detail: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = JOBS[request_id]
    row = detail.get("request") or {}
    if (
        row.get("_id") != request_id
        or row.get("title") != expected["title"]
        or row.get("buyerId") != EXPECTED_BUYER_ID
        or row.get("escrow") is not True
        or row.get("escrowDepositedCents") != expected["budget_cents"]
        or row.get("budgetMaxCents") != expected["budget_cents"]
    ):
        raise RuntimeError(f"{request_id}: exact funded request no longer matches")
    bids = detail.get("bids")
    if not isinstance(bids, list):
        raise RuntimeError(f"{request_id}: bid projection is invalid")
    own = [bid for bid in bids if bid.get("bidderId") == SELLER_ID]
    if len(own) != 1:
        raise RuntimeError(f"{request_id}: exact Viridis bid is not unique")
    bid = own[0]
    if bid.get("_id") != EXPECTED_BID_IDS[request_id]:
        raise RuntimeError(f"{request_id}: Viridis bid id drifted")
    expected_payload = exact_bid_payload(expected)
    for key, value in expected_payload.items():
        if bid.get(key) != value:
            raise RuntimeError(f"{request_id}: Viridis bid {key} drifted")
    return row, bid


def classify(request_id: str, detail: dict[str, Any]) -> dict[str, Any]:
    row, bid = validate_exact_bid(request_id, detail)
    request_status = str(row.get("status") or "")
    bid_status = str(bid.get("status") or "")
    provider_id = row.get("providerId")
    agreed_price = row.get("agreedPriceCents")

    if request_status == "open" and bid_status == "pending":
        state = "pending_buyer_acceptance"
    elif request_status == "accepted" and bid_status == "accepted":
        if provider_id != SELLER_ID or agreed_price != JOBS[request_id]["bid_cents"]:
            raise RuntimeError(f"{request_id}: accepted assignment or price drifted")
        state = "accepted_purchase_authorization_required"
    elif request_status in {"fulfilled", "approved", "completed"}:
        state = (
            "viridis_delivery_requires_receipt_verification"
            if provider_id == SELLER_ID
            else "lost_to_other_provider"
        )
    elif provider_id and provider_id != SELLER_ID:
        state = "lost_to_other_provider"
    elif bid_status in {"rejected", "withdrawn", "cancelled"}:
        state = "bid_inactive"
    else:
        raise RuntimeError(
            f"{request_id}: unrecognized request/bid state {request_status}/{bid_status}"
        )

    return {
        "request_id": request_id,
        "bid_id": bid.get("_id"),
        "request_status": request_status,
        "bid_status": bid_status,
        "provider_id": provider_id,
        "agreed_price_cents": agreed_price,
        "state": state,
        "external_purchase_cap_usd": "0.001",
        "purchase_authorized": False,
        "funds_moved": False,
        "fulfilled": request_status in {"fulfilled", "approved", "completed"},
    }


def material_state(snapshot: dict[str, Any] | None) -> dict[str, str]:
    if not snapshot:
        return {}
    return {
        str(item["request_id"]): str(item["state"])
        for item in snapshot.get("jobs", [])
        if isinstance(item, dict) and item.get("request_id") and item.get("state")
    }


def build_snapshot(
    fetch: Callable[[str], tuple[int, dict[str, Any]]], observed_at: str
) -> dict[str, Any]:
    jobs = []
    for request_id in JOBS:
        status, detail = fetch(request_id)
        if status != 200:
            raise RuntimeError(f"{request_id}: public request returned HTTP {status}")
        jobs.append(classify(request_id, detail))
    accepted = sum(
        1 for job in jobs if job["state"] == "accepted_purchase_authorization_required"
    )
    return {
        "observed_at": observed_at,
        "status": "ok",
        "classification": "read_only_exact_bid_acceptance_watch",
        "jobs": jobs,
        "accepted_authorization_required_count": accepted,
        "next_action": (
            "hold_for_exact_purchase_authorization"
            if accepted
            else "wait_for_buyer_acceptance"
        ),
        "boundaries": {
            "signs": False,
            "spends": False,
            "moves_money": False,
            "buys_offer": False,
            "fulfills_request": False,
            "approves_delivery": False,
            "recognizes_revenue": False,
        },
    }


def load_previous(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:
        raise RuntimeError("previous acceptance snapshot is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("previous acceptance snapshot is not an object")
    return payload


def main() -> int:
    observed_at = datetime.now(timezone.utc).isoformat()

    def fetch(request_id: str) -> tuple[int, dict[str, Any]]:
        return request_json(f"{BASE_URL}/api/v1/requests/{request_id}")

    snapshot = build_snapshot(fetch, observed_at)
    previous = load_previous(LATEST_PATH)
    changed = material_state(previous) != material_state(snapshot)
    snapshot["material_state_changed"] = changed
    atomic_json(LATEST_PATH, snapshot)
    if changed:
        event_name = observed_at.replace(":", "").replace("+00:00", "Z") + ".json"
        atomic_json(EVENT_ROOT / event_name, snapshot)
    print(json.dumps(snapshot, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
