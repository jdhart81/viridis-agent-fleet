"""
participant_bridge.py — turn the fleet's COUNTERPARTIES into PARTICIPANTS.

The 2026-07-17 growth review found strangers already earning on the rails
(riverside-robotics, jovian-sensors: RELEASED escrows) and disputing on
them (two live DISPUTED escrows) — with no way to claim earnings, spend
them, or resolve conflicts. This bridge closes both loops:

  PAYEE ECONOMY — a payee on any RELEASED escrow can claim its name,
  get an identity in the fleet registry, see its earned balance, and make
  that balance LIQUID: internal-ledger earnings convert into prepaid call
  credits on any gated fleet service (earnings become a service-backed
  currency), while custody-cash earnings pay out through the existing
  certified-only rail (EC5). Every paid counterparty becomes a recruited,
  identified, trust-accruing fleet participant.

  DISPUTE INTAKE — a DISPUTED escrow files into the arbitration core
  (evidence-cited, hash-committed rulings, A-invariants) and the ruling's
  escrow_instruction (release|refund) is executed back onto the escrow,
  exactly once. Fee schedule is pre-committed; fees are only ever
  COLLECTED on custody-cash escrows (internal-ledger disputes record the
  fee as waived — honest books, doctrine: tax transactions, not rails).

--- INVARIANTS (spec-invariance contract) ---
PB1  claim_payee registers the payee name in the identity registry
     (idempotent, R2) and issues a claim_secret bound to the claim. One
     claim per payee name, first-come (a rival claim is refused and
     directed to arbitration). V1 HONESTY: possession of the name string
     is not proven; therefore a claim unlocks ONLY internal-credit
     spending (bounded value). CASH payouts remain certified-only (EC5) —
     a human reviews the payee before money moves. Claims are visible in
     status() for review.
PB2  payee_balance is derived, never stored: earned = sum of
     net_to_payee_minor over RELEASED escrows naming the payee, split
     cash-backed (custody registry, PG17/EC3) vs internal-ledger, minus
     prior conversions/payouts. The ledger can never pay the same escrow
     twice (consumed escrow ids are persisted).
PB3  spend_earnings converts INTERNAL earned balance into prepaid credits
     on a chosen gated agent at its list price:
     credits = amount_minor // price (>=1), amount debited exactly,
     idempotent per spend_id, persisted before acknowledgement; a failed
     persist reverts and never double-spends (PG16/EC7 family).
PB4  Only internal-ledger balance is spendable via PB3. Cash-backed
     balance is only referenced toward the certified payout instruction
     path (escrow_custody EC5); this bridge never moves cash.
PB5  Failures degrade to structured refusals; nothing here crashes a tool
     call; partial state never persists (save-or-revert).
PB6  file_escrow_dispute requires the escrow to be DISPUTED; files an
     arbitration case (claimant=payer, respondent=payee, amount=escrow
     amount) exactly once per escrow (idempotent); the pre-committed fee
     (2.5% of disputed amount, min 50 minor) is RECORDED on the case
     record — collected=False unless the escrow is custody-cash-funded.
PB7  execute_ruling maps a RULED case's escrow_instruction
     (release|refund) onto the escrow through its own state machine
     (E4-E6, never bypassed), exactly once per case; a case without a
     ruling, or an instruction the escrow refuses, is a refusal — never a
     forced transition.
PB8  Everything auditable: claims, spends, filings, executions carry
     timestamps and are persisted in one StateStore aggregate
     ("participants") that survives restarts.
PB9  SELF-TEACHING RELEASE: every ok escrow response whose data shows a
     single escrow in state RELEASED with a non-viridis payee carries
     payee_next_steps (claim_payee call on /payments/mcp + the
     payee_balance / spend_payee_earnings tool names). Gateway-side
     enrichment (attach_self_teaching) — the stdlib escrow core stays
     pure. ADDITIVE ONLY: no existing response key is ever modified or
     removed; enrichment is idempotent (wrapping twice appends once);
     viridis:* payees (fleet revenue, bond collateral) are never taught.
PB10 SELF-TEACHING DISPUTE: every ok escrow response whose data shows a
     single escrow in state DISPUTED carries dispute_next_steps
     (file_escrow_dispute on /payments/mcp, the arbitration
     submit_evidence -> rule -> execute_arbitration_ruling flow, and the
     pre-committed PB6 fee schedule). Same additive/idempotent contract
     as PB9.
"""
from __future__ import annotations

