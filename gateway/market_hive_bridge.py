"""Verified-funded Agent Market -> Hive execution and delivery bridge.

The bridge closes one narrow commercial lifecycle:

    awarded Hive offer
      -> independently Hub-verified live cash escrow still FUNDED
      -> one exact payment-gated Hive solve
      -> durable content-addressed artifact
      -> signed Market delivery

It deliberately does not accept delivery for the buyer, release/refund escrow,
attest buyer settlement, report usefulness, or call a model without a durable
Market hold.  Buyer acceptance therefore remains the release boundary.
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


SELLER_ID = "viridis-hive-orchestrator"
PAYEE_ID = "viridis:hive"
SERVICE_NAME = "hive"
SERVICE_PRICE_MINOR = 500
INTERNAL_MARKET_URL = "http://agent-market-network:8410/mcp"
PUBLIC_MARKET_URL = "https://mcp.viridisconservation.com/network/mcp"
ALLOWED_MARKET_URLS = frozenset({INTERNAL_MARKET_URL, PUBLIC_MARKET_URL})
MAX_RESPONSE_BYTES = 2_000_000
MAX_ARTIFACTS = 250
SELLER_CAPABILITIES = frozenset({
    "agent-orchestration",
    "cross-review",
    "multi-agent-synthesis",
    "nested-hive",
    "provenance",
    "reviewed-problem-solving",
})


class MarketHiveBridgeError(RuntimeError):
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
            raise MarketHiveBridgeError("empty MCP event stream")
        message = json.loads(messages[-1])
    else:
        message = json.loads(raw)
    if message.get("error"):
        raise MarketHiveBridgeError(
            "MCP error: " + str(message["error"].get("message") or "unknown"))
    result = message.get("result") or {}
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content") or []
    if content and isinstance(content[0], dict):
        raw_text = content[0].get("text")
        if isinstance(raw_text, str):
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                return parsed
    raise MarketHiveBridgeError("MCP result contains no structured object")


def default_market_call(tool: str, arguments: dict, *,
                        market_url: str = INTERNAL_MARKET_URL,
                        timeout_s: int = 20) -> dict:
    if market_url not in ALLOWED_MARKET_URLS:
        raise MarketHiveBridgeError("market URL is not allowlisted")
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
            "user-agent": "viridis-market-hive-bridge/0.1",
        })
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise MarketHiveBridgeError("Agent Market response exceeds cap")
        return _decode_mcp_response(
            response.headers.get("content-type", ""),
            raw.decode("utf-8", "replace"))


class MarketSigner:
    def __init__(self, private_key: Ed25519PrivateKey):
        self._private_key = private_key

    @classmethod
    def from_env(
            cls, name: str = "VIRIDIS_AGENT_MARKET_PRIVATE_KEY_B64"
            ) -> "MarketSigner":
        raw = os.getenv(name, "").strip()
        if not raw:
            raise MarketHiveBridgeError(f"{name} is not configured")
        try:
            decoded = base64.urlsafe_b64decode(
                raw + "=" * (-len(raw) % 4))
            return cls(Ed25519PrivateKey.from_private_bytes(decoded))
        except Exception as exc:
            raise MarketHiveBridgeError(
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


class MarketHiveBridge:
    """Durable, at-most-one-progress-step Market seller lifecycle."""

    def __init__(
            self, store, hive_core, payment_gate,
            market_call: Callable[[str, dict], dict] = default_market_call,
            signer: Optional[MarketSigner] = None,
            public_base: str = "https://mcp.viridisconservation.com",
            now_fn: Callable[[], datetime] = (
                lambda: datetime.now(timezone.utc))) -> None:
        # StateStore excludes ``config`` by contract. All live dependencies
        # stay here; only the plain-data state below is snapshotted.
        self.config = {
            "store": store,
            "hive_core": hive_core,
            "payment_gate": payment_gate,
            "market_call": market_call,
            "signer": signer,
            "public_base": public_base.rstrip("/"),
            "now_fn": now_fn,
        }
        self.state: Dict[str, Any] = {
            "jobs": {},
            "artifacts": {},
            "runs": 0,
            "last_run_at": None,
            "last_error": None,
        }

    @staticmethod
    def _payload(result: dict) -> dict:
        if result.get("status") != "ok":
            raise MarketHiveBridgeError(
                str(result.get("message") or result.get("error")
                    or "Agent Market call failed"))
        data = result.get("data")
        if not isinstance(data, dict):
            raise MarketHiveBridgeError("Market response has no data object")
        return data

    @property
    def signer(self) -> MarketSigner:
        signer = self.config.get("signer")
        if signer is None:
            signer = MarketSigner.from_env()
            self.config["signer"] = signer
        return signer

    def _market_write(self, action: str, tool: str, body: dict) -> dict:
        auth = self.signer.auth(action, SELLER_ID, body)
        return self._payload(self.config["market_call"](
            tool, {"agent_id": SELLER_ID, **body, "auth": auth}
            if action == "read_inbox" else
            {"seller_id": SELLER_ID, **body, "auth": auth}))

    def _read_work_ids(self) -> list[str]:
        body = {
            "limit": 100,
            "after": "",
            "idempotency_key": "hive-inbox-" + uuid.uuid4().hex,
        }
        inbox = self._market_write(
            "read_inbox", "read_agent_inbox", body)
        ids = {
            str(item.get("work_id"))
            for item in inbox.get("messages") or []
            if isinstance(item, dict) and item.get("work_id")
        }
        ids.update(self.state["jobs"])
        return sorted(ids)

    def _work_detail(self, work_id: str) -> dict:
        return self._payload(self.config["market_call"](
            "get_work", {"work_id": work_id}))

    def _validate_candidate(self, detail: dict) -> tuple[dict, dict, dict]:
        if detail.get("status") != "AWARDED":
            raise MarketHiveBridgeError("work is not awaiting delivery")
        if detail.get("funding_status") != "VERIFIED":
            raise MarketHiveBridgeError("work funding is not Hub-verified")
        if detail.get("delivery") is not None:
            raise MarketHiveBridgeError("work already has a delivery")
        buyer = str(detail.get("buyer_id") or "")
        if (not buyer or buyer == SELLER_ID
                or buyer.startswith("viridis-")
                or buyer.startswith("viridis:")):
            raise MarketHiveBridgeError("buyer is common-control or invalid")
        required = detail.get("required_capabilities")
        if (not isinstance(required, list) or not required
                or not set(required).issubset(SELLER_CAPABILITIES)):
            raise MarketHiveBridgeError("work capabilities are not Hive-safe")
        deadline = datetime.fromisoformat(
            str(detail.get("delivery_deadline") or "").replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if deadline <= self.config["now_fn"]():
            raise MarketHiveBridgeError("delivery deadline has passed")
        offers = [
            item for item in detail.get("offers") or []
            if isinstance(item, dict)
            and item.get("offer_id") == detail.get("awarded_offer_id")]
        if len(offers) != 1:
            raise MarketHiveBridgeError("awarded offer is missing or ambiguous")
        offer = offers[0]
        settlement = offer.get("settlement") or {}
        if (offer.get("seller_id") != SELLER_ID
                or offer.get("status") != "AWARDED"
                or offer.get("amount_minor") != SERVICE_PRICE_MINOR
                or offer.get("currency") != "USD"
                or settlement.get("rail") != "viridis_cash_escrow"
                or settlement.get("payee_id") != PAYEE_ID):
            raise MarketHiveBridgeError("awarded terms do not match Hive")
        receipt = detail.get("funding_receipt")
        primitive = (receipt or {}).get("money_primitive") or {}
        if (not isinstance(receipt, dict)
                or receipt.get("verified") is not True
                or receipt.get("funding_status") != "VERIFIED"
                or receipt.get("work_id") != detail.get("work_id")
                or primitive.get("primitive")
                != "stripe_checkout_escrow_funding"
                or primitive.get("escrow_state") != "FUNDED"
                or primitive.get("payee") != PAYEE_ID
                or primitive.get("amount_minor") != SERVICE_PRICE_MINOR):
            raise MarketHiveBridgeError("funding receipt is not exact")
        return offer, receipt, primitive

    @staticmethod
    def _solve_payload(detail: dict) -> dict:
        work_id = str(detail["work_id"])
        seed = int(hashlib.sha256(work_id.encode()).hexdigest()[:8], 16)
        return {
            "action": "solve",
            "problem": str(detail["description"]),
            "budget_minor": SERVICE_PRICE_MINOR,
            "depth": 0,
            "redundancy": 2,
            "accept_threshold": 0.6,
            "seed": seed,
            "fee_bps": 0,
            "request_id": "market-hive-" + hashlib.sha256(
                work_id.encode()).hexdigest()[:32],
        }

    @staticmethod
    def _binding(detail: dict, receipt: dict, primitive: dict) -> dict:
        return {
            "work_id": str(detail["work_id"]),
            "escrow_id": str(primitive["escrow_id"]),
            "funding_event_id": str(receipt["event_id"]),
            "event_sha256": str(receipt["event_sha256"]),
            "amount_minor": SERVICE_PRICE_MINOR,
            "currency": "USD",
            "payee": PAYEE_ID,
        }

    def _persist(self) -> bool:
        return bool(self.config["store"].save("market_hive_bridge", self))

    def _artifact(self, detail: dict, solve: dict, audit: dict) -> tuple[str, str]:
        artifact = {
            "spec_version": "viridis-market-hive-delivery-v1",
            "work_id": detail["work_id"],
            "seller_id": SELLER_ID,
            "buyer_id": detail["buyer_id"],
            "source_description_sha256": hashlib.sha256(
                str(detail["description"]).encode()).hexdigest(),
            "hive_result": solve["data"],
            "hive_audit": audit["data"],
            "commercial_boundary": (
                "delivery under a still-FUNDED escrow; not revenue or "
                "settlement until buyer acceptance and verified release"),
        }
        content = _stable(artifact)
        return hashlib.sha256(content.encode()).hexdigest(), content

    def _store_artifact(self, digest: str, content: str) -> None:
        artifacts = self.state["artifacts"]
        artifacts[digest] = content
        if len(artifacts) > MAX_ARTIFACTS:
            referenced = {
                row.get("artifact_sha256")
                for row in self.state["jobs"].values()
                if isinstance(row, dict)
            }
            for key in list(artifacts):
                if len(artifacts) <= MAX_ARTIFACTS:
                    break
                if key not in referenced:
                    artifacts.pop(key, None)

    async def _execute(self, detail: dict, receipt: dict,
                       primitive: dict) -> dict:
        work_id = str(detail["work_id"])
        payload = self._solve_payload(detail)
        binding = self._binding(detail, receipt, primitive)
        reserved = self.config["payment_gate"].reserve_market_payment(
            SERVICE_NAME, binding, payload)
        if reserved.get("status") != "ok":
            raise MarketHiveBridgeError(
                "payment hold refused: " + str(reserved.get("reason")))
        row = self.state["jobs"].setdefault(work_id, {})
        row.update({
            "stage": "PAYMENT_RESERVED",
            "binding": binding,
            "request_id": payload["request_id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if not self._persist():
            raise MarketHiveBridgeError(
                "bridge reservation state was not durable")
        call = {**payload, "_market_payment_token": reserved["token"]}
        solve = await self.config["hive_core"].process(call)
        if (not isinstance(solve, dict) or solve.get("status") != "ok"
                or (solve.get("data") or {}).get("state") != "COMPLETE"):
            row.update({"stage": "SOLVE_FAILED", "solve_result": solve})
            self._persist()
            raise MarketHiveBridgeError("Hive solve did not complete")
        audit = await self.config["hive_core"].process({
            "action": "audit_job", "job_id": solve["data"]["job_id"]})
        if not isinstance(audit, dict) or audit.get("status") != "ok":
            row.update({"stage": "AUDIT_FAILED"})
            self._persist()
            raise MarketHiveBridgeError("Hive audit was unavailable")
        digest, content = self._artifact(detail, solve, audit)
        self._store_artifact(digest, content)
        row.update({
            "stage": "ARTIFACT_READY",
            "artifact_sha256": digest,
            "hive_job_id": solve["data"]["job_id"],
            "audit_sha256": solve["data"]["audit_sha256"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if not self._persist():
            raise MarketHiveBridgeError("delivery artifact was not durable")
        return row

    def _deliver(self, detail: dict, row: dict) -> dict:
        work_id = str(detail["work_id"])
        digest = str(row["artifact_sha256"])
        body = {
            "work_id": work_id,
            "artifact_url": (
                f"{self.config['public_base']}/market-artifacts/{digest}.json"),
            "content_sha256": digest,
            "summary": (
                "Completed cost-bounded Hive synthesis with reviewer "
                "separation and a content-addressed full audit."),
            "idempotency_key": "hive-delivery-" + hashlib.sha256(
                work_id.encode()).hexdigest()[:24],
        }
        delivered = self._market_write(
            "submit_delivery", "submit_delivery", body)
        row.update({
            "stage": "DELIVERED",
            "delivery_id": delivered["delivery_id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if not self._persist():
            # Market idempotency still makes the next delivery retry safe.
            raise MarketHiveBridgeError(
                "delivery was accepted by Market but local state is not durable")
        return delivered

    async def run_once(self, *, apply: bool = False) -> dict:
        if not apply:
            return {
                "status": "ok",
                "mode": "read_only",
                "execution_started": False,
                "jobs_tracked": len(self.state["jobs"]),
                "artifacts": len(self.state["artifacts"]),
                "commercial_boundary": (
                    "no Market inbox mutation, model call, delivery, "
                    "settlement, or money movement"),
            }
        if os.getenv("HIVE_MARKET_LIFECYCLE_ENABLED", "").lower() not in {
                "1", "true", "yes", "on"}:
            return {
                "status": "ok", "mode": "apply_refused",
                "reason": "HIVE_MARKET_LIFECYCLE_ENABLED is not enabled",
                "execution_started": False,
            }
        self.state["runs"] += 1
        self.state["last_run_at"] = datetime.now(timezone.utc).isoformat()
        try:
            for work_id in self._read_work_ids():
                detail = self._work_detail(work_id)
                try:
                    _, receipt, primitive = self._validate_candidate(detail)
                except MarketHiveBridgeError:
                    continue
                row = self.state["jobs"].get(work_id) or {}
                if not row.get("artifact_sha256"):
                    row = await self._execute(detail, receipt, primitive)
                delivered = self._deliver(detail, row)
                self.state["last_error"] = None
                return {
                    "status": "ok", "mode": "apply",
                    "work_id": work_id,
                    "execution_started": True,
                    "delivery": delivered,
                    "escrow_state": "FUNDED",
                    "money_movement": "none before buyer acceptance",
                }
            self.state["last_error"] = None
            self._persist()
            return {
                "status": "ok", "mode": "apply",
                "result": "no_verified_funded_hive_work",
                "execution_started": False,
            }
        except Exception as exc:
            self.state["last_error"] = (
                f"{type(exc).__name__}: {str(exc)[:300]}")
            self._persist()
            return {
                "status": "error",
                "error_type": "market_hive_bridge_failed",
                "message": str(exc)[:300],
                "execution_retry_safe": True,
            }

    def artifact_bytes(self, digest: str) -> Optional[bytes]:
        content = self.state["artifacts"].get(digest)
        return content.encode("utf-8") if isinstance(content, str) else None

    def status(self) -> dict:
        stages: Dict[str, int] = {}
        for row in self.state["jobs"].values():
            stage = str(row.get("stage") or "UNKNOWN")
            stages[stage] = stages.get(stage, 0) + 1
        return {
            "enabled": os.getenv(
                "HIVE_MARKET_LIFECYCLE_ENABLED", "").lower()
            in {"1", "true", "yes", "on"},
            "jobs": len(self.state["jobs"]),
            "stages": stages,
            "artifacts": len(self.state["artifacts"]),
            "runs": self.state["runs"],
            "last_run_at": self.state["last_run_at"],
            "last_error": self.state["last_error"],
            "buyer_acceptance_releases_escrow": True,
        }
