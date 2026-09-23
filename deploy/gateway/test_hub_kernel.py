"""HK1-HK8 tests for the market-to-fleet Hub composition boundary."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from hub_kernel import HubError, HubKernel  # noqa: E402


TX = "0x" + "ab" * 32
PAYEE = "0xfef2e570b645eb720ee6c589d27450810982f329"


class Store:
    def __init__(self):
        self.saved = {}

    def restore(self, name, state):
        if name in self.saved:
            state.__dict__.update(copy.deepcopy(self.saved[name]))
            return True
        return False

    def save(self, name, state):
        self.saved[name] = copy.deepcopy(state.__dict__)
        return True


class Identity:
    def __init__(self):
        self.items = {}

    async def process(self, data):
        ident = data.get("agent_id")
        if data["action"] == "resolve":
            if ident not in self.items:
                return {"status": "error"}
            return {"status": "ok", "data": self.items[ident]}
        item = {"agent_id": ident,
                "did": "did:viridis:" + hashlib.sha256(ident.encode()).hexdigest()[:16],
                "name": data["name"], "capabilities": data["capabilities"],
                "endpoint": data["endpoint"]}
        self.items[ident] = item
        return {"status": "ok", "data": item}


@dataclass
class Outcome:
    note: str


@dataclass
class Attestation:
    claim: str
    hash: str
    score: float = 0.75
    tier: str = "RELIABLE"


@dataclass
class Subject:
    outcomes: list = field(default_factory=list)
    attestations: list = field(default_factory=list)


class Trust:
    def __init__(self):
        self._subjects = {}

    async def process(self, data):
        subject = self._subjects.setdefault(data["agent_id"], Subject())
        if data["action"] == "record_outcome":
            subject.outcomes.append(Outcome(data["note"]))
            return {"status": "ok", "data": {"score": 0.75}}
        att = Attestation(
            data["claim"], hashlib.sha256(
                f"{data['agent_id']}:{data['claim']}".encode()).hexdigest())
        subject.attestations.append(att)
        return {"status": "ok", "data": {
            "attestation_id": att.hash, "subject": data["agent_id"],
            "claim": att.claim, "score": att.score, "tier": att.tier}}


class Compute:
    def __init__(self):
        self.entries = {}

    async def process(self, data):
        if data["action"] == "record_work":
            self.entries.setdefault(data["entry_id"], dict(data))
            return {"status": "ok", "data": self.entries[data["entry_id"]]}
        entry = self.entries.get(data["entry_id"])
        if entry is None:
            return {"status": "error"}
        carbon = {"version": "x402c/0.1", "entry_id": data["entry_id"],
                  "energy_j": entry["power_w"] * entry["duration_s"],
                  "g_co2e": 0.01}
        return {"status": "ok", "data": {"carbon": carbon,
                                             "entry_hash": "c" * 64}}


class PaidCore:
    def __init__(self, amount=250_000):
        self._payment_gate_state = {"consumed_x402": {"payment": {
            "tx_hash": TX, "amount_atomic": amount,
            "route": "regulatory-radar/scan_regulations",
            "network": "eip155:8453", "payer_wallet": "0x" + "11" * 20,
            "timestamp": "2026-07-20T20:00:00+00:00"}}}


class Escrow:
    def __init__(self, record):
        self.record = record

    def process_sync(self, data):
        return {"status": "ok", "data": dict(self.record)}


class Holder:
    pass


class Custody:
    def __init__(self, *, cash=False, instruction=None,
                 escrow_state="RELEASED", payer="buyer-agent",
                 payee="seller-agent", amount_minor=100,
                 currency="USD", livemode=True, evidence_amount=None):
        self.state = Holder()
        self.state.funded = ({"escrow_12345678": {
            "session_id": "cs_live_12345678",
            "amount_total": (amount_minor if evidence_amount is None
                             else evidence_amount),
            "livemode": livemode}} if cash else {})
        self.state.instructions = ({"escrow_12345678": instruction}
                                   if instruction else {})
        self.escrow = Escrow({
            "state": escrow_state, "amount_minor": amount_minor,
            "currency": currency, "payer": payer, "payee": payee,
        })


def profiles():
    common = {"description": "agent", "capabilities": ["agent-service"],
              "representative_queries": [], "endpoint": "https://agent.example/mcp",
              "public_key_b64": "", "auth_mode": "signed_ed25519",
              "provenance": "self_signed", "status": "ACTIVE", "version": 1,
              "profile_sha256": "d" * 64, "created_at": "x", "updated_at": "x",
              "expires_at": "x"}
    buyer = {**common, "agent_id": "buyer-agent", "did": "did:market:buyer",
             "name": "Buyer", "payment": {}}
    seller = {**common, "agent_id": "seller-agent", "did": "did:market:seller",
              "name": "Seller", "payment": {"payee_address": PAYEE}}
    return buyer, seller


def event(*, rail="x402", amount_minor=25, reference=TX,
          compute=True, settlement_override=None):
    buyer, seller = profiles()
    settlement = ({"rail": rail,
                   "payment_endpoint": ("https://mcp.viridisconservation.com/"
                                        "x402/regulatory-radar/scan_regulations"),
                   "network": "eip155:8453", "asset": "USDC",
                   "payee_address": PAYEE, "price_minor": 25}
                  if rail == "x402" else
                  {"rail": rail,
                   "payment_endpoint": "https://mcp.viridisconservation.com/payments/mcp",
                   "payee_id": "seller-agent"})
    settlement.update(settlement_override or {})
    work_id = "work_12345678"
    payload = {
        "spec_version": "viridis-hub-event-v1",
        "work": {"work_id": work_id, "buyer_id": "buyer-agent",
                 "title": "test", "description": "test",
                 "required_capabilities": ["agent-service"],
                 "budget_minor": amount_minor, "currency": "USD"},
        "offer": {"offer_id": "offer_12345678", "work_id": work_id,
                  "seller_id": "seller-agent", "amount_minor": amount_minor,
                  "currency": "USD", "proposal": "test", "delivery_seconds": 60,
                  "settlement": settlement, "status": "AWARDED",
                  "created_at": "x", "updated_at": "x"},
        "delivery": {"delivery_id": "delivery_12345678", "work_id": work_id,
                     "seller_id": "seller-agent",
                     "artifact_url": "https://artifact.example/result.json",
                     "content_sha256": "a" * 64, "summary": "done",
                     "compute_evidence": ({"power_w": 10.0, "duration_s": 2.0,
                                           "source": "seller_measured"}
                                          if compute else {}),
                     "proofs": {}, "created_at": "x", "accepted_at": "x"},
        "settlement": {"settlement_id": "settlement_12345678", "rail": rail,
                       "amount_minor": amount_minor, "currency": "USD",
                       "reference": reference,
                       "evidence_url": "https://basescan.org/tx/" + reference},
        "buyer_profile": buyer, "seller_profile": seller,
    }
    payload["event_id"] = "hub_" + hashlib.sha256(
        f"{work_id}|{reference}".encode()).hexdigest()
    return payload


def funding_event(*, amount_minor=100, reference="escrow_12345678",
                  payee_id="seller-agent"):
    buyer, seller = profiles()
    seller["payment"]["payee_id"] = payee_id
    work_id = "work_12345678"
    payload = {
        "spec_version": "viridis-hub-funding-event-v1",
        "work": {
            "work_id": work_id, "buyer_id": "buyer-agent",
            "title": "test", "description": "test",
            "required_capabilities": ["agent-service"],
            "budget_minor": amount_minor, "currency": "USD",
        },
        "offer": {
            "offer_id": "offer_12345678", "work_id": work_id,
            "seller_id": "seller-agent", "amount_minor": amount_minor,
            "currency": "USD", "proposal": "test", "delivery_seconds": 60,
            "settlement": {
                "rail": "viridis_cash_escrow",
                "payment_endpoint":
                    "https://mcp.viridisconservation.com/payments/mcp",
                "payee_id": payee_id,
            },
            "status": "AWARDED", "created_at": "x", "updated_at": "x",
        },
        "funding": {
            "rail": "viridis_cash_escrow",
            "amount_minor": amount_minor, "currency": "USD",
            "reference": reference,
        },
        "buyer_profile": buyer,
        "seller_profile": seller,
    }
    payload["event_id"] = "funding_" + hashlib.sha256(
        f"{work_id}|{reference}".encode()).hexdigest()
    return payload


def kernel(custody=None, *, store=None):
    return HubKernel(store or Store(), {
        "identity": Identity(), "trust": Trust(),
        "compute-ledger": Compute(), "notary": object(),
        "verified": object(), "regulatory-radar": PaidCore(),
    }, custody or Custody(), secret="s" * 32)


def run(coro):
    import asyncio
    return asyncio.run(coro)


def test_hmac_authentication_fails_closed_and_accepts_exact_body():
    hub = kernel()
    body = json.dumps(event(), sort_keys=True, separators=(",", ":")).encode()
    timestamp = "1000"
    signature = hmac.new(b"s" * 32, timestamp.encode() + b"." + body,
                         hashlib.sha256).hexdigest()
    hub.authenticate(body, timestamp, signature, now_epoch=1000)
    with pytest.raises(HubError, match="signature"):
        hub.authenticate(body + b" ", timestamp, signature, now_epoch=1000)
    with pytest.raises(HubError, match="stale"):
        hub.authenticate(body, timestamp, signature, now_epoch=1400)


def test_gateway_x402_receipt_composes_identity_trust_and_x402c_exactly_once():
    hub = kernel()
    first = run(hub.handle_event(event()))
    assert first["verified"] is True
    assert first["money_primitive"]["source"] == "gateway_ledger"
    assert first["money_primitive"]["amount_atomic"] == 250_000
    assert first["x402c"]["carbon"]["version"] == "x402c/0.1"
    assert first["mission_accounting"]["conservation_allocation_minor"] == 0
    second = run(hub.handle_event(event()))
    assert second["duplicate"] is True
    assert sum(len(s.outcomes) for s in hub.cores["trust"]._subjects.values()) == 2
    assert hub.status()["verified_settlements"] == 1


def test_post_award_cash_funding_is_verified_without_counting_earnings():
    custody = Custody(cash=True, escrow_state="FUNDED")
    hub = kernel(custody)
    first = run(hub.handle_event(funding_event()))

    assert first["verified"] is True
    assert first["funding_status"] == "VERIFIED"
    assert first["money_primitive"] == {
        "primitive": "stripe_checkout_escrow_funding",
        "source": "escrow_custody",
        "escrow_id": "escrow_12345678",
        "session_id": "cs_live_12345678",
        "livemode": True,
        "amount_minor": 100,
        "currency": "USD",
        "payer": "buyer-agent",
        "payee": "seller-agent",
        "escrow_state": "FUNDED",
    }
    assert hub.status()["verified_work_fundings"] == 1
    assert hub.status()["verified_work_funding_minor"] == 100
    assert hub.status()["verified_settlements"] == 0
    assert hub.cores["identity"].items == {}
    assert hub.cores["trust"]._subjects == {}

    replay = run(hub.handle_event(funding_event()))
    assert replay["duplicate"] is True
    assert hub.status()["verified_work_fundings"] == 1


@pytest.mark.parametrize(
    ("custody", "message"),
    [
        (Custody(cash=False, escrow_state="FUNDED"),
         "pull-verified funding"),
        (Custody(cash=True, escrow_state="OPEN"), "not FUNDED"),
        (Custody(cash=True, escrow_state="FUNDED", livemode=False),
         "test-mode"),
        (Custody(cash=True, escrow_state="FUNDED",
                 payer="other-buyer"), "terms do not match"),
        (Custody(cash=True, escrow_state="FUNDED",
                 payee="other-seller"), "terms do not match"),
        (Custody(cash=True, escrow_state="FUNDED",
                 evidence_amount=99), "funding evidence amount"),
    ],
)
def test_work_funding_fails_closed_without_exact_live_custody(
        custody, message):
    hub = kernel(custody)
    with pytest.raises(HubError, match=message):
        run(hub.handle_event(funding_event()))
    assert hub.status()["verified_work_fundings"] == 0
    assert hub.status()["verified_settlements"] == 0


def test_funding_reference_cannot_bind_two_work_orders_and_survives_restart():
    store = Store()
    first = kernel(Custody(cash=True, escrow_state="FUNDED"), store=store)
    run(first.handle_event(funding_event()))
    second = kernel(
        Custody(cash=True, escrow_state="FUNDED"), store=store)
    replay = run(second.handle_event(funding_event()))
    assert replay["duplicate"] is True
    reused = funding_event()
    reused["work"]["work_id"] = "work_other123"
    reused["offer"]["work_id"] = "work_other123"
    reused["event_id"] = "funding_" + hashlib.sha256(
        b"work_other123|escrow_12345678").hexdigest()
    with pytest.raises(HubError, match="another work order"):
        run(second.handle_event(reused))


def test_amount_mismatch_and_reference_reuse_never_compose():
    hub = kernel()
    with pytest.raises(HubError, match="amount"):
        run(hub.handle_event(event(amount_minor=50)))
    assert hub.status()["verified_settlements"] == 0
    assert hub.cores["identity"].items == {}
    run(hub.handle_event(event()))
    reused = event()
    reused["work"]["work_id"] = "work_other123"
    reused["event_id"] = "hub_" + hashlib.sha256(
        f"work_other123|{TX}".encode()).hexdigest()
    with pytest.raises(HubError, match="already used"):
        run(hub.handle_event(reused))


def test_cash_connect_primitive_verifies_but_manual_boolean_is_refused():
    connect = {"type": "payout", "rail": "connect", "executed": True,
               "transfer_id": "tr_live_123", "net_minor": 95}
    hub = kernel(Custody(cash=True, instruction=connect))
    result = run(hub.handle_event(event(
        rail="viridis_cash_escrow", amount_minor=100,
        reference="escrow_12345678", compute=False)))
    assert result["money_primitive"]["primitive"] == "stripe_connect_transfer"
    manual = {"type": "payout", "rail": "manual", "executed": True}
    second = kernel(Custody(cash=True, instruction=manual))
    with pytest.raises(HubError, match="manual payout"):
        run(second.handle_event(event(
            rail="viridis_cash_escrow", amount_minor=100,
            reference="escrow_12345678", compute=False)))


def test_restart_restores_receipt_and_refuses_duplicate_side_effects():
    store = Store()
    first = kernel(store=store)
    run(first.handle_event(event()))
    second = kernel(store=store)
    replay = run(second.handle_event(event()))
    assert replay["duplicate"] is True
    assert second.status()["verified_settlements"] == 1


def test_pre_funding_schema_state_restores_with_empty_funding_ledgers():
    store = Store()
    store.saved["hub_kernel"] = {
        "receipts": {},
        "references": {},
        "identity_profiles": {},
        "errors": {},
    }

    restored = kernel(store=store)

    assert restored.state.funding_receipts == {}
    assert restored.state.funding_references == {}
    assert restored.status()["verified_work_fundings"] == 0
