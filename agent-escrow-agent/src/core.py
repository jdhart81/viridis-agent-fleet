"""
agent-escrow-agent — Core business logic.

Trustless escrow + settlement for agent-to-agent (A2A) transactions.
When Agent A pays Agent B for a service (compute, data, a CAD file, a security
scan), funds sit in escrow until delivery is verified — then release or refund.

Design note: this is the *coordination + state-machine* layer. It leverages the
same x402 / HTTP-402 micropayment idiom already proven in Energy AI
(`micropayment.ts`: prepaid balance, idempotent on toolCallId, refunds). Real
fund custody is delegated to a payment rail adapter (Stripe/x402/on-chain);
this core owns the invariants that make settlement safe.

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input — it returns a
structured error envelope.

--- INVARIANTS (spec-invariance contract) ---
E1  Escrow state machine is forward-only:
        OPEN -> FUNDED -> (RELEASED | REFUNDED | DISPUTED)
        DISPUTED -> (RELEASED | REFUNDED)      (arbiter resolves)
    Terminal states {RELEASED, REFUNDED} are final and immutable.
E2  amount_minor is a positive integer (minor units, e.g. cents). No floats.
E3  fee_minor = ceil(amount_minor * fee_bps / 10_000), computed once at open,
    frozen for the escrow's life.
E4  release requires current state in {FUNDED, DISPUTED}. Never from OPEN.
E5  refund requires current state in {FUNDED, DISPUTED, OPEN}. OPEN refund is a
    cancel (nothing was funded) and moves straight to REFUNDED.
E6  Exactly-once settlement: a second release/refund on a terminal escrow is a
    no-op that returns the existing terminal record (idempotent), never a
    double payout.
E7  Every state transition is appended to an audit trail (tamper-evident hash
    chain: each entry commits to the previous entry's hash).
E8  Unknown escrow_id -> error envelope, never a crash.
E9  process_sync(x) is semantically identical to await process(x) for every
    action: same dispatch table, same envelopes, same state effects, and it
    never raises. It exists so in-process composers that must make a blocking
    settlement decision (e.g. the gateway PaymentGate verifying and consuming
    an escrow before granting a paid call, PG13-PG16) do not have to drive a
    coroutine from a sync frame. It is NOT wrapped by external persistence
    decorators applied to process(); such callers own their own durability.
E10 IDEMPOTENT OPEN (added 2026-07-17; live evidence: 7 of 12 escrows
    opened by external agents on 2026-07-16/17 were client retries): open
    with a client-supplied open_ref (non-empty str, trimmed to 120 chars)
    creates at most one escrow per ref — a replay returns the ORIGINAL
    escrow's record marked duplicate=true, regardless of any other
    argument drift in the retry. open WITHOUT open_ref is byte-identical
    to pre-E10 behavior (additive only). Refs are scoped to this core
    instance's lifetime and persist with its state.
"""

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Fleet-standard base (self-contained; each agent runs in its own PYTHONPATH)
# --------------------------------------------------------------------------- #
@dataclass
class AgentConfig:
    name: str
    version: str = "0.1.3"
    debug: bool = False
    fee_bps: int = 100  # 1.00% default settlement fee


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentCore:
    """Minimal fleet-standard base. Subclasses override process()/describe()."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(config.name)
        self.logger.setLevel(logging.DEBUG if config.debug else logging.INFO)

    async def process(self, input_data: dict) -> dict:
        raise NotImplementedError

    async def health(self) -> dict:
        return {
            "status": "ok",
            "agent": self.config.name,
            "version": self.config.version,
            "timestamp": _utcnow(),
            "checks": {},
        }

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "override me",
            "capabilities": [],
            "inputs": {},
            "outputs": {},
        }

    # -- helpers -----------------------------------------------------------
    def _err(self, message: str, *, error_type: str = "Error",
             field: str = "", value: Any = None, constraint: str = "") -> dict:
        return {
            "status": "error",
            "error_type": error_type,
            "field": field,
            "value": value,
            "constraint": constraint,
            "message": message,
            "timestamp": _utcnow(),
        }

    def _ok(self, data: Any = None) -> dict:
        return {"status": "ok", "data": data, "error": None, "timestamp": _utcnow()}


# --------------------------------------------------------------------------- #
# Domain
# --------------------------------------------------------------------------- #
OPEN, FUNDED, RELEASED, REFUNDED, DISPUTED = (
    "OPEN", "FUNDED", "RELEASED", "REFUNDED", "DISPUTED",
)
TERMINAL = {RELEASED, REFUNDED}

# Allowed transitions (E1)
_TRANSITIONS = {
    OPEN: {FUNDED, REFUNDED},          # fund, or cancel-before-funding
    FUNDED: {RELEASED, REFUNDED, DISPUTED},
    DISPUTED: {RELEASED, REFUNDED},
    RELEASED: set(),
    REFUNDED: set(),
}


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


@dataclass
class Escrow:
    escrow_id: str
    payer: str
    payee: str
    amount_minor: int
    currency: str
    fee_minor: int
    terms: str
    deadline: Optional[str]
    state: str = OPEN
    created_at: str = field(default_factory=_utcnow)
    audit: List[Dict[str, Any]] = field(default_factory=list)

    def net_to_payee(self) -> int:
        return self.amount_minor - self.fee_minor

    def public(self) -> dict:
        return {
            "escrow_id": self.escrow_id,
            "payer": self.payer,
            "payee": self.payee,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "fee_minor": self.fee_minor,
            "net_to_payee_minor": self.net_to_payee(),
            "state": self.state,
            "terms": self.terms,
            "deadline": self.deadline,
            "created_at": self.created_at,
            "audit_head": self.audit[-1]["hash"] if self.audit else None,
            "audit_len": len(self.audit),
        }


class EscrowAgentCore(AgentCore):
    """Escrow & settlement engine for A2A transactions."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-escrow-agent"))
        self._escrows: Dict[str, Escrow] = {}
        self._seq = 0

    # -- audit hash chain (E7) --------------------------------------------
    @staticmethod
    def _chain(prev_hash: str, payload: dict) -> str:
        body = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256((prev_hash + body).encode()).hexdigest()

    def _append_audit(self, esc: Escrow, event: str, detail: dict) -> None:
        prev = esc.audit[-1]["hash"] if esc.audit else "genesis"
        entry = {"event": event, "detail": detail, "at": _utcnow(), "prev": prev}
        entry["hash"] = self._chain(prev, entry)
        esc.audit.append(entry)

    def _transition(self, esc: Escrow, target: str, event: str, detail: dict) -> None:
        if target not in _TRANSITIONS[esc.state]:
            raise ValidationError(
                f"illegal transition {esc.state} -> {target}",
                field="state", value=esc.state, constraint=f"allowed={sorted(_TRANSITIONS[esc.state])}",
            )
        esc.state = target
        self._append_audit(esc, event, detail)

    # -- dispatch ----------------------------------------------------------
    def process_sync(self, input_data: dict) -> dict:
        """E9: blocking dispatch, envelope-identical to await process(x).

        Every handler below is synchronous; process() is async only to honor
        the fleet-standard interface. This public sync entry lets in-process
        composers (gateway PaymentGate escrow settlement, PG13-PG16) verify
        and consume an escrow inside a sync call frame without event-loop
        gymnastics. Persistence wrappers attached to process() do NOT cover
        this path — callers must persist the core themselves after mutating
        calls (the PaymentGate does).
        """
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object", error_type="ValidationError",
                                 field="input", value=type(input_data).__name__,
                                 constraint="dict")
            action = input_data.get("action")
            handler = {
                "open": self._open,
                "fund": self._fund,
                "release": self._release,
                "refund": self._refund,
                "dispute": self._dispute,
                "status": self._status,
                "list": self._list,
                "verify_audit": self._verify_audit,
            }.get(action)
            if handler is None:
                return self._err(
                    f"unknown action '{action}'", error_type="ValidationError",
                    field="action", value=action,
                    constraint="one of: open, fund, release, refund, dispute, status, list, verify_audit",
                )
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError",
                             field=e.field, value=e.value, constraint=e.constraint)
        except Exception as e:  # never crash the fleet contract
            self.logger.exception("escrow process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    async def process(self, input_data: dict) -> dict:
        return self.process_sync(input_data)                       # E9

    # -- operations --------------------------------------------------------
    def _get(self, data: dict) -> Escrow:
        eid = data.get("escrow_id")
        esc = self._escrows.get(eid)
        if esc is None:
            raise ValidationError("unknown escrow_id", field="escrow_id",
                                  value=eid, constraint="must exist")
        return esc

    def _open(self, data: dict) -> dict:
        # E10: client-supplied idempotency ref — a retry never mints a
        # second escrow. Checked before any validation so a replay of a
        # successful open can never start failing on argument drift.
        refs = getattr(self, "_open_refs", None)
        if refs is None:
            refs = self._open_refs = {}          # pre-E10 snapshots restore
        ref = data.get("open_ref")
        ref = ref.strip()[:120] if isinstance(ref, str) and ref.strip() else None
        if ref is not None and ref in refs:
            prior = self._escrows.get(refs[ref])
            if prior is not None:
                return self._ok({**prior.public(), "duplicate": True})
        for f in ("payer", "payee", "amount_minor"):
            if f not in data:
                raise ValidationError(f"missing '{f}'", field=f, constraint="required")
        amount = data["amount_minor"]
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:  # E2
            raise ValidationError("amount_minor must be a positive integer (minor units)",
                                  field="amount_minor", value=amount, constraint="int > 0")
        if data["payer"] == data["payee"]:
            raise ValidationError("payer and payee must differ", field="payee",
                                  value=data["payee"], constraint="payer != payee")
        fee_bps = int(data.get("fee_bps", self.config.fee_bps))
        fee_minor = math.ceil(amount * fee_bps / 10_000)  # E3
        self._seq += 1
        eid = data.get("escrow_id") or f"esc_{self._seq:06d}"
        esc = Escrow(
            escrow_id=eid, payer=data["payer"], payee=data["payee"],
            amount_minor=amount, currency=data.get("currency", "USD"),
            fee_minor=fee_minor, terms=data.get("terms", ""),
            deadline=data.get("deadline"),
        )
        self._append_audit(esc, "open", {"amount_minor": amount, "fee_minor": fee_minor})
        self._escrows[eid] = esc
        if ref is not None:                      # E10
            refs[ref] = eid
        return self._ok(esc.public())

    def _fund(self, data: dict) -> dict:
        esc = self._get(data)
        if esc.state == FUNDED:
            return self._ok(esc.public())  # idempotent
        self._transition(esc, FUNDED, "fund", {"ref": data.get("payment_ref")})
        return self._ok(esc.public())

    def _release(self, data: dict) -> dict:
        esc = self._get(data)
        if esc.state == RELEASED:            # E6 exactly-once
            return self._ok(esc.public())
        if esc.state == REFUNDED:
            raise ValidationError("escrow already refunded; cannot release",
                                  field="state", value=esc.state, constraint="not REFUNDED")
        self._transition(esc, RELEASED, "release",  # E4 enforced by _transition
                         {"proof": data.get("delivery_proof"),
                          "net_to_payee_minor": esc.net_to_payee()})
        return self._ok(esc.public())

    def _refund(self, data: dict) -> dict:
        esc = self._get(data)
        if esc.state == REFUNDED:            # E6
            return self._ok(esc.public())
        if esc.state == RELEASED:
            raise ValidationError("escrow already released; cannot refund",
                                  field="state", value=esc.state, constraint="not RELEASED")
        self._transition(esc, REFUNDED, "refund", {"reason": data.get("reason", "")})
        return self._ok(esc.public())

    def _dispute(self, data: dict) -> dict:
        esc = self._get(data)
        self._transition(esc, DISPUTED, "dispute", {"reason": data.get("reason", "")})
        return self._ok(esc.public())

    def _status(self, data: dict) -> dict:
        return self._ok(self._get(data).public())

    def _list(self, data: dict) -> dict:
        state = data.get("state")
        items = [e.public() for e in self._escrows.values()
                 if state is None or e.state == state]
        return self._ok({"count": len(items), "escrows": items})

    def _verify_audit(self, data: dict) -> dict:
        esc = self._get(data)
        prev = "genesis"
        for i, entry in enumerate(esc.audit):
            recomputed = self._chain(prev, {k: entry[k] for k in ("event", "detail", "at", "prev")})
            if recomputed != entry["hash"] or entry["prev"] != prev:
                return self._ok({"valid": False, "broken_at": i})
            prev = entry["hash"]
        return self._ok({"valid": True, "entries": len(esc.audit)})

    # -- describe / health -------------------------------------------------
    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Trustless escrow & settlement for agent-to-agent transactions.",
            "capabilities": ["open", "fund", "release", "refund", "dispute",
                             "status", "list", "verify_audit"],
            "inputs": {"action": "str", "payer": "str", "payee": "str",
                       "amount_minor": "int", "currency": "str (optional)",
                       "escrow_id": "str (for state ops)"},
            "outputs": {"status": "str (ok|error)", "data": "dict", "error": "str (optional)"},
            "a2a_role": "settlement",
        }

    async def health(self) -> dict:
        h = await super().health()
        open_n = sum(1 for e in self._escrows.values() if e.state in (OPEN, FUNDED, DISPUTED))
        h["checks"] = {"escrows_total": len(self._escrows), "escrows_active": open_n}
        return h


def build(config: Optional[AgentConfig] = None) -> EscrowAgentCore:
    return EscrowAgentCore(config)