import functools
import inspect
import logging
import secrets
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("viridis.participant_bridge")

DISPUTE_FEE_BPS = 250          # 2.5% of disputed amount ...
DISPUTE_FEE_MIN_MINOR = 50     # ... never less than 50 minor (PB6)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _err(error_type: str, message: str, **extra) -> dict:
    return {"status": "error", "error_type": error_type,
            "message": message, "timestamp": _now(), **extra}


class ParticipantState:
    """Plain persisted holder (CustodyState pattern)."""

    def __init__(self):
        self.claims: Dict[str, dict] = {}        # payee -> claim record (PB1)
        self.spends: Dict[str, dict] = {}        # spend_id -> record (PB3)
        self.spent_minor: Dict[str, int] = {}    # payee -> internal spent (PB2)
        self.disputes: Dict[str, dict] = {}      # escrow_id -> filing (PB6)
        self.executions: Dict[str, dict] = {}    # case_id -> execution (PB7)


class ParticipantBridge:
    def __init__(self, store, escrow_core, identity_core, arbitration_core,
                 gate, custody, persist_key: str = "participants"):
        self.store = store
        self.escrow = escrow_core
        self.identity = identity_core
        self.arbitration = arbitration_core
        self.gate = gate
        self.custody = custody
        self.persist_key = persist_key
        self.state = ParticipantState()
        self._errors: Dict[str, str] = {}
        try:                                                    # PB8
            self.store.restore(persist_key, self.state)
        except Exception as exc:
            self._errors["restore"] = f"{type(exc).__name__}: {exc}"

    def _persist(self) -> bool:
        try:
            return bool(self.store.save(self.persist_key, self.state))
        except Exception as exc:                                # PB5
            self._errors["persist"] = f"{type(exc).__name__}: {exc}"
            return False

    # ---------------- payee economy (PB1-PB4) -------------------------- #
    def _released_escrows_for(self, payee: str) -> list:
        listing = self.escrow.process_sync({"action": "list",
                                            "state": "RELEASED"})
        if listing.get("status") != "ok":
            return []
        return [e for e in listing["data"]["escrows"]
                if e.get("payee") == payee]

    def _balance(self, payee: str) -> dict:
        """PB2: derived, split cash vs internal, net of prior spends."""
        custody_funded = getattr(getattr(self.custody, "state", None),
                                 "funded", {}) or {}
        earned_cash = earned_internal = 0
        for e in self._released_escrows_for(payee):
            if str(e.get("payee", "")).startswith("viridis:"):
                continue                       # fleet revenue, not a payee
            net = int(e.get("net_to_payee_minor") or 0)
            if e["escrow_id"] in custody_funded:
                earned_cash += net
            else:
                earned_internal += net
        spent = int(self.state.spent_minor.get(payee, 0))
        return {"payee": payee,
                "earned_internal_minor": earned_internal,
                "spent_internal_minor": spent,
                "spendable_internal_minor": max(earned_internal - spent, 0),
                "cash_backed_minor": earned_cash,
                "cash_note": ("cash-backed earnings pay out ONLY via the "
                              "certified escrow_settlement_instruction rail "
                              "(EC5); internal earnings are spendable as "
                              "fleet credits via spend_payee_earnings")}

    async def claim_payee(self, payee: Any, contact: Any = "",
                          capabilities: Any = None) -> dict:
        if not isinstance(payee, str) or not payee.strip():
            return _err("bad_payee", "payee name is required")
        payee = payee.strip()
        if payee.startswith("viridis:"):
            return _err("reserved", "viridis:* payees are the fleet itself")
        existing = self.state.claims.get(payee)
        if existing is not None:                                # PB1
            return _err("already_claimed",
                        "payee already claimed; if you are the rightful "
                        "owner, file a dispute via the arbitration mount",
                        claimed_at=existing["claimed_at"])
        if not self._released_escrows_for(payee):
            return _err("no_earnings",
                        "no RELEASED escrow names this payee; nothing to claim")
        caps = capabilities if (isinstance(capabilities, list) and capabilities) \
            else ["escrow-payee"]
        try:
            reg = await self.identity.process({
                "action": "register", "agent_id": payee,
                "name": payee, "capabilities": caps,
                "endpoint": str(contact)[:200]})
        except Exception as exc:                                # PB5
            return _err("identity_error",
                        f"registry failed: {type(exc).__name__}")
        if reg.get("status") != "ok":
            return _err("identity_refused",
                        f"registry refused: {reg.get('message')}")
        claim_secret = secrets.token_hex(16)
        record = {"payee": payee, "contact": str(contact)[:200],
                  "did": (reg.get("data") or {}).get("did"),
                  "claim_secret": claim_secret,
                  "claimed_at": _now(), "review": "pending-human-review"}
        self.state.claims[payee] = record
        if not self._persist():                                 # PB5/PB8
            self.state.claims.pop(payee, None)
            return _err("persist_failed", "claim not durable; retry")
        public = {k: v for k, v in record.items() if k != "claim_secret"}
        return {"status": "ok", **public, "claim_secret": claim_secret,
                "keep_this_secret": ("required for spend_payee_earnings; "
                                     "shown exactly once"),
                "balance": self._balance(payee)}

    def payee_balance(self, payee: Any) -> dict:
        if not isinstance(payee, str) or not payee.strip():
            return _err("bad_payee", "payee name is required")
        return {"status": "ok", **self._balance(payee.strip()),
                "claimed": payee.strip() in self.state.claims}

    def spend_earnings(self, payee: Any, claim_secret: Any, agent: Any,
                       amount_minor: Any, spend_id: Any) -> dict:
        """PB3: internal earnings -> prepaid credits on a gated agent."""
        if not isinstance(spend_id, str) or not spend_id.strip():
            return _err("bad_spend_id", "spend_id is required (idempotency key)")
        spend_id = spend_id.strip()
        prior = self.state.spends.get(spend_id)
        if prior is not None:                                   # PB3 idempotent
            return {"status": "ok", "duplicate": True, **prior}
        claim = self.state.claims.get(payee if isinstance(payee, str) else "")
        if claim is None or claim.get("claim_secret") != claim_secret:
            return _err("unauthorized", "unknown payee or wrong claim_secret")
        cores = getattr(self.gate, "_cores", {})
        if agent not in cores:
            return _err("unknown_agent", f"'{agent}' is not a gated agent",
                        gated_agents=sorted(cores))
        if (not isinstance(amount_minor, int) or isinstance(amount_minor, bool)
                or amount_minor <= 0):
            return _err("bad_amount", "amount_minor must be a positive int")
        from payment_gate import PRICE_MINOR, DEFAULT_PRICE_MINOR, GATE_ATTR
        price = PRICE_MINOR.get(agent, DEFAULT_PRICE_MINOR)
        credits = amount_minor // price
        if credits < 1:
            return _err("insufficient_amount",
                        f"{amount_minor} minor buys no {agent} call "
                        f"(price {price})", price_minor=price)
        balance = self._balance(payee)
        if amount_minor > balance["spendable_internal_minor"]:  # PB2/PB3
            return _err("insufficient_balance",
                        f"spendable internal balance is "
                        f"{balance['spendable_internal_minor']} minor",
                        balance=balance)
        core = cores[agent]
        with self.gate._billing_lock(agent):
            gate_state = getattr(core, GATE_ATTR)
            gate_state["credits"] = gate_state.get("credits", 0) + credits
            self.state.spent_minor[payee] = \
                self.state.spent_minor.get(payee, 0) + amount_minor
            record = {"spend_id": spend_id, "payee": payee, "agent": agent,
                      "amount_minor": amount_minor, "credits": credits,
                      "price_minor": price, "spent_at": _now()}
            self.state.spends[spend_id] = record
            try:                                                # PB3/PB5 atomic
                saved = bool(self.store.save_many({
                    agent: core, self.persist_key: self.state}))
            except Exception:
                saved = False
            if not saved:
                gate_state["credits"] -= credits
                self.state.spent_minor[payee] -= amount_minor
                self.state.spends.pop(spend_id, None)
                return _err("persist_failed", "spend not durable; retry "
                            "with the SAME spend_id — nothing was debited")
        logger.info("participant: %s spent %s minor -> %s credits on %s",
                    payee, amount_minor, credits, agent)
        return {"status": "ok", "duplicate": False, **record,
                "how_to_use": (f"call {agent} tools normally; {credits} "
                               "prepaid credits apply after any free tier")}

    # ---------------- dispute intake (PB6-PB7) ------------------------- #
    async def file_dispute(self, escrow_id: Any) -> dict:
        if not isinstance(escrow_id, str) or not escrow_id.strip():
            return _err("bad_escrow_id", "escrow_id is required")
        escrow_id = escrow_id.strip()
        prior = self.state.disputes.get(escrow_id)
        if prior is not None:                                   # PB6 idempotent
            return {"status": "ok", "duplicate": True, **prior}
        status = self.escrow.process_sync({"action": "status",
                                           "escrow_id": escrow_id})
        if status.get("status") != "ok":
            return _err("unknown_escrow", f"no such escrow '{escrow_id}'")
        esc = status["data"]
        if esc["state"] != "DISPUTED":                          # PB6
            return _err("not_disputed", f"escrow is {esc['state']}; only "
                        "DISPUTED escrows file into arbitration")
        try:
            case = await self.arbitration.process({
                "action": "file_case", "escrow_id": escrow_id,
                "claimant": esc["payer"], "respondent": esc["payee"],
                "amount_minor": int(esc["amount_minor"])})
        except Exception as exc:                                # PB5
            return _err("arbitration_error",
                        f"case filing failed: {type(exc).__name__}")
        if case.get("status") != "ok":
            return _err("arbitration_refused",
                        f"arbitration refused: {case.get('message')}")
        fee = max(int(esc["amount_minor"]) * DISPUTE_FEE_BPS // 10000,
                  DISPUTE_FEE_MIN_MINOR)
        custody_funded = getattr(getattr(self.custody, "state", None),
                                 "funded", {}) or {}
        record = {"escrow_id": escrow_id,
                  "case_id": (case.get("data") or {}).get("case_id"),
                  "claimant": esc["payer"], "respondent": esc["payee"],
                  "amount_minor": int(esc["amount_minor"]),
                  "fee_minor": fee,
                  "fee_collected": False,                       # PB6
                  "fee_note": ("collected from the pot on custody-cash "
                               "escrows only; waived (recorded) on "
                               "internal-ledger escrows"
                               if escrow_id not in custody_funded else
                               "custody-cash escrow: fee due from pot at "
                               "ruling execution"),
                  "filed_at": _now()}
        self.state.disputes[escrow_id] = record
        if not self._persist():                                 # PB5/PB8
            self.state.disputes.pop(escrow_id, None)
            return _err("persist_failed", "filing recorded in arbitration "
                        "but bridge record not durable; retry (idempotent)")
        return {"status": "ok", "duplicate": False, **record,
                "next": ("parties submit_evidence on the arbitration mount, "
                         "then rule; execute_arbitration_ruling applies the "
                         "outcome to the escrow")}

    async def execute_ruling(self, case_id: Any) -> dict:
        if not isinstance(case_id, str) or not case_id.strip():
            return _err("bad_case_id", "case_id is required")
        case_id = case_id.strip()
        prior = self.state.executions.get(case_id)
        if prior is not None:                                   # PB7 idempotent
            return {"status": "ok", "duplicate": True, **prior}
        try:
            case = await self.arbitration.process({"action": "get_case",
                                                   "case_id": case_id})
        except Exception as exc:
            return _err("arbitration_error", f"{type(exc).__name__}")
        if case.get("status") != "ok":
            return _err("unknown_case", f"no such case '{case_id}'")
        cdata = case["data"]
        ruling = cdata.get("ruling")
        if not ruling:                                          # PB7
            return _err("not_ruled", "case has no ruling yet")
        instruction = ruling.get("escrow_instruction")
        if instruction not in ("release", "refund"):
            return _err("bad_instruction",
                        f"ruling instruction '{instruction}' is not executable")
        outcome = self.escrow.process_sync({
            "action": instruction, "escrow_id": cdata["escrow_id"],
            "reason" if instruction == "refund" else "delivery_proof":
                f"arbitration ruling {ruling.get('ruling_hash', '')[:16]}"})
        if outcome.get("status") != "ok":                       # PB7 refusal
            return _err("escrow_refused",
                        f"escrow refused '{instruction}': "
                        f"{outcome.get('message')}")
        record = {"case_id": case_id, "escrow_id": cdata["escrow_id"],
                  "instruction": instruction,
                  "escrow_state": (outcome.get("data") or {}).get("state"),
                  "ruling_hash": ruling.get("ruling_hash"),
                  "executed_at": _now()}
        self.state.executions[case_id] = record
        try:                                                    # PB5/PB8 atomic
            saved = bool(self.store.save_many({
                "escrow": self.escrow, self.persist_key: self.state}))
        except Exception:
            saved = False
        if not saved:
            # escrow transition is terminal & idempotent (E6); the record
            # is safe to retry — refuse ack rather than lie about durability
            self.state.executions.pop(case_id, None)
            return _err("persist_failed", "execution not durable; retry — "
                        "the escrow transition is exactly-once (E6)")
        return {"status": "ok", "duplicate": False, **record}

    # ------------------------------------------------------------------ #
    def status(self) -> dict:
        return {"claims": {p: {k: v for k, v in c.items()
                               if k != "claim_secret"}
                           for p, c in self.state.claims.items()},
                "spends": len(self.state.spends),
                "internal_spent_minor": sum(self.state.spent_minor.values()),
                "disputes_filed": len(self.state.disputes),
                "rulings_executed": len(self.state.executions),
                "dispute_fee_schedule": {
                    "bps": DISPUTE_FEE_BPS, "min_minor": DISPUTE_FEE_MIN_MINOR,
                    "collected_on": "custody-cash escrows only (PB6)"},
                "errors": dict(self._errors)}


