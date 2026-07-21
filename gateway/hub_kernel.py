"""Viridis Hub Kernel — verified composition for the agent market.

The market owns signed discovery/workflow state.  The gateway already owns the
trusted payment, identity, reputation, notary, relay, and compute ledgers.  This
module is the narrow authenticated seam between them; it creates no third money
rail and holds no buyer key.

HK1 only HMAC-authenticated market events inside a five-minute window enter.
HK2 a settlement reference can complete at most one market work order.
HK3 x402 is verified from the gateway's settled receipt or Base USDC logs.
HK4 cash escrow is verified from custody funding plus an executed real rail.
HK5 trust outcomes are recorded only after HK3/HK4 succeeds and exactly once.
HK6 delivery proofs and compute evidence are never inferred or fabricated.
HK7 every accepted event is durable before the verification receipt is returned.
HK8 failures are fail-closed and retryable; they never execute a market job.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger("viridis.hub_kernel")
USDC_BASE_MAINNET = "0x833589fcd6eb6e08f4c7c32d4f71b54bda02913"
TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef")
TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
EVENT_RE = re.compile(r"^hub_[0-9a-f]{64}$")
MAX_BODY = 1_000_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


class HubError(RuntimeError):
    def __init__(self, message: str, *, error_type: str = "verification_failed",
                 status_code: int = 409, retryable: bool = False):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.retryable = retryable


@dataclass
class HubState:
    receipts: Dict[str, dict] = field(default_factory=dict)
    references: Dict[str, str] = field(default_factory=dict)
    identity_profiles: Dict[str, str] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)


class HubKernel:
    def __init__(self, store, cores: Dict[str, Any], custody, *,
                 secret: Optional[str] = None,
                 persist_key: str = "hub_kernel",
                 rpc_url: Optional[str] = None,
                 rpc_opener: Callable[..., Any] = urllib.request.urlopen,
                 allow_test_settlements: Optional[bool] = None):
        self.store = store
        self.cores = cores
        self.custody = custody
        self.persist_key = persist_key
        self.secret = str(secret if secret is not None else
                          os.environ.get("HUB_EVENT_SECRET", ""))
        self.rpc_url = str(rpc_url if rpc_url is not None else
                           os.environ.get("BASE_RPC_URL", "https://mainnet.base.org"))
        self.rpc_opener = rpc_opener
        self.allow_test_settlements = (
            str(os.environ.get("HUB_ALLOW_TEST_SETTLEMENTS", "0")).lower()
            in {"1", "true", "yes", "on"}
            if allow_test_settlements is None else bool(allow_test_settlements))
        self.state = HubState()
        try:
            self.store.restore(self.persist_key, self.state)
        except Exception:
            logger.exception("hub state restore failed")

    @property
    def enabled(self) -> bool:
        return len(self.secret) >= 32

    def authenticate(self, body: bytes, timestamp: str, signature: str,
                     *, now_epoch: Optional[int] = None) -> None:
        if not self.enabled:
            raise HubError("Hub event authentication is not configured",
                           error_type="hub_disabled", status_code=503,
                           retryable=True)
        try:
            issued = int(timestamp)
        except (TypeError, ValueError) as exc:
            raise HubError("invalid Hub timestamp", error_type="unauthorized",
                           status_code=401) from exc
        current = int(time.time()) if now_epoch is None else int(now_epoch)
        if abs(current - issued) > 300:
            raise HubError("stale Hub event", error_type="unauthorized",
                           status_code=401)
        expected = hmac.new(
            self.secret.encode(), str(timestamp).encode() + b"." + body,
            hashlib.sha256).hexdigest()
        if not isinstance(signature, str) or not hmac.compare_digest(
                signature.lower(), expected):
            raise HubError("invalid Hub signature", error_type="unauthorized",
                           status_code=401)

    @staticmethod
    def _required_dict(payload: dict, name: str) -> dict:
        value = payload.get(name)
        if not isinstance(value, dict):
            raise HubError(f"{name} must be an object", error_type="bad_event",
                           status_code=400)
        return value

    def _validate_event(self, payload: dict) -> tuple[str, str, int]:
        if not isinstance(payload, dict) or payload.get("spec_version") != \
                "viridis-hub-event-v1":
            raise HubError("unsupported Hub event", error_type="bad_event",
                           status_code=400)
        event_id = str(payload.get("event_id") or "")
        if not EVENT_RE.fullmatch(event_id):
            raise HubError("invalid event_id", error_type="bad_event",
                           status_code=400)
        work = self._required_dict(payload, "work")
        settlement = self._required_dict(payload, "settlement")
        self._required_dict(payload, "offer")
        self._required_dict(payload, "delivery")
        self._required_dict(payload, "buyer_profile")
        self._required_dict(payload, "seller_profile")
        work_id = str(work.get("work_id") or "")
        reference = str(settlement.get("reference") or "")
        try:
            amount_minor = int(settlement.get("amount_minor"))
        except (TypeError, ValueError) as exc:
            raise HubError("invalid settlement amount", error_type="bad_event",
                           status_code=400) from exc
        expected = "hub_" + hashlib.sha256(
            f"{work_id}|{reference}".encode()).hexdigest()
        if event_id != expected or not work_id or amount_minor <= 0:
            raise HubError("event binding is invalid", error_type="bad_event",
                           status_code=400)
        return event_id, reference, amount_minor

    def _local_x402(self, payload: dict, tx_hash: str,
                    amount_atomic: int) -> Optional[dict]:
        settlement = payload["offer"]["settlement"]
        endpoint = urllib.parse.urlsplit(str(settlement.get("payment_endpoint") or ""))
        parts = [part for part in endpoint.path.split("/") if part]
        if (endpoint.hostname != "mcp.viridisconservation.com" or len(parts) != 3
                or parts[0] != "x402"):
            return None
        agent, tool = parts[1], parts[2]
        core = self.cores.get(agent)
        gate = getattr(core, "_payment_gate_state", None) if core else None
        consumed = gate.get("consumed_x402", {}) if isinstance(gate, dict) else {}
        for record in consumed.values():
            if not isinstance(record, dict):
                continue
            if str(record.get("tx_hash") or "").lower() != tx_hash.lower():
                continue
            if int(record.get("amount_atomic") or 0) != amount_atomic:
                raise HubError("x402 receipt amount does not match the award")
            route = str(record.get("route") or f"{agent}/{tool}")
            if route != f"{agent}/{tool}":
                raise HubError("x402 receipt route does not match the award")
            return {"primitive": "x402_settlement", "source": "gateway_ledger",
                    "tx_hash": tx_hash.lower(), "amount_atomic": amount_atomic,
                    "network": record.get("network") or "eip155:8453",
                    "route": route, "payer_wallet": record.get("payer_wallet"),
                    "settled_at": record.get("timestamp")}
        return None

    def _rpc_receipt(self, tx_hash: str) -> dict:
        body = json.dumps({"jsonrpc": "2.0", "id": 1,
                           "method": "eth_getTransactionReceipt",
                           "params": [tx_hash]}).encode()
        request = urllib.request.Request(
            self.rpc_url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "User-Agent": "viridis-hub-kernel/1"})
        try:
            with self.rpc_opener(request, timeout=10) as response:
                raw = response.read(MAX_BODY)
            payload = json.loads(raw)
        except Exception as exc:
            raise HubError(f"Base receipt lookup unavailable: {type(exc).__name__}",
                           error_type="rpc_unavailable", status_code=503,
                           retryable=True) from exc
        receipt = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(receipt, dict):
            raise HubError("Base transaction receipt not found", retryable=True)
        return receipt

    def _chain_x402(self, payload: dict, tx_hash: str,
                    amount_atomic: int) -> dict:
        awarded = payload["offer"]["settlement"]
        if str(awarded.get("network") or "") != "eip155:8453" \
                or str(awarded.get("asset") or "").upper() != "USDC":
            raise HubError("only Base-mainnet USDC x402 is independently verified")
        payee = str(awarded.get("payee_address") or "").lower()
        if not ADDRESS_RE.fullmatch(payee):
            raise HubError("x402 award lacks a verified payee_address")
        receipt = self._rpc_receipt(tx_hash)
        if str(receipt.get("status") or "").lower() != "0x1":
            raise HubError("Base transaction did not succeed")
        matched = False
        for log in receipt.get("logs") or []:
            topics = log.get("topics") or [] if isinstance(log, dict) else []
            if (not isinstance(log, dict)
                    or str(log.get("address") or "").lower() != USDC_BASE_MAINNET
                    or len(topics) < 3
                    or str(topics[0]).lower() != TRANSFER_TOPIC
                    or str(topics[2]).lower()[-40:] != payee[2:]):
                continue
            try:
                amount = int(str(log.get("data") or "0x0"), 16)
            except ValueError:
                continue
            if amount == amount_atomic:
                matched = True
                break
        if not matched:
            raise HubError("no exact USDC Transfer to the awarded payee was found")
        return {"primitive": "usdc_transfer", "source": "base_rpc",
                "tx_hash": tx_hash.lower(), "amount_atomic": amount_atomic,
                "network": "eip155:8453", "asset": USDC_BASE_MAINNET,
                "payee_address": payee,
                "block_number": receipt.get("blockNumber")}

    def _verify_x402(self, payload: dict, amount_minor: int) -> dict:
        settlement = payload["settlement"]
        tx_hash = str(settlement.get("reference") or "")
        if not TX_RE.fullmatch(tx_hash):
            raise HubError("x402 reference must be a transaction hash")
        if str(settlement.get("currency") or "").upper() not in {"USD", "USDC"}:
            raise HubError("x402 currency must be USD or USDC")
        amount_atomic = amount_minor * 10_000
        local = self._local_x402(payload, tx_hash, amount_atomic)
        return local or self._chain_x402(payload, tx_hash, amount_atomic)

    def _verify_cash(self, payload: dict, amount_minor: int) -> dict:
        settlement = payload["settlement"]
        escrow_id = str(settlement.get("reference") or "")
        funded = getattr(getattr(self.custody, "state", None), "funded", {}) or {}
        evidence = funded.get(escrow_id)
        if not isinstance(evidence, dict):
            raise HubError("cash escrow has no pull-verified funding evidence")
        if not self.allow_test_settlements and evidence.get("livemode") is not True:
            raise HubError("test-mode escrow cannot count as production earnings")
        status = self.custody.escrow.process_sync(
            {"action": "status", "escrow_id": escrow_id})
        escrow = status.get("data") if isinstance(status, dict) else None
        if not isinstance(escrow, dict) or escrow.get("state") != "RELEASED":
            raise HubError("cash escrow is not RELEASED")
        awarded = payload["offer"]["settlement"]
        if (int(escrow.get("amount_minor") or 0) != amount_minor
                or str(escrow.get("payee") or "") != str(awarded.get("payee_id") or "")):
            raise HubError("cash escrow terms do not match the awarded offer")
        instruction = (getattr(getattr(self.custody, "state", None),
                               "instructions", {}) or {}).get(escrow_id)
        if not isinstance(instruction, dict) or instruction.get("executed") is not True:
            raise HubError("cash settlement instruction is not executed",
                           retryable=True)
        primitive = {"source": "escrow_custody", "escrow_id": escrow_id,
                     "session_id": evidence.get("session_id"),
                     "livemode": bool(evidence.get("livemode")),
                     "amount_minor": amount_minor,
                     "instruction_type": instruction.get("type")}
        if instruction.get("type") == "revenue_recognized":
            if int(instruction.get("revenue_minor") or 0) != amount_minor:
                raise HubError("revenue recognition amount mismatch")
            primitive.update({"primitive": "stripe_checkout_revenue",
                              "revenue_minor": amount_minor})
            return primitive
        if instruction.get("rail") == "connect" and instruction.get("transfer_id"):
            primitive.update({"primitive": "stripe_connect_transfer",
                              "transfer_id": instruction["transfer_id"],
                              "net_minor": instruction.get("net_minor")})
            return primitive
        raise HubError("manual payout lacks independently verifiable licensed-rail evidence")

    async def _verify_delivery_proofs(self, payload: dict) -> dict:
        delivery = payload["delivery"]
        proofs = delivery.get("proofs") or {}
        result = {"digest": delivery["content_sha256"],
                  "buyer_digest_acceptance": True,
                  "notary": None, "verified_relay": None}
        commitment = proofs.get("notary_commitment_id")
        if commitment:
            response = await self.cores["notary"].process({
                "action": "verify", "commitment_id": commitment,
                "content_digest": delivery["content_sha256"]})
            if response.get("status") != "ok" or \
                    (response.get("data") or {}).get("valid") is not True:
                raise HubError("Notary commitment does not verify the delivery")
            result["notary"] = {"commitment_id": commitment, "valid": True}
        receipt_id = proofs.get("verified_receipt_id")
        if receipt_id:
            receipt_result = await self.cores["verified"].process(
                {"action": "get_receipt", "receipt_id": receipt_id})
            receipt = receipt_result.get("data") if isinstance(receipt_result, dict) else None
            if (not isinstance(receipt, dict)
                    or receipt.get("response_hash") != delivery["content_sha256"]):
                raise HubError("Verified Relay receipt does not bind the delivery digest")
            chain = await self.cores["verified"].process(
                {"action": "verify_receipts", "service_id": receipt["service_id"]})
            if chain.get("status") != "ok" or \
                    (chain.get("data") or {}).get("valid") is not True:
                raise HubError("Verified Relay receipt chain is invalid")
            result["verified_relay"] = {"receipt_id": receipt_id,
                                         "receipt_hash": receipt.get("receipt_hash"),
                                         "valid": True}
        return result

    async def _identity(self, profile: dict) -> dict:
        market_id = str(profile["agent_id"])
        subject = f"market:{market_id}"
        profile_sha = str(profile.get("profile_sha256") or "")
        existing = await self.cores["identity"].process(
            {"action": "resolve", "agent_id": subject})
        if (existing.get("status") == "ok"
                and self.state.identity_profiles.get(subject) == profile_sha):
            return existing["data"]
        result = await self.cores["identity"].process({
            "action": "register", "agent_id": subject,
            "name": profile.get("name") or market_id,
            "capabilities": profile.get("capabilities") or ["agent-service"],
            "endpoint": profile.get("endpoint") or "",
            "pubkey": profile.get("public_key_b64") or profile_sha,
            "pricing": profile.get("payment") or {},
        })
        if result.get("status") != "ok":
            raise HubError("fleet identity registration failed",
                           error_type="composition_failed", status_code=503,
                           retryable=True)
        self.state.identity_profiles[subject] = profile_sha
        return result["data"]

    async def _trust(self, event_id: str, work_id: str, buyer_id: str,
                     seller_id: str) -> dict:
        marker = f"hub:{event_id}"
        out = {}
        for subject, kind, counterparty in (
                (f"market:{seller_id}", "delivered", f"market:{buyer_id}"),
                (f"market:{buyer_id}", "success", f"market:{seller_id}")):
            state = getattr(self.cores["trust"], "_subjects", {}).get(subject)
            already = bool(state and any(
                getattr(item, "note", "") == marker for item in state.outcomes))
            if not already:
                recorded = await self.cores["trust"].process({
                    "action": "record_outcome", "agent_id": subject,
                    "kind": kind, "weight": 1.0, "counterparty": counterparty,
                    "note": marker})
                if recorded.get("status") != "ok":
                    raise HubError("trust outcome persistence failed",
                                   error_type="composition_failed", status_code=503,
                                   retryable=True)
            state = getattr(self.cores["trust"], "_subjects", {}).get(subject)
            claim = f"verified-market-settlement:{work_id}"
            attestation = next((item for item in (state.attestations if state else [])
                                if getattr(item, "claim", "") == claim), None)
            if attestation is None:
                issued = await self.cores["trust"].process({
                    "action": "attest", "agent_id": subject, "claim": claim})
                if issued.get("status") != "ok":
                    raise HubError("trust attestation persistence failed",
                                   error_type="composition_failed", status_code=503,
                                   retryable=True)
                out[subject] = issued["data"]
            else:
                out[subject] = {"attestation_id": attestation.hash,
                                "subject": subject, "claim": claim,
                                "score": attestation.score, "tier": attestation.tier}
        return out

    async def _carbon(self, payload: dict) -> Optional[dict]:
        evidence = payload["delivery"].get("compute_evidence") or {}
        if not evidence:
            return None
        work_id = payload["work"]["work_id"]
        seller = f"market:{payload['offer']['seller_id']}"
        record = {"action": "record_work", "agent_id": seller,
                  "entry_id": f"market-work:{work_id}",
                  "task": f"market delivery {work_id}", **evidence}
        record.pop("source", None)
        created = await self.cores["compute-ledger"].process(record)
        if created.get("status") != "ok":
            raise HubError("compute evidence failed physical validation")
        receipt = await self.cores["compute-ledger"].process(
            {"action": "carbon_receipt", "entry_id": record["entry_id"]})
        if receipt.get("status") != "ok":
            raise HubError("x402-C receipt generation failed",
                           error_type="composition_failed", status_code=503,
                           retryable=True)
        return {**receipt["data"], "evidence_source": evidence.get("source")}

    async def handle_event(self, payload: dict) -> dict:
        event_id, reference, amount_minor = self._validate_event(payload)
        payload_sha = hashlib.sha256(_stable(payload).encode()).hexdigest()
        prior = self.state.receipts.get(event_id)
        if prior:
            if prior.get("event_sha256") != payload_sha:
                raise HubError("event_id reused with different content")
            return {**prior, "duplicate": True}
        other = self.state.references.get(reference.lower())
        if other and other != event_id:
            raise HubError("settlement reference already used by another work order")
        rail = str(payload["settlement"].get("rail") or "")
        if rail == "x402":
            primitive = self._verify_x402(payload, amount_minor)
        elif rail == "viridis_cash_escrow":
            primitive = self._verify_cash(payload, amount_minor)
        else:
            raise HubError("unsupported settlement rail")
        delivery_proof = await self._verify_delivery_proofs(payload)
        buyer_identity = await self._identity(payload["buyer_profile"])
        seller_identity = await self._identity(payload["seller_profile"])
        trust = await self._trust(
            event_id, payload["work"]["work_id"],
            payload["work"]["buyer_id"], payload["offer"]["seller_id"])
        carbon = await self._carbon(payload)
        receipt = {
            "verified": True, "duplicate": False, "event_id": event_id,
            "event_sha256": payload_sha, "work_id": payload["work"]["work_id"],
            "verified_at": _now(), "money_primitive": primitive,
            "delivery_proof": delivery_proof,
            "identities": {"buyer": buyer_identity, "seller": seller_identity},
            "trust_attestations": trust, "x402c": carbon,
            "mission_accounting": {
                "compute_evidence": "recorded" if carbon else "not_supplied",
                "conservation_allocation_minor": 0,
                "note": ("mission evidence is recorded without inventing an "
                         "unratified revenue-allocation percentage"),
            },
        }
        self.state.receipts[event_id] = receipt
        self.state.references[reference.lower()] = event_id
        try:
            saved = bool(self.store.save(self.persist_key, self.state))
        except Exception:
            saved = False
        if not saved:
            self.state.receipts.pop(event_id, None)
            self.state.references.pop(reference.lower(), None)
            raise HubError("Hub receipt was not durable", error_type="persist_failed",
                           status_code=503, retryable=True)
        return receipt

    def status(self) -> dict:
        receipts = list(self.state.receipts.values())
        return {
            "enabled": self.enabled,
            "spec_version": "viridis-hub-kernel-v1",
            "verified_settlements": len(receipts),
            "verified_volume_minor": sum(int(
                item.get("money_primitive", {}).get("amount_minor")
                or int(item.get("money_primitive", {}).get("amount_atomic", 0)) // 10_000)
                for item in receipts),
            "x402c_receipts": sum(item.get("x402c") is not None for item in receipts),
            "identity_bindings": len(self.state.identity_profiles),
            "errors": dict(self.state.errors),
            "payment_credentials": "none added; reuses gateway-owned evidence",
        }


def make_hub_route(kernel: HubKernel):
    async def handler(request):
        from starlette.responses import JSONResponse
        body = await request.body()
        if len(body) > MAX_BODY:
            return JSONResponse({"verified": False, "error": "event too large"},
                                status_code=413)
        try:
            kernel.authenticate(
                body, request.headers.get("x-viridis-hub-timestamp", ""),
                request.headers.get("x-viridis-hub-signature", ""))
            payload = json.loads(body)
            result = await kernel.handle_event(payload)
            return JSONResponse(result, status_code=200)
        except HubError as exc:
            return JSONResponse({"verified": False, "error_type": exc.error_type,
                                 "reason": str(exc), "retryable": exc.retryable},
                                status_code=exc.status_code)
        except (TypeError, ValueError):
            return JSONResponse({"verified": False, "error_type": "bad_event",
                                 "reason": "event body must be JSON"},
                                status_code=400)
        except Exception as exc:
            logger.exception("Hub event failed")
            return JSONResponse({"verified": False, "error_type": "internal_error",
                                 "reason": type(exc).__name__, "retryable": True},
                                status_code=503)
    return handler


__all__ = ["HubError", "HubKernel", "HubState", "make_hub_route"]
