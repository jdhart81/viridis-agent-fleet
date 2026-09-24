"""
agent-arbitration-agent — Core business logic.

Dispute-resolution oracle for the A2A economy. agent-escrow-agent's state
machine allows DISPUTED -> (RELEASED | REFUNDED) "arbiter resolves" — this is
that arbiter. It takes a disputed escrow, collects evidence from both parties,
folds in trust-oracle reputation signals, and produces a deterministic,
machine-verifiable ruling that allocates 100% of the disputed amount.

Rulings are evidence-weighted, not discretionary: the same case record always
produces the same ruling, and verify_ruling recomputes it from the cited
inputs — an auditable oracle, on the Viridis "proof-backed trust" thesis.

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input.

--- INVARIANTS (spec-invariance contract) ---
A1  Case lifecycle is forward-only: FILED -> EVIDENCE_OPEN -> RULED.
    RULED is terminal and the ruling is immutable.
A2  A case requires two distinct parties (claimant != respondent) and a
    non-empty disputed reference (escrow_id).
A3  Evidence may be submitted only by the case's named parties and only while
    the case is EVIDENCE_OPEN; submission after ruling is rejected.
A4  Rulings are deterministic: the same evidence set + the same trust signals
    always produce the same allocation (rule-based weights, no randomness).
A5  A ruling allocates exactly 100% of the disputed amount:
    claimant_pct + respondent_pct == 100 (integers).
A6  Every ruling is machine-checkable: it cites the evidence ids and trust
    inputs it used, and verify_ruling recomputes the allocation from those
    citations and matches the stored ruling.
A7  Exactly-once: ruling a RULED case is an idempotent no-op returning the
    existing ruling.
A8  Unknown case_id -> error envelope, never a crash.
A9  DEFAULT JUDGMENT (burden of proof; policy DJ-14, ratified 2026-07-17 by
    Justin Hart): rule with default_judgment=true is valid ONLY while the
    case is EVIDENCE_OPEN and the CLAIMANT has submitted zero evidence —
    the claimant bore the burden and did not carry it. It allocates 0/100
    (claimant/respondent), instructs "release", and stamps the ruling with
    default_judgment + the policy id. It is machine-checkable like A6:
    verify_ruling recomputes the PRECONDITION (no claimant evidence among
    citations, exact 0/100 allocation) instead of the evidence-weighted
    allocation. A default judgment against an evidenced claim is refused —
    evidence always forces the ordinary A4 path. rule() WITHOUT the flag
    is unchanged in every observable way (additive only). The deadline
    itself (14 days) is enforced by the caller that holds the filing
    record (participant_bridge PB11); this core enforces the burden rule.
"""

import hashlib
import json
import logging
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
    version: str = "0.2.0"
    debug: bool = False


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


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


# --------------------------------------------------------------------------- #
# Domain
# --------------------------------------------------------------------------- #
FILED, EVIDENCE_OPEN, RULED = "FILED", "EVIDENCE_OPEN", "RULED"

# A4: fixed, public evidence weights (rule-based, no discretion)
EVIDENCE_WEIGHTS = {"delivery_proof": 3.0, "log": 2.0, "statement": 1.0}
TRUST_WEIGHT = 2.0  # weight of a party's trust score (0..1) in its total


@dataclass
class Case:
    case_id: str
    escrow_id: str
    claimant: str
    respondent: str
    amount_minor: int
    state: str = EVIDENCE_OPEN  # filing opens evidence immediately (A1)
    filed_at: str = field(default_factory=_utcnow)
    evidence: List[dict] = field(default_factory=list)
    trust_scores: Dict[str, float] = field(default_factory=dict)
    ruling: Optional[dict] = None

    def public(self) -> dict:
        return {
            "case_id": self.case_id, "escrow_id": self.escrow_id,
            "claimant": self.claimant, "respondent": self.respondent,
            "amount_minor": self.amount_minor, "state": self.state,
            "filed_at": self.filed_at, "evidence_count": len(self.evidence),
            "trust_scores": dict(self.trust_scores), "ruling": self.ruling,
        }


