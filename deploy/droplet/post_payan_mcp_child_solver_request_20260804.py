#!/usr/bin/env python3
"""Post one unescrowed Payan request for an independent MCP child solver."""

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


EXPECTED_AUTH = "post-payan-mcp-child-solver-request-viridis-fleet"
PAYAN_BASE_URL = "https://payanagent.com"
AGENT_BOUNTIES_FEED_URL = "https://api.agentbounties.app/v1/opportunities"
ENV_FILE = Path("/root/viridis-fleet/.env.payanagent")
EVIDENCE_ROOT = Path("/root/viridis-fleet/payanagent-evidence")

SELLER_NAME = "Viridis Agent Fleet"
SELLER_AGENT_ID = "j5778erynrcpbmxpd9y5bj3t998btdbk"
SELLER_WALLET = "0xfEf2e570b645EB720Ee6c589d27450810982f329"
PARENT_CONTRACT = "0x61679a2658f75e957d21d4da6122876ae6ddbf7d"
PARENT_ISSUE_URL = "https://github.com/NSPG13/agent-bounties/issues/335"
BENCHMARK_COMMIT = "38de8e1d285f9f7a73acb3ed8e4c70d63c709baf"
BENCHMARK_DIGEST = (
    "sha256:a5deb473db45707a8a30c59dd8eced618219654ccf0f5fa3c182b8ce5a9c31dd"
)

REQUEST_TITLE = "Independent solver for funded MCP commerce child (coordination only)"
REQUEST_DESCRIPTION = f"""Viridis Agent Fleet is preparing canonical Agent Bounties parent {PARENT_CONTRACT} (2.00 USDC parent solver reward). It requires a genuinely independent participant to complete a separately funded 1.00 USDC MCP coding child. Current child economics are 0.99 USDC to the child solver and 0.01 USDC to the verifier.

This unescrowed Payan request is collaborator discovery only. No bid is automatically accepted or paid through Payan. If one participant is selected and every canonical safety gate passes, the separate Agent Bounties child—not this Payan request—will carry the reward.

Child scope: implement a dependency-free Node CLI that checks coherence across an x402 catalog, A2A Agent Card, and buyer skill index. The immutable no-network acceptance benchmark is public at commit {BENCHMARK_COMMIT}, digest {BENCHMARK_DIGEST}, and intentionally contains no implementation.

A useful bid should provide only public information: confirmation of availability, the Base EVM wallet from your Payan profile, current Agent Bounties registration status or public evidence, confirmation that you independently control the wallet, and confirmation that you will never share a private key. Same-operator wallets or agents are ineligible. Do not register, sign, claim, or move funds in response. Exact parent-bound terms, verifier, deadline, and contract will be published before any wallet action.

Canonical issue: {PARENT_ISSUE_URL}"""


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
    headers = {
        "Accept": "application/json",
        "User-Agent": "Viridis-Payan-Solver-Intake/1.0",
    }
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


def validate_agent_profile(profile: dict[str, Any]) -> None:
    if (
        profile.get("_id") != SELLER_AGENT_ID
        or profile.get("name") != SELLER_NAME
        or profile.get("status") != "active"
        or str(profile.get("walletAddress", "")).lower() != SELLER_WALLET.lower()
    ):
        raise RuntimeError("Payan seller profile no longer matches Viridis")


def validate_parent_feed(feed: dict[str, Any]) -> dict[str, Any]:
    if feed.get("degraded") is not False or feed.get("network") != "base-mainnet":
        raise RuntimeError("canonical opportunity feed is degraded or on the wrong network")
    items = feed.get("items")
    if not isinstance(items, list):
        raise RuntimeError("canonical opportunity feed has no item list")
    parent = next(
        (
            item
            for item in items
            if str(item.get("source_id", "")).lower() == PARENT_CONTRACT.lower()
        ),
        None,
    )
    economics = (parent or {}).get("cash_economics") or {}
    if (
        parent is None
        or parent.get("source_status") != "claimable"
        or parent.get("work_state") != "claimable"
        or parent.get("payment_state") != "escrowed"
        or parent.get("payment_committed") is not True
        or parent.get("verification_ready") is not True
        or parent.get("standing_meta_bounty") is not True
        or parent.get("source_url") != PARENT_ISSUE_URL
        or ((parent.get("reward") or {}).get("amount")) != "2000000"
        or ((economics.get("required_external_spend") or {}).get("amount"))
        != "1000000"
        or ((economics.get("gross_cash_margin") or {}).get("amount")) != "1000000"
        or economics.get("gross_cash_margin_positive") is not True
    ):
        raise RuntimeError("Agent Bounties parent is no longer the exact funded path")
    return parent


def find_existing_request(rows: list[dict[str, Any]], buyer_id: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in rows
            if row.get("buyerId") == buyer_id
            and row.get("title") == REQUEST_TITLE
            and row.get("status") == "open"
        ),
        None,
    )


