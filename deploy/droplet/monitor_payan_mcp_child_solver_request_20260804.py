#!/usr/bin/env python3
"""Read-only monitor for independent bids on the Viridis MCP solver intake."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = "https://payanagent.com"
REQUEST_ID = "ks78y33jgqrww5yrj7g1n0xb398bt35s"
REQUEST_TITLE = "Independent solver for funded MCP commerce child (coordination only)"
BUYER_ID = "j5778erynrcpbmxpd9y5bj3t998btdbk"
VIRIDIS_WALLET = "0xfEf2e570b645EB720Ee6c589d27450810982f329"
LATEST_PATH = Path(
    "/root/viridis-fleet/payanagent-evidence/solver-intake-latest.json"
)
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def request_json(url: str, timeout: int = 30) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Viridis-Payan-Solver-Monitor/1.0",
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


def validate_request(detail: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row = detail.get("request") or {}
    bids = detail.get("bids")
    if (
        row.get("_id") != REQUEST_ID
        or row.get("buyerId") != BUYER_ID
        or row.get("title") != REQUEST_TITLE
        or row.get("escrow") is not False
        or row.get("budgetMaxCents") != 1
        or not isinstance(bids, list)
    ):
        raise RuntimeError("solver-intake request no longer matches the exact public record")
    return row, bids


def safe_candidate(
    bid: dict[str, Any],
    profile: dict[str, Any] | None,
    profile_http_status: int,
) -> dict[str, Any]:
    raw_message = str(bid.get("message", ""))
    wallet = str((profile or {}).get("walletAddress", ""))
    profile_basics_valid = (
        profile_http_status == 200
        and (profile or {}).get("_id") == bid.get("bidderId")
        and (profile or {}).get("status") == "active"
        and (profile or {}).get("chain") == "base"
        and ADDRESS_RE.fullmatch(wallet) is not None
        and wallet.lower() != VIRIDIS_WALLET.lower()
    )
    provider_type = (profile or {}).get("providerType")
    public_profile_valid = profile_basics_valid and provider_type == "agent"
    return {
        "bid_id": bid.get("_id"),
        "bidder_id": bid.get("bidderId"),
        "bid_status": bid.get("status"),
        "price_cents": bid.get("priceCents"),
        "estimated_duration_seconds": bid.get("estimatedDurationSeconds"),
        "message_bytes": len(raw_message.encode()),
        "message_sha256": hashlib.sha256(raw_message.encode()).hexdigest(),
        "profile_http_status": profile_http_status,
        "profile_name": (profile or {}).get("name"),
        "profile_status": (profile or {}).get("status"),
        "profile_chain": (profile or {}).get("chain"),
        "profile_provider_type": provider_type,
        "public_base_wallet": wallet if ADDRESS_RE.fullmatch(wallet) else None,
        "profile_reputation": (profile or {}).get("reputation"),
        "public_profile_valid": public_profile_valid,
        "independence_verified": False,
        "agent_bounties_registration_verified": False,
        "eligibility": (
            "requires_canonical_independence_and_registration_review"
            if public_profile_valid
            else (
                "provider_type_ineligible_for_solver"
                if profile_basics_valid and provider_type != "agent"
                else "public_profile_failed_closed"
            )
        ),
    }


def build_snapshot(
    detail: dict[str, Any],
    fetch_profile: Callable[[str], tuple[int, dict[str, Any]]],
    observed_at: str,
) -> dict[str, Any]:
    row, bids = validate_request(detail)
    candidates = []
    for bid in bids:
        bidder_id = str(bid.get("bidderId", ""))
        if not bidder_id:
            candidates.append(safe_candidate(bid, None, 0))
            continue
        profile_status, profile = fetch_profile(bidder_id)
        candidates.append(safe_candidate(bid, profile, profile_status))
    viable_count = sum(
        1
        for candidate in candidates
        if candidate["public_profile_valid"] and candidate["bid_status"] == "pending"
    )
    return {
        "observed_at": observed_at,
        "status": "ok",
        "classification": "read_only_solver_intake_snapshot",
        "request_id": REQUEST_ID,
        "request_status": row.get("status"),
        "request_escrow": row.get("escrow"),
        "bid_count": len(bids),
        "public_profile_valid_pending_count": viable_count,
        "candidates": candidates,
        "next_action": (
            "review_candidate_independence_and_registration"
            if viable_count
            else "wait_for_candidate"
        ),
        "boundaries": {
            "accepts_bid": False,
            "registers_identity": False,
            "signs": False,
            "claims_parent": False,
            "publishes_child_terms": False,
            "funds_child": False,
            "moves_money": False,
            "stores_untrusted_bid_message": False,
        },
    }


def main() -> int:
    status, detail = request_json(f"{BASE_URL}/api/v1/requests/{REQUEST_ID}")
    if status != 200:
        raise SystemExit(f"solver-intake request returned HTTP {status}")

    def fetch_profile(agent_id: str) -> tuple[int, dict[str, Any]]:
        return request_json(f"{BASE_URL}/api/v1/agents/{agent_id}")

    observed_at = datetime.now(timezone.utc).isoformat()
    snapshot = build_snapshot(detail, fetch_profile, observed_at)
    atomic_json(LATEST_PATH, snapshot)
    print(json.dumps(snapshot, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
