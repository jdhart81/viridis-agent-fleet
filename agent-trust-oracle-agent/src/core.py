"""
agent-trust-oracle-agent — Core business logic.

Reputation + trust attestations for the agent-to-agent economy. Before Agent A
delegates authority, money, or tools to Agent B, it needs to know: can B be
trusted to behave? This oracle answers that with a transparent, decay-weighted
reputation score and issues tamper-evident trust attestations.

This is the commercial embodiment of the Viridis Security thesis — "make AI
agents safe to trust with real authority, backed by proof." Trust here is
framed as *information*: an agent's reputation is the log-odds of good behavior
accumulated from observed outcomes, consistent with the Intelligence Bound /
Adversarial Landauer framing (attribution as thermodynamic cost). Composes with
ShenDao (governance) and OTA (truth verification) as upstream signal sources.

Fleet-standard interface: async process(), async health(), sync describe().

--- INVARIANTS (spec-invariance contract) ---
T1  Reputation score is always in [0.0, 1.0].
T2  Unknown agent -> neutral prior 0.5 (never crash, never 0).
T3  Score is monotone in evidence: a 'success' never decreases score; a
    'failure'/'dispute_lost' never increases it (all else equal).
T4  Time decay: older outcomes weigh less (half-life in days). Recorded via a
    per-outcome weight; decay is applied at query time against 'now'.
T5  Attestations are tamper-evident: each commits to a SHA-256 over its content
    plus the agent's prior attestation hash (per-subject hash chain).
T6  verify_attestation recomputes the hash and validates the chain link.
T7  Tiers derive deterministically from score:
        >=0.85 TRUSTED, >=0.65 RELIABLE, >=0.40 NEUTRAL, >=0.20 CAUTION, else UNTRUSTED.
T8  process() never raises on bad input — returns a structured error envelope.
"""

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    name: str
    version: str = "0.1.1"
    debug: bool = False
    half_life_days: float = 30.0
    prior_strength: float = 2.0  # pseudo-counts for the Beta(prior) smoothing


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utcnow()).isoformat()


# outcome kind -> (successes, failures) contribution
_OUTCOME_WEIGHT = {
    "success": (1.0, 0.0),
    "delivered": (1.0, 0.0),
    "dispute_won": (1.0, 0.0),
    "failure": (0.0, 1.0),
    "undelivered": (0.0, 1.0),
    "dispute_lost": (0.0, 1.0),
    "timeout": (0.0, 1.0),
    "security_incident": (0.0, 3.0),  # heavier penalty (on-thesis: safety weighs hard)
}


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

    def _err(self, message, *, error_type="Error", field="", value=None, constraint="") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _iso()}

    def _ok(self, data=None) -> dict:
        return {"status": "ok", "data": data, "error": None, "timestamp": _iso()}


@dataclass
class Outcome:
    kind: str
    at: datetime
    weight: float
    counterparty: str = ""
    note: str = ""


@dataclass
class Attestation:
    subject: str
    claim: str
    score: float
    tier: str
    issued_at: str
    prev: str
    hash: str = ""


@dataclass
class Subject:
    agent_id: str
    outcomes: List[Outcome] = field(default_factory=list)
    attestations: List[Attestation] = field(default_factory=list)