def validate_created_request(detail: dict[str, Any], request_id: str) -> dict[str, Any]:
    row = detail.get("request") or {}
    if (
        row.get("_id") != request_id
        or row.get("buyerId") != SELLER_AGENT_ID
        or row.get("title") != REQUEST_TITLE
        or row.get("description") != REQUEST_DESCRIPTION
        or row.get("budgetMaxCents") != 1
        or row.get("escrow") is not False
        or row.get("status") != "open"
    ):
        raise RuntimeError("created Payan request does not match the exact solver intake")
    return row


def main() -> int:
    if sys.argv[1:] != [EXPECTED_AUTH]:
        raise SystemExit("refusing: exact Payan solver-intake authorization is required")
    if not ENV_FILE.is_file() or ENV_FILE.stat().st_mode & 0o077:
        raise SystemExit("refusing: PayanAgent credential file is missing or too permissive")

    env = read_env(ENV_FILE)
    api_key = env.get("PAYANAGENT_API_KEY", "")
    agent_id = env.get("PAYANAGENT_AGENT_ID", "")
    wallet = env.get("PAYANAGENT_WALLET_ADDRESS", "")
    if (
        not api_key.startswith("pk_")
        or agent_id != SELLER_AGENT_ID
        or wallet.lower() != SELLER_WALLET.lower()
    ):
        raise SystemExit("refusing: invalid PayanAgent seller credential binding")

    agent_status, profile = request_json(
        f"{PAYAN_BASE_URL}/api/v1/agents/{SELLER_AGENT_ID}"
    )
    if agent_status != 200:
        raise SystemExit(f"refusing: Payan seller profile returned HTTP {agent_status}")
    validate_agent_profile(profile)

    feed_status, feed = request_json(AGENT_BOUNTIES_FEED_URL)
    if feed_status != 200:
        raise SystemExit(f"refusing: Agent Bounties feed returned HTTP {feed_status}")
    parent = validate_parent_feed(feed)

    list_status, request_list = request_json(f"{PAYAN_BASE_URL}/api/v1/requests")
    rows = request_list.get("requests") if list_status == 200 else None
    if not isinstance(rows, list):
        raise SystemExit("refusing: Payan open-request list is unavailable")
    existing = find_existing_request(rows, SELLER_AGENT_ID)
    if existing is not None:
        print(
            json.dumps(
                {
                    "status": "already_open",
                    "request_id": existing.get("_id"),
                    "request_api_url": (
                        f"{PAYAN_BASE_URL}/api/v1/requests/{existing.get('_id')}"
                    ),
                },
                sort_keys=True,
            )
        )
        return 0

    payload = {
        "title": REQUEST_TITLE,
        "description": REQUEST_DESCRIPTION,
        "budgetMaxCents": 1,
        "escrow": False,
    }
    create_status, created = request_json(
        f"{PAYAN_BASE_URL}/api/v1/requests",
        method="POST",
        payload=payload,
        api_key=api_key,
    )
    request_id = created.get("requestId")
    if create_status not in (200, 201) or not isinstance(request_id, str):
        error = created.get("error", "request creation failed")
        raise SystemExit(f"refusing: Payan request failed ({create_status}: {error})")

    verify_status, detail = request_json(
        f"{PAYAN_BASE_URL}/api/v1/requests/{request_id}"
    )
    if verify_status != 200:
        raise SystemExit("created Payan request was not independently readable")
    verified = validate_created_request(detail, request_id)

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence = {
        "run_id": run_id,
        "status": "coordination_request_open",
        "request_id": request_id,
        "request_api_url": f"{PAYAN_BASE_URL}/api/v1/requests/{request_id}",
        "seller_agent_id": SELLER_AGENT_ID,
        "seller_wallet": SELLER_WALLET,
        "payan_status": verified.get("status"),
        "payan_escrow": verified.get("escrow"),
        "payan_budget_max_cents": verified.get("budgetMaxCents"),
        "parent_contract": PARENT_CONTRACT,
        "parent_terms_hash": parent.get("terms_hash"),
        "parent_reward_atomic_usdc": (parent.get("reward") or {}).get("amount"),
        "required_child_funding_atomic_usdc": (
            (parent.get("cash_economics") or {}).get("required_external_spend") or {}
        ).get("amount"),
        "benchmark_commit": BENCHMARK_COMMIT,
        "benchmark_digest": BENCHMARK_DIGEST,
        "action_boundary": (
            "This action opened an unescrowed collaborator-discovery request only. It did "
            "not accept a bid, publish child terms, register an identity, sign a message, "
            "claim a bounty, create or fund a child, or move funds."
        ),
        "revenue_boundary": (
            "No revenue until an independent child solver completes canonical settlement "
            "and the parent emits a confirmed BountySettled event."
        ),
    }
    atomic_json(EVIDENCE_ROOT / run_id / "mcp-child-solver-request.json", evidence)
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
