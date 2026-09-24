"""
agent-surety-agent — Core business logic.

Counterparty risk transfer for the agent economy — the missing piece of the
settlement stack. The trust oracle SCORES counterparties; nobody BACKS them.
Here an agent posts a bond behind its promises; a wronged counterparty files
a claim; a machine-verifiable arbitration ruling (agent-arbitration) triggers
slashing from the bond; honest agents reclaim their stake after the coverage
window. The agent-economy analog of a surety bond.

Custody note: like escrow, this is the COORDINATION + STATE-MACHINE layer.
Real fund custody is delegated to a payment rail (Stripe/x402); this core
owns the invariants that make bonding safe.

Composes with: agent-escrow (bonds back escrowed jobs), agent-arbitration
(rulings are the ONLY slash authority), agent-trust-oracle (slashes feed
reputation), agent-metering (bond fees are metered revenue).

Fleet-standard interface: async process(), async health(), sync describe().

--- INVARIANTS (spec-invariance contract) ---
SB1  Bond state machine is forward-only:
         POSTED -> ACTIVE -> (RELEASED | EXHAUSTED)
     with slashes only in ACTIVE. Terminal states are final.
SB2  Amounts are positive integers in minor units. No floats, ever.
SB3  Conservation: for every bond,
         available + slashed_total + released == principal
     at all times (checked after every mutation).
SB4  Slashing requires authority: a claim can only be paid out against a
     ruling reference (arbitration case id + ruling hash). No ruling, no
     slash. A given ruling reference pays at most once (exactly-once).
SB5  A slash never exceeds the bond's available balance; a claim above it
     pays out the remainder and marks the bond EXHAUSTED.
SB6  Release requires the coverage window to have elapsed AND no open
     claims; it returns exactly the available balance.
SB7  Every mutation is appended to a tamper-evident hash chain (each entry
     commits to the previous entry's hash); verify_audit recomputes it.
SB8  process() never raises on bad input — structured error envelope.
SB9  Underwriting (price_bond) is PURE and DETERMINISTIC: integer-only
     arithmetic (no floats), same inputs always produce the same premium and
     the same quote_hash, and quoting never mutates any bond state. The
     quote_hash makes every quote independently recomputable — an arbiter
     can re-derive the premium from the disclosed inputs and model version.
SB10 Risk ceiling: counterparties above the ceiling (>= 4 slashes, or
     historical slashed value >= 50% of requested coverage) are DECLINED
     with a structured reason — an unpriceable risk is never quoted.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TRANSITIONS = {
    "POSTED": {"ACTIVE"},
    "ACTIVE": {"RELEASED", "EXHAUSTED"},
    "RELEASED": set(),
    "EXHAUSTED": set(),
}


@dataclass
class AgentConfig:
    name: str
    version: str = "0.2.0"
    debug: bool = False
    fee_bps: int = 200            # 2.00% bond fee (the revenue)


# ---- underwriting model uw-v1 (SB9/SB10) ---------------------------------- #
# All integer arithmetic. Multipliers are expressed in parts-per-million.
UW_MODEL_VERSION = "uw-v1"
UW_BASE_RATE_BPS_PER_YEAR = 200          # 2.00%/yr of coverage, pro-rated
UW_UNKNOWN_MULT_PPM = 3_000_000          # 3.0x for a counterparty with no history
UW_FLOOR_MULT_PPM = 1_000_000            # 1.0x floor for proven counterparties
UW_EVIDENCE_HALFWEIGHT = 20              # evidence units to halve the risk spread
UW_SLASH_DOUBLINGS_CAP = 3               # each slash doubles, capped at 2^3
UW_SEVERITY_CAP_PPM = 5_000_000          # cap on slashed-value loading
UW_CEILING_MULT_PPM = 10_000_000         # 10x absolute multiplier ceiling
UW_DECLINE_SLASHES = 4                   # SB10: >= this many slashes => decline
UW_MAX_DURATION_DAYS = 365


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utcnow()).isoformat()


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


class AgentCore:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(config.name)
        self.logger.setLevel(logging.DEBUG if config.debug else logging.INFO)

    async def health(self) -> dict:
        return {"status": "ok", "agent": self.config.name,
                "version": self.config.version, "timestamp": _iso(), "checks": {}}

    def _err(self, message, *, error_type="Error", field="", value=None,
             constraint="") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _iso()}

    def _ok(self, data=None) -> dict:
        return {"status": "ok", "data": data, "error": None, "timestamp": _iso()}


def _pos_int(d: dict, key: str) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or v <= 0:      # SB2
        raise ValidationError(f"'{key}' must be a positive integer (minor units)",
                              field=key, value=v, constraint="int > 0")
    return v


@dataclass
class Bond:
    bond_id: str
    principal_agent: str          # who is bonded (the promiser)
    principal: int                # minor units
    fee_minor: int
    currency: str
    coverage: str                 # what the bond backs (free text / scope)
    expires_at: str               # coverage window end (ISO)
    state: str = "POSTED"
    available: int = 0
    slashed_total: int = 0
    released: int = 0
    created_at: str = ""
    claims: List[dict] = field(default_factory=list)
    paid_rulings: Dict[str, str] = field(default_factory=dict)  # ruling_ref -> claim_id
    audit: List[dict] = field(default_factory=list)

    def public(self) -> dict:
        return {"bond_id": self.bond_id, "principal_agent": self.principal_agent,
                "principal": self.principal, "fee_minor": self.fee_minor,
                "currency": self.currency, "coverage": self.coverage,
                "expires_at": self.expires_at, "state": self.state,
                "available": self.available, "slashed_total": self.slashed_total,
                "released": self.released, "created_at": self.created_at,
                "open_claims": sum(1 for c in self.claims
                                   if c["state"] == "OPEN"),
                "claims": self.claims,
                "audit_head": self.audit[-1]["hash"] if self.audit else None,
                "audit_len": len(self.audit)}


class SuretyAgentCore(AgentCore):
    """Bond posting, ruling-gated slashing, and release for A2A promises."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-surety-agent"))
        self._bonds: Dict[str, Bond] = {}
        self._seq = 0
        self._claim_seq = 0

    # -- audit hash chain (SB7) --------------------------------------------
    @staticmethod
    def _chain(prev: str, payload: dict) -> str:
        body = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256((prev + body).encode()).hexdigest()

    def _append_audit(self, bond: Bond, event: str, detail: dict) -> None:
        prev = bond.audit[-1]["hash"] if bond.audit else "genesis"
        entry = {"event": event, "detail": detail, "at": _iso(), "prev": prev}
        entry["hash"] = self._chain(prev, entry)
        bond.audit.append(entry)

    def _transition(self, bond: Bond, target: str, event: str, detail: dict):
        if target not in _TRANSITIONS[bond.state]:                    # SB1
            raise ValidationError(f"illegal transition {bond.state} -> {target}",
                                  field="state", value=bond.state,
                                  constraint=f"allowed={sorted(_TRANSITIONS[bond.state])}")
        bond.state = target
        self._append_audit(bond, event, detail)

    def _check_conservation(self, bond: Bond) -> None:                # SB3
        total = bond.available + bond.slashed_total + bond.released
        if total != bond.principal:
            # This is an internal invariant violation — fail LOUD.
            raise RuntimeError(
                f"SB3 conservation violated on {bond.bond_id}: "
                f"{bond.available}+{bond.slashed_total}+{bond.released} "
                f"!= {bond.principal}")

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"bonds_total": len(self._bonds),
                       "bonds_active": sum(1 for b in self._bonds.values()
                                           if b.state == "ACTIVE"),
                       "slashed_minor": sum(b.slashed_total
                                            for b in self._bonds.values())}
        return h

    def describe(self) -> dict:
        return {"name": self.config.name, "version": self.config.version,
                "capabilities": ["post_bond", "activate", "file_claim",
                                 "slash", "release", "status", "list",
                                 "verify_audit", "price_bond"],
                "inputs": {"action": "one of capabilities", "...": "per action"},
                "outputs": {"status": "ok|error", "data": "per action"},
                "a2a_role": "surety"}

    # -- dispatch ----------------------------------------------------------
    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object",
                                 error_type="ValidationError", field="input",
                                 value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "post_bond": self._post_bond,
                "activate": self._activate,
                "file_claim": self._file_claim,
                "slash": self._slash,
                "release": self._release,
                "status": self._status,
                "list": self._list,
                "verify_audit": self._verify_audit,
                "price_bond": self._price_bond,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'",
                                 error_type="ValidationError", field="action",
                                 value=action,
                                 constraint="one of: post_bond, activate, "
                                            "file_claim, slash, release, status, "
                                            "list, verify_audit, price_bond")
            result = handler(input_data)
            return result
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError",
                             field=e.field, value=e.value, constraint=e.constraint)
        except Exception as e:                                        # SB8
            self.logger.exception("surety process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # -- operations ----------------------------------------------------------
    def _get(self, d: dict) -> Bond:
        bid = d.get("bond_id")
        bond = self._bonds.get(bid or "")
        if bond is None:
            raise ValidationError(f"unknown bond_id '{bid}'", field="bond_id",
                                  value=bid, constraint="an existing bond")
        return bond

    def _post_bond(self, d: dict) -> dict:
        agent_id = d.get("principal_agent")
        if not agent_id:
            raise ValidationError("'principal_agent' is required",
                                  field="principal_agent", value=agent_id,
                                  constraint="non-empty")
        principal = _pos_int(d, "principal")                          # SB2
        expires_at = d.get("expires_at")
        if not expires_at:
            raise ValidationError("'expires_at' (coverage window end, ISO-8601) "
                                  "is required", field="expires_at",
                                  value=expires_at, constraint="ISO-8601")
        try:
            datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError:
            raise ValidationError("'expires_at' must be ISO-8601",
                                  field="expires_at", value=expires_at,
                                  constraint="ISO-8601")
        self._seq += 1
        fee = -(-principal * self.config.fee_bps // 10_000)   # ceil, frozen
        bond = Bond(bond_id=f"bond_{self._seq:06d}", principal_agent=str(agent_id),
                    principal=principal, fee_minor=fee,
                    currency=str(d.get("currency", "USD")),
                    coverage=str(d.get("coverage", "")),
                    expires_at=str(expires_at), available=principal,
                    created_at=_iso())
        self._append_audit(bond, "posted", {"principal": principal, "fee": fee})
        self._bonds[bond.bond_id] = bond
        self._check_conservation(bond)                                # SB3
        return self._ok(bond.public())

    def _activate(self, d: dict) -> dict:
        bond = self._get(d)
        if bond.state == "ACTIVE":                    # idempotent activation
            return self._ok(bond.public())
        self._transition(bond, "ACTIVE", "activated",
                         {"funding_ref": str(d.get("funding_ref", ""))})
        self._check_conservation(bond)
        return self._ok(bond.public())

    def _file_claim(self, d: dict) -> dict:
        bond = self._get(d)
        if bond.state != "ACTIVE":
            raise ValidationError(f"claims require an ACTIVE bond "
                                  f"(state={bond.state})", field="state",
                                  value=bond.state, constraint="ACTIVE")
        claimant = d.get("claimant")
        if not claimant:
            raise ValidationError("'claimant' is required", field="claimant",
                                  value=claimant, constraint="non-empty")
        amount = _pos_int(d, "amount_minor")                          # SB2
        self._claim_seq += 1
        claim = {"claim_id": f"clm_{self._claim_seq:06d}",
                 "claimant": str(claimant), "amount_minor": amount,
                 "reason": str(d.get("reason", "")), "state": "OPEN",
                 "filed_at": _iso(), "ruling_ref": None, "paid_minor": 0}
        bond.claims.append(claim)
        self._append_audit(bond, "claim_filed", {"claim_id": claim["claim_id"],
                                                 "amount": amount})
        return self._ok(claim)

    def _slash(self, d: dict) -> dict:
        bond = self._get(d)
        if bond.state != "ACTIVE":
            raise ValidationError(f"slash requires an ACTIVE bond "
                                  f"(state={bond.state})", field="state",
                                  value=bond.state, constraint="ACTIVE")
        claim_id = d.get("claim_id")
        claim = next((c for c in bond.claims if c["claim_id"] == claim_id), None)
        if claim is None:
            raise ValidationError(f"unknown claim_id '{claim_id}'",
                                  field="claim_id", value=claim_id,
                                  constraint="a filed claim on this bond")
        if claim["state"] != "OPEN":
            # exactly-once per claim: return the existing terminal claim (SB4)
            return self._ok({"idempotent": True, **claim})
        ruling_case = d.get("ruling_case_id")
        ruling_hash = d.get("ruling_hash")
        if not ruling_case or not ruling_hash:                        # SB4
            raise ValidationError(
                "slashing requires arbitration authority: 'ruling_case_id' and "
                "'ruling_hash' (from agent-arbitration's machine-verifiable "
                "ruling). No ruling, no slash.",
                field="ruling_case_id,ruling_hash", value=None,
                constraint="both required")
        ruling_ref = f"{ruling_case}:{ruling_hash}"
        if ruling_ref in bond.paid_rulings:                           # SB4
            return self._ok({"idempotent": True,
                             "already_paid_by_ruling": ruling_ref,
                             "claim_id": bond.paid_rulings[ruling_ref]})
        upheld = d.get("upheld", True)
        if not upheld:
            claim["state"] = "DENIED"
            claim["ruling_ref"] = ruling_ref
            bond.paid_rulings[ruling_ref] = claim["claim_id"]
            self._append_audit(bond, "claim_denied",
                               {"claim_id": claim_id, "ruling_ref": ruling_ref})
            return self._ok(claim)
        payout = min(claim["amount_minor"], bond.available)           # SB5
        bond.available -= payout
        bond.slashed_total += payout
        claim["state"] = "PAID"
        claim["paid_minor"] = payout
        claim["ruling_ref"] = ruling_ref
        bond.paid_rulings[ruling_ref] = claim["claim_id"]
        self._append_audit(bond, "slashed",
                           {"claim_id": claim_id, "payout": payout,
                            "ruling_ref": ruling_ref,
                            "shortfall": claim["amount_minor"] - payout})
        if bond.available == 0:                                       # SB5
            self._transition(bond, "EXHAUSTED", "exhausted", {})
        self._check_conservation(bond)                                # SB3
        return self._ok({**claim, "bond_state": bond.state,
                         "bond_available": bond.available})

    def _release(self, d: dict) -> dict:
        bond = self._get(d)
        if bond.state != "ACTIVE":
            raise ValidationError(f"release requires an ACTIVE bond "
                                  f"(state={bond.state})", field="state",
                                  value=bond.state, constraint="ACTIVE")
        now = d.get("_now")  # test hook; production uses real time
        now_dt = (datetime.fromisoformat(now) if now else _utcnow())
        exp = datetime.fromisoformat(bond.expires_at.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        if now_dt < exp:                                              # SB6
            raise ValidationError("coverage window has not elapsed",
                                  field="expires_at", value=bond.expires_at,
                                  constraint=f"now >= {bond.expires_at}")
        if any(c["state"] == "OPEN" for c in bond.claims):            # SB6
            raise ValidationError("open claims must be ruled before release",
                                  field="claims", value="OPEN",
                                  constraint="no open claims")
        amount = bond.available
        bond.released += amount
        bond.available = 0
        self._transition(bond, "RELEASED", "released", {"amount": amount})
        self._check_conservation(bond)                                # SB3
        return self._ok({**bond.public(), "released_now": amount})

    def _status(self, d: dict) -> dict:
        return self._ok(self._get(d).public())

    def _list(self, d: dict) -> dict:
        state = d.get("state")
        bonds = [b.public() for b in self._bonds.values()
                 if state is None or b.state == state]
        return self._ok({"count": len(bonds), "bonds": bonds})

    def _price_bond(self, d: dict) -> dict:                           # SB9/SB10
        """Deterministic actuarial quote for bonding a counterparty.

        History fields are caller-supplied evidence (composable with
        agent-trust-oracle / agent-notary reads at the gateway); the model is
        deliberately transparent so any party can recompute the premium.
        """
        coverage = _pos_int(d, "coverage_minor")
        duration = _pos_int(d, "duration_days")
        if duration > UW_MAX_DURATION_DAYS:
            raise ValidationError("duration_days exceeds maximum",
                                  field="duration_days", value=duration,
                                  constraint=f"<= {UW_MAX_DURATION_DAYS}")
        hist = d.get("history", {})
        if not isinstance(hist, dict):
            raise ValidationError("history must be an object", field="history",
                                  value=type(hist).__name__, constraint="dict")
        def _nn(key: str) -> int:
            v = hist.get(key, 0)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:  # SB2
                raise ValidationError(f"history.{key} must be a non-negative int",
                                      field=f"history.{key}", value=v,
                                      constraint="int >= 0")
            return v
        attestations = _nn("attestations")
        deliveries = _nn("successful_deliveries")
        bonds_completed = _nn("bonds_completed")
        slashes = _nn("slashes")
        slashed_minor = _nn("slashed_minor")

        inputs = {"coverage_minor": coverage, "duration_days": duration,
                  "history": {"attestations": attestations,
                              "successful_deliveries": deliveries,
                              "bonds_completed": bonds_completed,
                              "slashes": slashes,
                              "slashed_minor": slashed_minor},
                  "model": UW_MODEL_VERSION}

        # SB10: risk ceiling — decline, never quote.
        if slashes >= UW_DECLINE_SLASHES or slashed_minor * 2 >= coverage:
            quote = {"decision": "declined", **inputs,
                     "reason": ("slash count at or above ceiling"
                                if slashes >= UW_DECLINE_SLASHES else
                                "historical slashed value >= 50% of coverage")}
            quote["quote_hash"] = self._chain("uw-genesis", quote)
            return self._ok(quote)

        # Evidence decays the unknown-counterparty spread toward the floor.
        evidence = attestations + 2 * deliveries + 5 * bonds_completed
        spread = UW_UNKNOWN_MULT_PPM - UW_FLOOR_MULT_PPM
        mult_ppm = UW_FLOOR_MULT_PPM + (
            spread * UW_EVIDENCE_HALFWEIGHT
            // (UW_EVIDENCE_HALFWEIGHT + evidence))
        # Slash penalties: doubling per slash (capped) + severity loading.
        mult_ppm <<= min(slashes, UW_SLASH_DOUBLINGS_CAP)
        mult_ppm += min(slashed_minor * 1_000_000 // coverage,
                        UW_SEVERITY_CAP_PPM)
        mult_ppm = min(mult_ppm, UW_CEILING_MULT_PPM)

        # premium = coverage * base_rate * (days/365) * multiplier, ceil, >= 1
        num = (coverage * UW_BASE_RATE_BPS_PER_YEAR * duration * mult_ppm)
        den = 10_000 * 365 * 1_000_000
        premium = max(1, -(-num // den))                    # integer ceil
        quote = {"decision": "quote", **inputs,
                 "premium_minor": premium,
                 "multiplier_ppm": mult_ppm,
                 "base_rate_bps_per_year": UW_BASE_RATE_BPS_PER_YEAR,
                 "effective_rate_bps_per_year":
                     premium * 10_000 * 365 // (coverage * duration)}
        quote["quote_hash"] = self._chain("uw-genesis", quote)  # recomputable
        return self._ok(quote)

    def _verify_audit(self, d: dict) -> dict:                         # SB7
        bond = self._get(d)
        prev = "genesis"
        for i, entry in enumerate(bond.audit):
            body = {k: v for k, v in entry.items() if k != "hash"}
            if entry.get("prev") != prev or self._chain(prev, body) != entry["hash"]:
                return self._ok({"valid": False, "broken_at": i})
            prev = entry["hash"]
        return self._ok({"valid": True, "length": len(bond.audit)})


def build(config: Optional[AgentConfig] = None) -> SuretyAgentCore:
    return SuretyAgentCore(config)
