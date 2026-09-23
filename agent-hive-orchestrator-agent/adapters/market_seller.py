"""Bounded Agent Market seller worker for the reviewed $5 Hive.

The worker is read-only by default.  Apply mode may sign at most one fixed
cash-escrow offer per invocation, and only after deterministic capability,
counterparty, deadline, provider-readiness, and margin gates pass.  It never
opens escrow, confirms funding, calls a model, submits a delivery, or marks a
settlement.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adapters.mcp_server import (
    CONTRIBUTION_MARGIN_BPS,
    MIN_REQUIRED_CONTRIBUTION_MARGIN_BPS,
    SERVICE_PRICE_MINOR,
)

SELLER_ID = "viridis-hive-orchestrator"
PAYEE_ID = "viridis:hive"
CASH_ESCROW_ENDPOINT = "https://mcp.viridisconservation.com/payments/mcp"
PUBLIC_MARKET_URL = "https://mcp.viridisconservation.com/network/mcp"
INTERNAL_MARKET_URL = "http://agent-market-network:8410/mcp"
ALLOWED_MARKET_URLS = frozenset({PUBLIC_MARKET_URL, INTERNAL_MARKET_URL})
SELLER_CAPABILITIES = frozenset({
    "agent-orchestration",
    "cross-review",
    "multi-agent-synthesis",
    "nested-hive",
    "provenance",
    "reviewed-problem-solving",
})
MIN_DELIVERY_SECONDS = 3_600
MAX_RESPONSE_BYTES = 2_000_000


class SellerWorkerError(RuntimeError):
    pass


def _stable(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_action(action: str, actor_id: str, nonce: str,
                      signed_at: str, body: dict) -> str:
    return _stable({
        "protocol": "viridis-agent-market-v1",
        "action": action,
        "actor_id": actor_id,
        "nonce": nonce,
        "signed_at": signed_at,
        "body": body,
    })


def _decode_mcp_response(content_type: str, raw: str) -> dict:
    if "text/event-stream" in (content_type or ""):
        messages = [
            line[5:].strip() for line in raw.splitlines()
            if line.startswith("data:")]
        if not messages:
            raise SellerWorkerError("empty MCP event stream")
        message = json.loads(messages[-1])
    else:
        message = json.loads(raw)
    if message.get("error"):
        raise SellerWorkerError(
            "MCP error: " + str(message["error"].get("message") or "unknown"))
    result = message.get("result") or {}
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content") or []
    if content and isinstance(content[0], dict):
        text = content[0].get("text")
        if isinstance(text, str):
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
    raise SellerWorkerError("MCP result contains no structured object")


def default_market_call(tool: str, arguments: dict, *,
                        market_url: str = INTERNAL_MARKET_URL,
                        timeout_s: int = 20) -> dict:
    """Call the exact allowlisted Agent Market MCP endpoint."""
    if market_url not in ALLOWED_MARKET_URLS:
        raise SellerWorkerError("market URL is not allowlisted")
    body = _stable({
        "jsonrpc": "2.0", "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }).encode()
    request = urllib.request.Request(
        market_url, data=body, method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            "user-agent": "viridis-hive-market-seller/0.1",
        })
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise SellerWorkerError("Agent Market response exceeds size cap")
        return _decode_mcp_response(
            response.headers.get("content-type", ""),
            raw.decode("utf-8", "replace"))


class MarketSigner:
    """Caller-held signer; only the public signature crosses the boundary."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self._private_key = private_key

    @classmethod
    def from_env(
            cls,
            name: str = "VIRIDIS_AGENT_MARKET_PRIVATE_KEY_B64"
            ) -> "MarketSigner":
        raw = os.getenv(name, "").strip()
        if not raw:
            raise SellerWorkerError(f"{name} is not configured")
        try:
            decoded = base64.urlsafe_b64decode(
                raw + "=" * (-len(raw) % 4))
            return cls(Ed25519PrivateKey.from_private_bytes(decoded))
        except Exception as exc:
            raise SellerWorkerError(
                f"{name} is not a valid Ed25519 private key") from exc

    def auth(self, action: str, actor_id: str, body: dict) -> dict:
        nonce = "nonce-" + uuid.uuid4().hex
        signed_at = datetime.now(timezone.utc).isoformat()
        message = _canonical_action(
            action, actor_id, nonce, signed_at, body).encode()
        signature = base64.urlsafe_b64encode(
            self._private_key.sign(message)).decode().rstrip("=")
        return {"nonce": nonce, "signed_at": signed_at,
                "signature": signature}