# ---------------- self-teaching envelopes (PB9-PB10) ---------------------- #
PAYMENTS_MCP = "https://mcp.viridisconservation.com/payments/mcp"


def _teach(result: Any) -> Any:
    """PB9/PB10 enrichment. ADDITIVE ONLY — existing keys are never touched;
    anything that is not an ok single-escrow response passes through
    byte-identical. Never raises (PB5 family): teaching must not be able
    to break settlement."""
    try:
        if not isinstance(result, dict) or result.get("status") != "ok":
            return result
        data = result.get("data")
        if not isinstance(data, dict) or "state" not in data:
            return result                      # list/verify shapes: untouched
        state = data.get("state")
        payee = data.get("payee")
        if (state == "RELEASED" and isinstance(payee, str) and payee
                and not payee.startswith("viridis:")
                and "payee_next_steps" not in result):              # PB9
            result["payee_next_steps"] = {
                "claim": (f"call claim_payee('{payee}') on {PAYMENTS_MCP} "
                          "— earnings are spendable as fleet credits or "
                          "certified cash"),
                "balance_tool": "payee_balance",
                "spend_tool": "spend_payee_earnings",
            }
        if state == "DISPUTED" and "dispute_next_steps" not in result:  # PB10
            result["dispute_next_steps"] = {
                "file": (f"call file_escrow_dispute("
                         f"'{data.get('escrow_id')}') on {PAYMENTS_MCP} "
                         "to open an evidence-cited arbitration case"),
                "evidence_flow": ("parties submit_evidence on "
                                  "/arbitration/mcp; after `rule`, call "
                                  "execute_arbitration_ruling to apply the "
                                  "outcome to the escrow exactly once"),
                "fee_schedule": {
                    "bps": DISPUTE_FEE_BPS,
                    "min_minor": DISPUTE_FEE_MIN_MINOR,
                    "collected_on": "custody-cash escrows only (PB6)"},
            }
    except Exception:                                               # PB5
        logger.exception("self-teaching enrichment failed (response "
                         "returned unenriched)")
    return result


def attach_self_teaching(escrow_core) -> None:
    """PB9/PB10: wrap the escrow core's dispatch at the GATEWAY so the
    response a participant sees at the moment of an event teaches the next
    step. The stdlib escrow core stays pure; enrichment is idempotent, so
    a path that traverses both wrappers (async process delegating to
    process_sync) appends exactly once. Safe to call twice (no-op)."""
    if getattr(escrow_core, "_self_teaching_attached", False):
        return
    escrow_core._self_teaching_attached = True

    inner_sync = escrow_core.process_sync

    @functools.wraps(inner_sync)
    def process_sync(input_data):
        return _teach(inner_sync(input_data))

    escrow_core.process_sync = process_sync

    inner = escrow_core.process
    if inspect.iscoroutinefunction(inner):
        @functools.wraps(inner)
        async def process(input_data):
            return _teach(await inner(input_data))
    else:
        @functools.wraps(inner)
        def process(input_data):
            return _teach(inner(input_data))

    escrow_core.process = process