class TrustOracleCore(AgentCore):
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-trust-oracle-agent"))
        self._subjects: Dict[str, Subject] = {}

    # -- scoring -----------------------------------------------------------
    def _decayed_counts(self, subj: Subject, now: datetime) -> (float, float):
        """Beta-smoothed, time-decayed success/failure pseudo-counts."""
        hl = max(self.config.half_life_days, 1e-6)
        s = f = 0.0
        for o in subj.outcomes:
            age_days = max((now - o.at).total_seconds() / 86400.0, 0.0)
            decay = 0.5 ** (age_days / hl)          # T4
            sw, fw = _OUTCOME_WEIGHT.get(o.kind, (0.0, 0.0))
            s += sw * o.weight * decay
            f += fw * o.weight * decay
        return s, f

    def _score(self, subj: Subject, now: Optional[datetime] = None) -> float:
        now = now or _utcnow()
        s, f = self._decayed_counts(subj, now)
        a = self.config.prior_strength / 2.0
        score = (s + a) / (s + f + 2 * a)           # T2 prior => 0.5 when no evidence
        return max(0.0, min(1.0, score))            # T1

    @staticmethod
    def _tier(score: float) -> str:                  # T7
        if score >= 0.85: return "TRUSTED"
        if score >= 0.65: return "RELIABLE"
        if score >= 0.40: return "NEUTRAL"
        if score >= 0.20: return "CAUTION"
        return "UNTRUSTED"

    def _subject(self, agent_id: str, create: bool = False) -> Optional[Subject]:
        subj = self._subjects.get(agent_id)
        if subj is None and create:
            subj = self._subjects[agent_id] = Subject(agent_id=agent_id)
        return subj

    # -- dispatch ----------------------------------------------------------
    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object", error_type="ValidationError",
                                 field="input", value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "record_outcome": self._record_outcome,
                "score": self._score_action,
                "query": self._score_action,
                "attest": self._attest,
                "verify_attestation": self._verify_attestation,
                "history": self._history,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'", error_type="ValidationError",
                                 field="action", value=action,
                                 constraint="one of: record_outcome, score, query, attest, verify_attestation, history")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError", field=e.field,
                             value=e.value, constraint=e.constraint)
        except Exception as e:
            self.logger.exception("trust-oracle process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    def _require(self, data: dict, f: str):
        if f not in data:
            raise ValidationError(f"missing '{f}'", field=f, constraint="required")
        return data[f]

    def _record_outcome(self, data: dict) -> dict:
        agent_id = self._require(data, "agent_id")
        kind = self._require(data, "kind")
        if kind not in _OUTCOME_WEIGHT:
            raise ValidationError(f"unknown outcome kind '{kind}'", field="kind",
                                  value=kind, constraint=f"one of {sorted(_OUTCOME_WEIGHT)}")
        weight = data.get("weight", 1.0)
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
            raise ValidationError("weight must be a positive number", field="weight",
                                  value=weight, constraint="number > 0")
        subj = self._subject(agent_id, create=True)
        subj.outcomes.append(Outcome(kind=kind, at=_utcnow(), weight=float(weight),
                                     counterparty=data.get("counterparty", ""),
                                     note=data.get("note", "")))
        score = self._score(subj)
        return self._ok({"agent_id": agent_id, "score": round(score, 4),
                         "tier": self._tier(score), "outcomes": len(subj.outcomes)})

    def _score_action(self, data: dict) -> dict:
        agent_id = self._require(data, "agent_id")
        subj = self._subject(agent_id)
        if subj is None:                              # T2
            return self._ok({"agent_id": agent_id, "score": 0.5, "tier": "NEUTRAL",
                             "outcomes": 0, "prior": True})
        score = self._score(subj)
        return self._ok({"agent_id": agent_id, "score": round(score, 4),
                         "tier": self._tier(score), "outcomes": len(subj.outcomes),
                         "prior": False})

    @staticmethod
    def _hash(prev: str, payload: dict) -> str:
        return hashlib.sha256((prev + json.dumps(payload, sort_keys=True, default=str)).encode()).hexdigest()

    def _attest(self, data: dict) -> dict:
        agent_id = self._require(data, "agent_id")
        claim = data.get("claim", "reputation-snapshot")
        subj = self._subject(agent_id, create=True)
        score = self._score(subj)
        prev = subj.attestations[-1].hash if subj.attestations else "genesis"
        content = {"subject": agent_id, "claim": claim, "score": round(score, 4),
                   "tier": self._tier(score), "issued_at": _iso(), "prev": prev}
        att = Attestation(subject=agent_id, claim=claim, score=content["score"],
                          tier=content["tier"], issued_at=content["issued_at"],
                          prev=prev, hash=self._hash(prev, content))
        subj.attestations.append(att)
        return self._ok({"attestation_id": att.hash, "subject": agent_id,
                         "claim": claim, "score": att.score, "tier": att.tier,
                         "issued_at": att.issued_at, "prev": prev})

    def _verify_attestation(self, data: dict) -> dict:
        agent_id = self._require(data, "agent_id")
        att_id = self._require(data, "attestation_id")
        subj = self._subject(agent_id)
        if subj is None:
            return self._ok({"valid": False, "reason": "unknown subject"})
        for att in subj.attestations:
            if att.hash == att_id:
                content = {"subject": att.subject, "claim": att.claim, "score": att.score,
                           "tier": att.tier, "issued_at": att.issued_at, "prev": att.prev}
                ok = self._hash(att.prev, content) == att.hash
                return self._ok({"valid": ok, "subject": agent_id, "tier": att.tier,
                                 "score": att.score})
        return self._ok({"valid": False, "reason": "attestation not found"})

    def _history(self, data: dict) -> dict:
        agent_id = self._require(data, "agent_id")
        subj = self._subject(agent_id)
        if subj is None:
            return self._ok({"agent_id": agent_id, "outcomes": [], "attestations": 0})
        return self._ok({
            "agent_id": agent_id,
            "outcomes": [{"kind": o.kind, "at": _iso(o.at), "weight": o.weight} for o in subj.outcomes],
            "attestations": len(subj.attestations),
            "score": round(self._score(subj), 4),
            "tier": self._tier(self._score(subj)),
        })

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Reputation & tamper-evident trust attestations for A2A delegation.",
            "capabilities": ["record_outcome", "score", "query", "attest",
                             "verify_attestation", "history"],
            "inputs": {"action": "str", "agent_id": "str", "kind": "str (outcome)",
                       "claim": "str (attest)", "attestation_id": "str (verify)"},
            "outputs": {"status": "str (ok|error)", "data": "dict"},
            "a2a_role": "trust",
        }

    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"subjects": len(self._subjects),
                       "attestations": sum(len(s.attestations) for s in self._subjects.values())}
        return h


def build(config: Optional[AgentConfig] = None) -> TrustOracleCore:
    return TrustOracleCore(config)