class HiveMarketSeller:
    """One-cycle, at-most-one-offer seller with deterministic refusal reasons."""

    def __init__(
            self, market_call: Callable[[str, dict], dict] = default_market_call,
            signer: Optional[MarketSigner] = None,
            now_fn: Callable[[], datetime] = (
                lambda: datetime.now(timezone.utc))) -> None:
        self._market_call = market_call
        self._signer = signer
        self._now = now_fn

    @staticmethod
    def _payload(result: dict) -> dict:
        if result.get("status") != "ok":
            raise SellerWorkerError(
                str(result.get("message") or result.get("error")
                    or "Agent Market call failed"))
        data = result.get("data")
        if not isinstance(data, dict):
            raise SellerWorkerError("Agent Market response has no data object")
        return data

    def _refusal(self, work: dict, detail: dict) -> str:
        buyer = str(work.get("buyer_id") or "")
        if (not buyer or buyer == SELLER_ID
                or buyer.startswith("viridis-")
                or buyer.startswith("viridis:")):
            return "common_control_or_invalid_buyer"
        required = work.get("required_capabilities")
        if (not isinstance(required, list) or not required
                or not set(required).issubset(SELLER_CAPABILITIES)):
            return "capability_mismatch"
        if work.get("currency") != "USD":
            return "currency_not_supported"
        if int(work.get("budget_minor") or 0) < SERVICE_PRICE_MINOR:
            return "budget_below_fixed_price"
        if "viridis_cash_escrow" not in (work.get("allowed_rails") or []):
            return "verified_cash_escrow_not_allowed"
        if CONTRIBUTION_MARGIN_BPS < MIN_REQUIRED_CONTRIBUTION_MARGIN_BPS:
            return "contribution_margin_below_floor"
        if not os.getenv("OPENAI_API_KEY", "").strip():
            return "solver_provider_not_ready"
        try:
            deadline = datetime.fromisoformat(
                str(work.get("delivery_deadline") or "").replace(
                    "Z", "+00:00"))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
        except ValueError:
            return "invalid_delivery_deadline"
        remaining = int((deadline - self._now()).total_seconds())
        if remaining < MIN_DELIVERY_SECONDS:
            return "delivery_window_too_short"
        offers = detail.get("offers") or []
        if any(item.get("seller_id") == SELLER_ID for item in offers
               if isinstance(item, dict)):
            return "offer_already_exists"
        description = str(work.get("description") or "").strip()
        if not description or len(description) > 12_000:
            return "problem_statement_out_of_bounds"
        return ""

    def scan(self, limit: int = 25) -> dict:
        found = self._payload(self._market_call("search_work", {
            "query": "reviewed multi-agent synthesis orchestration",
            "capabilities": [],
            "currency": "USD",
            "min_budget_minor": SERVICE_PRICE_MINOR,
            "limit": max(1, min(int(limit), 100)),
        }))
        decisions = []
        for work in found.get("results") or []:
            detail = self._payload(self._market_call(
                "get_work", {"work_id": work.get("work_id", "")}))
            refusal = self._refusal(work, detail)
            decisions.append({
                "work": work,
                "eligible": not refusal,
                "refusal_reason": refusal or None,
            })
        decisions.sort(key=lambda row: (
            not row["eligible"],
            -int(row["work"].get("match_score") or 0),
            str(row["work"].get("work_id") or "")))
        return {
            "status": "ok",
            "mode": "read_only",
            "send_attempted": False,
            "eligible_count": sum(
                1 for item in decisions if item["eligible"]),
            "decisions": decisions,
            "commercial_boundary": (
                "an open work listing is not funded demand or revenue"),
        }

    def run_once(self, *, apply: bool = False, limit: int = 25) -> dict:
        report = self.scan(limit=limit)
        eligible = [
            item for item in report["decisions"] if item["eligible"]]
        if not apply:
            return report
        if os.getenv("HIVE_MARKET_APPLY", "").strip().lower() not in {
                "1", "true", "yes", "on"}:
            return {
                **report, "mode": "apply_refused",
                "apply_refusal": "HIVE_MARKET_APPLY is not enabled",
            }
        if not eligible:
            return {**report, "mode": "apply", "result": "no_eligible_work"}
        signer = self._signer or MarketSigner.from_env()
        work = eligible[0]["work"]
        work_id = str(work["work_id"])
        body = {
            "work_id": work_id,
            "amount_minor": SERVICE_PRICE_MINOR,
            "currency": "USD",
            "proposal": (
                "Fixed-price reviewed multi-agent synthesis with cross-review, "
                "content-addressed audit, and execution only after exact "
                "cash-escrow funding is independently verified."),
            "delivery_seconds": MIN_DELIVERY_SECONDS,
            "settlement": {
                "rail": "viridis_cash_escrow",
                "payment_endpoint": CASH_ESCROW_ENDPOINT,
                "payee_id": PAYEE_ID,
            },
            "idempotency_key": "hive-offer-" + hashlib.sha256(
                work_id.encode()).hexdigest()[:24],
        }
        auth = signer.auth("submit_offer", SELLER_ID, body)
        submitted = self._market_call("submit_offer", {
            "seller_id": SELLER_ID, **body, "auth": auth})
        result = self._payload(submitted)
        return {
            **report,
            "mode": "apply",
            "send_attempted": True,
            "selected_work_id": work_id,
            "offer": result,
            "execution_started": False,
            "funding_claimed": False,
            "money_movement": "none",
        }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Read-only-by-default Hive Agent Market seller worker")
    parser.add_argument(
        "--apply", action="store_true",
        help="submit at most one offer; also requires HIVE_MARKET_APPLY=1")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    report = HiveMarketSeller().run_once(
        apply=args.apply, limit=args.limit)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