def _score_party(party: str, evidence: List[dict], trust: Dict[str, float]) -> float:
    """A4: deterministic party score = evidence weights + weighted trust prior."""
    ev = sum(EVIDENCE_WEIGHTS[e["kind"]] for e in evidence if e["party"] == party)
    return ev + TRUST_WEIGHT * float(trust.get(party, 0.5))


def _allocate(case_public: dict, evidence: List[dict],
              trust: Dict[str, float]) -> dict:
    """Compute the allocation. Pure function of its inputs (A4/A6)."""
    claimant, respondent = case_public["claimant"], case_public["respondent"]
    cs = _score_party(claimant, evidence, trust)
    rs = _score_party(respondent, evidence, trust)
    total = cs + rs
    claimant_pct = 50 if total == 0 else round(100 * cs / total)
    return {
        "claimant_pct": claimant_pct,
        "respondent_pct": 100 - claimant_pct,  # A5
        "claimant_score": cs,
        "respondent_score": rs,
        "weights": {"evidence": dict(EVIDENCE_WEIGHTS), "trust": TRUST_WEIGHT},
    }


class ArbitrationAgentCore(AgentCore):
    """Deterministic, machine-verifiable dispute resolution for A2A escrows."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-arbitration-agent"))
        self._cases: Dict[str, Case] = {}
        self._seq = 0

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object", error_type="ValidationError",
                                 field="input", value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "file_case": self._file_case,
                "submit_evidence": self._submit_evidence,
                "set_trust_scores": self._set_trust_scores,
                "rule": self._rule,
                "verify_ruling": self._verify_ruling,
                "get_case": self._get_case_action,
                "list_cases": self._list_cases,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'", error_type="ValidationError",
                                 field="action", value=action,
                                 constraint="one of: file_case, submit_evidence, set_trust_scores, "
                                            "rule, verify_ruling, get_case, list_cases")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError", field=e.field,
                             value=e.value, constraint=e.constraint)
        except Exception as e:  # noqa: BLE001
            self.logger.exception("arbitration process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ------------------------------------------------------------------ #
    def _case(self, data: dict) -> Case:
        cid = data.get("case_id")
        case = self._cases.get(cid)
        if case is None:  # A8
            raise ValidationError("unknown case", field="case_id", value=cid,
                                  constraint="must exist")
        return case

    def _file_case(self, data: dict) -> dict:
        for f in ("escrow_id", "claimant", "respondent"):
            if not data.get(f) or not isinstance(data.get(f), str):
                raise ValidationError(f"missing '{f}'", field=f, constraint="non-empty str")
        if data["claimant"] == data["respondent"]:  # A2
            raise ValidationError("claimant and respondent must be distinct parties",
                                  field="respondent", value=data["respondent"],
                                  constraint="!= claimant")
        amount = data.get("amount_minor")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValidationError("amount_minor must be a positive integer",
                                  field="amount_minor", value=amount, constraint="int > 0")
        self._seq += 1
        cid = f"case-{self._seq:06d}"
        case = Case(case_id=cid, escrow_id=data["escrow_id"], claimant=data["claimant"],
                    respondent=data["respondent"], amount_minor=amount)
        self._cases[cid] = case
        return self._ok(case.public())

    def _submit_evidence(self, data: dict) -> dict:
        case = self._case(data)
        if case.state == RULED:  # A3
            raise ValidationError("case already ruled; evidence window closed",
                                  field="case_id", value=case.case_id,
                                  constraint="state must be EVIDENCE_OPEN")
        party = data.get("party")
        if party not in (case.claimant, case.respondent):  # A3
            raise ValidationError("party is not a participant in this case",
                                  field="party", value=party,
                                  constraint=f"one of: {case.claimant}, {case.respondent}")
        kind = data.get("kind")
        if kind not in EVIDENCE_WEIGHTS:
            raise ValidationError("unknown evidence kind", field="kind", value=kind,
                                  constraint=f"one of: {sorted(EVIDENCE_WEIGHTS)}")
        content = data.get("content", "")
        eid = hashlib.sha256(json.dumps(
            {"case": case.case_id, "party": party, "kind": kind, "content": content,
             "n": len(case.evidence)}, sort_keys=True).encode()).hexdigest()[:16]
        item = {"evidence_id": f"ev-{eid}", "party": party, "kind": kind,
                "content": content, "submitted_at": _utcnow()}
        case.evidence.append(item)
        return self._ok(item)

    def _set_trust_scores(self, data: dict) -> dict:
        """Attach trust-oracle scores (0..1 per party) as ruling inputs."""
        case = self._case(data)
        if case.state == RULED:
            raise ValidationError("case already ruled", field="case_id",
                                  value=case.case_id, constraint="state must be EVIDENCE_OPEN")
        scores = data.get("scores")
        if not isinstance(scores, dict) or not scores:
            raise ValidationError("scores must be a non-empty dict of party -> [0,1]",
                                  field="scores", value=scores, constraint="dict")
        for party, s in scores.items():
            if party not in (case.claimant, case.respondent):
                raise ValidationError("score for non-participant", field="scores",
                                      value=party, constraint="parties only")
            if not isinstance(s, (int, float)) or isinstance(s, bool) or not 0.0 <= s <= 1.0:
                raise ValidationError("trust score must be in [0,1]", field="scores",
                                      value=s, constraint="0 <= s <= 1")
        case.trust_scores.update({p: float(s) for p, s in scores.items()})
        return self._ok(case.public())

    def _rule(self, data: dict) -> dict:
        case = self._case(data)
        if case.state == RULED:  # A7 idempotent
            return self._ok({**case.ruling, "duplicate": True})
        if data.get("default_judgment") is True:  # A9
            return self._default_judgment(case, data)
        alloc = _allocate(case.public(), case.evidence, case.trust_scores)  # A4
        cited = [e["evidence_id"] for e in case.evidence]  # A6
        ruling_body = {
            "case_id": case.case_id, "escrow_id": case.escrow_id,
            "amount_minor": case.amount_minor,
            **alloc,
            "claimant_amount_minor": case.amount_minor * alloc["claimant_pct"] // 100,
            "respondent_amount_minor":
                case.amount_minor - case.amount_minor * alloc["claimant_pct"] // 100,
            "cited_evidence": cited,
            "cited_trust_scores": dict(case.trust_scores),
            "escrow_instruction": ("refund" if alloc["claimant_pct"] >= 50 else "release"),
            "ruled_at": _utcnow(),
        }
        ruling_hash = hashlib.sha256(json.dumps(
            {k: ruling_body[k] for k in ("case_id", "claimant_pct", "respondent_pct",
                                         "cited_evidence", "cited_trust_scores")},
            sort_keys=True).encode()).hexdigest()
        case.ruling = {**ruling_body, "ruling_hash": ruling_hash}
        case.state = RULED  # A1 terminal
        return self._ok({**case.ruling, "duplicate": False})

    def _default_judgment(self, case: Case, data: dict) -> dict:
        """A9: burden-of-proof default judgment (policy DJ-14)."""
        claimant_evidence = [e for e in case.evidence
                             if e["party"] == case.claimant]
        if claimant_evidence:
            raise ValidationError(
                "default judgment refused: the claimant has submitted "
                "evidence — rule on the merits (A4) instead",
                field="default_judgment", value=len(claimant_evidence),
                constraint="claimant evidence count must be 0")
        cited = [e["evidence_id"] for e in case.evidence]  # respondent's only
        ruling_body = {
            "case_id": case.case_id, "escrow_id": case.escrow_id,
            "amount_minor": case.amount_minor,
            "claimant_pct": 0, "respondent_pct": 100,          # A5
            "claimant_amount_minor": 0,
            "respondent_amount_minor": case.amount_minor,
            "cited_evidence": cited,
            "cited_trust_scores": dict(case.trust_scores),
            "default_judgment": True,
            "policy": str(data.get("policy", "DJ-14")),
            "rationale": ("burden of proof: claimant submitted no evidence "
                          "while the window was open; ruled for respondent "
                          "under the pre-committed default-judgment policy"),
            "escrow_instruction": "release",
            "ruled_at": _utcnow(),
        }
        ruling_hash = hashlib.sha256(json.dumps(
            {k: ruling_body[k] for k in ("case_id", "claimant_pct",
                                         "respondent_pct", "cited_evidence",
                                         "cited_trust_scores")},
            sort_keys=True).encode()).hexdigest()
        case.ruling = {**ruling_body, "ruling_hash": ruling_hash}
        case.state = RULED  # A1 terminal
        return self._ok({**case.ruling, "duplicate": False})

    def _verify_ruling(self, data: dict) -> dict:  # A6
        case = self._case(data)
        if case.state != RULED or case.ruling is None:
            raise ValidationError("case has no ruling to verify", field="case_id",
                                  value=case.case_id, constraint="state must be RULED")
        if case.ruling.get("default_judgment") is True:  # A9
            cited = set(case.ruling["cited_evidence"])
            cited_records = [e for e in case.evidence
                             if e["evidence_id"] in cited]
            no_claimant_citation = all(e["party"] != case.claimant
                                       for e in cited_records)
            exact_allocation = (case.ruling["claimant_pct"] == 0
                                and case.ruling["respondent_pct"] == 100)
            return self._ok({
                "case_id": case.case_id,
                "valid": no_claimant_citation and exact_allocation,
                "recomputed": {"claimant_cited_evidence": not no_claimant_citation,
                               "required_allocation": {"claimant_pct": 0,
                                                       "respondent_pct": 100},
                               "policy": case.ruling.get("policy")},
                "stored": {"claimant_pct": case.ruling["claimant_pct"],
                           "respondent_pct": case.ruling["respondent_pct"]}})
        cited = set(case.ruling["cited_evidence"])
        evidence = [e for e in case.evidence if e["evidence_id"] in cited]
        alloc = _allocate(case.public(), evidence, case.ruling["cited_trust_scores"])
        matches = (alloc["claimant_pct"] == case.ruling["claimant_pct"]
                   and alloc["respondent_pct"] == case.ruling["respondent_pct"])
        return self._ok({"case_id": case.case_id, "valid": matches,
                         "recomputed": alloc,
                         "stored": {"claimant_pct": case.ruling["claimant_pct"],
                                    "respondent_pct": case.ruling["respondent_pct"]}})

    def _get_case_action(self, data: dict) -> dict:
        return self._ok(self._case(data).public())

    def _list_cases(self, data: dict) -> dict:
        state = data.get("state")
        items = [c.public() for c in self._cases.values()
                 if state is None or c.state == state]
        return self._ok({"count": len(items), "cases": items})

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"cases": len(self._cases),
                       "ruled": sum(1 for c in self._cases.values() if c.state == RULED)}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Deterministic, machine-verifiable dispute resolution "
                           "for A2A escrows (closes DISPUTED -> resolved).",
            "capabilities": ["file_case", "submit_evidence", "set_trust_scores",
                             "rule", "verify_ruling", "get_case", "list_cases"],
            "inputs": {"action": "str", "case_id": "str", "escrow_id": "str",
                       "claimant": "str", "respondent": "str", "amount_minor": "int",
                       "party": "str", "kind": "delivery_proof|log|statement",
                       "scores": "dict[party, 0..1]"},
            "outputs": {"status": "str (ok|error)", "data": "dict"},
            "a2a_role": "arbitration",
        }


def build(config: Optional[AgentConfig] = None) -> ArbitrationAgentCore:
    return ArbitrationAgentCore(config)
