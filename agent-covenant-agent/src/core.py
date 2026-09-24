"""
agent-covenant-agent — Core business logic.

Power of attorney for agents: machine-checkable authority leases. Before an
agent wields real authority (spend money, mutate accounts, sign, publish), a
principal grants it a COVENANT — an explicit lease of scopes, a spend budget,
and an expiry. Every proposed act is checked against the covenant; every check
(allow AND deny) lands on a tamper-evident audit chain; revocation is
instantaneous and terminal. Deny-by-default, always.

This is the Viridis Security thesis made operational: an agent is safe to
trust with authority only when its authority is explicit, bounded, expiring,
revocable, and audited.

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input.

--- INVARIANTS (spec-invariance contract) ---
C1  Deny-by-default: an act is allowed ONLY if the covenant is ACTIVE, the
    scope is granted, the amount fits the remaining budget, and the covenant
    has not expired. Anything else denies with a reason.
C2  Budget is monotone non-increasing and never negative: total consumed
    never exceeds the granted budget.
C3  Every check — allowed or denied — is appended to a tamper-evident audit
    hash chain; verify_audit detects any mutation.
C4  Revocation is immediate and terminal: a REVOKED covenant denies every
    subsequent check and can never be re-activated.
C5  Scope matching is deterministic: exact match, or wildcard prefix
    ("payments.*" grants "payments.refund"). Bare "*" grants everything.
C6  Expiry is enforced: a check after expires_at denies and transitions the
    covenant to EXPIRED (terminal).
C7  Budget consumption is idempotent on act_id: retrying the same act never
    double-consumes budget.
C8  Unknown covenant_id -> error envelope, never a crash.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    name: str
    version: str = "0.1.1"
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
        return {"status": "ok", "agent": self.config.name,
                "version": self.config.version, "timestamp": _utcnow(), "checks": {}}

    def describe(self) -> dict:
        return {"name": self.config.name, "version": self.config.version,
                "description": "override me", "capabilities": [],
                "inputs": {}, "outputs": {}}

    def _err(self, message: str, *, error_type: str = "Error",
             field: str = "", value: Any = None, constraint: str = "") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _utcnow()}

    def _ok(self, data: Any = None) -> dict:
        return {"status": "ok", "data": data, "error": None, "timestamp": _utcnow()}


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


# --------------------------------------------------------------------------- #
# Domain
# --------------------------------------------------------------------------- #
ACTIVE, REVOKED, EXPIRED = "ACTIVE", "REVOKED", "EXPIRED"
_GENESIS = "0" * 64


def _hash(payload: dict, prev: str) -> str:
    return hashlib.sha256(
        (prev + json.dumps(payload, sort_keys=True, separators=(",", ":"))).encode()
    ).hexdigest()


def _scope_covers(granted: List[str], requested: str) -> bool:
    """C5: exact match or wildcard prefix. Deterministic, no regex."""
    for g in granted:
        if g == "*" or g == requested:
            return True
        if g.endswith(".*") and requested.startswith(g[:-1]):
            return True
    return False


@dataclass
class Covenant:
    covenant_id: str
    principal: str
    agent_id: str
    scopes: List[str]
    budget_minor: int
    expires_at: str
    state: str = ACTIVE
    consumed_minor: int = 0
    granted_at: str = field(default_factory=_utcnow)
    audit: List[dict] = field(default_factory=list)
    act_ids: Dict[str, dict] = field(default_factory=dict)

    def public(self) -> dict:
        return {"covenant_id": self.covenant_id, "principal": self.principal,
                "agent_id": self.agent_id, "scopes": list(self.scopes),
                "budget_minor": self.budget_minor,
                "consumed_minor": self.consumed_minor,
                "remaining_minor": self.budget_minor - self.consumed_minor,
                "expires_at": self.expires_at, "state": self.state,
                "granted_at": self.granted_at, "checks": len(self.audit)}


class CovenantAgentCore(AgentCore):
    """Machine-checkable authority leases: deny-by-default agent authority."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-covenant-agent"))
        self._covenants: Dict[str, Covenant] = {}
        self._seq = 0

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object", error_type="ValidationError",
                                 field="input", value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "grant": self._grant,
                "check_act": self._check_act,
                "revoke": self._revoke,
                "status": self._status,
                "verify_audit": self._verify_audit,
                "list": self._list,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'", error_type="ValidationError",
                                 field="action", value=action,
                                 constraint="one of: grant, check_act, revoke, status, "
                                            "verify_audit, list")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError", field=e.field,
                             value=e.value, constraint=e.constraint)
        except Exception as e:  # noqa: BLE001
            self.logger.exception("covenant process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ------------------------------------------------------------------ #
    def _covenant(self, data: dict) -> Covenant:
        cid = data.get("covenant_id")
        cov = self._covenants.get(cid)
        if cov is None:  # C8
            raise ValidationError("unknown covenant", field="covenant_id", value=cid,
                                  constraint="must exist")
        return cov

    def _grant(self, data: dict) -> dict:
        for f in ("principal", "agent_id", "expires_at"):
            if not data.get(f) or not isinstance(data.get(f), str):
                raise ValidationError(f"missing '{f}'", field=f, constraint="non-empty str")
        scopes = data.get("scopes")
        if not isinstance(scopes, list) or not scopes or \
                not all(isinstance(s, str) and s for s in scopes):
            raise ValidationError("scopes must be a non-empty list of strings",
                                  field="scopes", value=scopes, constraint="list[str], len>=1")
        budget = data.get("budget_minor")
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
            raise ValidationError("budget_minor must be a non-negative integer",
                                  field="budget_minor", value=budget, constraint="int >= 0")
        try:
            datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        except ValueError:
            raise ValidationError("expires_at must be ISO-8601", field="expires_at",
                                  value=data["expires_at"], constraint="ISO-8601 datetime")
        self._seq += 1
        cid = f"cov-{self._seq:06d}"
        cov = Covenant(covenant_id=cid, principal=data["principal"],
                       agent_id=data["agent_id"], scopes=list(scopes),
                       budget_minor=budget, expires_at=data["expires_at"])
        self._covenants[cid] = cov
        return self._ok(cov.public())

    def _append_audit(self, cov: Covenant, record: dict) -> dict:
        prev = cov.audit[-1]["entry_hash"] if cov.audit else _GENESIS
        body = {**record, "at": _utcnow(), "prev_hash": prev}
        entry = {**body, "entry_hash": _hash(body, prev)}  # C3
        cov.audit.append(entry)
        return entry

    def _now(self, data: dict) -> datetime:
        """Injectable clock: tests may pass 'now' to exercise expiry (C6)."""
        raw = data.get("now")
        if raw:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return datetime.now(timezone.utc)

    def _check_act(self, data: dict) -> dict:
        cov = self._covenant(data)
        act_id = data.get("act_id")
        if not act_id or not isinstance(act_id, str):
            raise ValidationError("missing 'act_id'", field="act_id", constraint="non-empty str")
        if act_id in cov.act_ids:  # C7 idempotent
            return self._ok({**cov.act_ids[act_id], "duplicate": True})
        scope = data.get("scope")
        if not scope or not isinstance(scope, str):
            raise ValidationError("missing 'scope'", field="scope", constraint="non-empty str")
        amount = data.get("amount_minor", 0)
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ValidationError("amount_minor must be a non-negative integer",
                                  field="amount_minor", value=amount, constraint="int >= 0")

        # C1 deny-by-default: collect the first failing reason
        allowed, reason = True, "within covenant"
        if cov.state == REVOKED:  # C4
            allowed, reason = False, "covenant revoked"
        elif cov.state == EXPIRED:
            allowed, reason = False, "covenant expired"
        else:
            expiry = datetime.fromisoformat(cov.expires_at.replace("Z", "+00:00"))
            if self._now(data) >= expiry:  # C6
                cov.state = EXPIRED
                allowed, reason = False, "covenant expired"
            elif not _scope_covers(cov.scopes, scope):  # C5
                allowed, reason = False, f"scope '{scope}' not granted"
            elif cov.consumed_minor + amount > cov.budget_minor:  # C2
                allowed, reason = False, (f"budget exceeded: {amount} > "
                                          f"{cov.budget_minor - cov.consumed_minor} remaining")
        if allowed and amount:
            cov.consumed_minor += amount  # C2 monotone
        entry = self._append_audit(cov, {
            "act_id": act_id, "scope": scope, "amount_minor": amount,
            "allowed": allowed, "reason": reason,
            "remaining_minor": cov.budget_minor - cov.consumed_minor,
        })
        result = {"covenant_id": cov.covenant_id, "act_id": act_id,
                  "allowed": allowed, "reason": reason,
                  "remaining_minor": cov.budget_minor - cov.consumed_minor,
                  "audit_hash": entry["entry_hash"], "duplicate": False}
        cov.act_ids[act_id] = result
        return self._ok(result)

    def _revoke(self, data: dict) -> dict:
        cov = self._covenant(data)
        if cov.state != REVOKED:  # C4 terminal
            cov.state = REVOKED
            self._append_audit(cov, {"act_id": None, "scope": None, "amount_minor": 0,
                                     "allowed": False,
                                     "reason": f"REVOKED by principal: "
                                               f"{data.get('reason', '')}",
                                     "remaining_minor": cov.budget_minor - cov.consumed_minor})
        return self._ok(cov.public())

    def _status(self, data: dict) -> dict:
        return self._ok(self._covenant(data).public())

    def _verify_audit(self, data: dict) -> dict:  # C3
        cov = self._covenant(data)
        prev = _GENESIS
        for i, e in enumerate(cov.audit):
            body = {k: v for k, v in e.items() if k != "entry_hash"}
            if e["prev_hash"] != prev or _hash(body, prev) != e["entry_hash"]:
                return self._ok({"covenant_id": cov.covenant_id, "valid": False,
                                 "broken_at_index": i})
            prev = e["entry_hash"]
        return self._ok({"covenant_id": cov.covenant_id, "valid": True,
                         "checks": len(cov.audit)})

    def _list(self, data: dict) -> dict:
        state = data.get("state")
        agent_id = data.get("agent_id")
        items = [c.public() for c in self._covenants.values()
                 if (state is None or c.state == state)
                 and (agent_id is None or c.agent_id == agent_id)]
        return self._ok({"count": len(items), "covenants": items})

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"covenants": len(self._covenants),
                       "active": sum(1 for c in self._covenants.values()
                                     if c.state == ACTIVE)}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Machine-checkable authority leases for agents: scoped, "
                           "budgeted, expiring, revocable, audited. Deny-by-default.",
            "capabilities": ["grant", "check_act", "revoke", "status",
                             "verify_audit", "list"],
            "inputs": {"action": "str", "covenant_id": "str", "principal": "str",
                       "agent_id": "str", "scopes": "list[str] (wildcards: 'x.*', '*')",
                       "budget_minor": "int >= 0", "expires_at": "ISO-8601",
                       "act_id": "str", "scope": "str", "amount_minor": "int >= 0"},
            "outputs": {"status": "str (ok|error)", "data": "dict"},
            "a2a_role": "authority",
        }


def build(config: Optional[AgentConfig] = None) -> CovenantAgentCore:
    return CovenantAgentCore(config)
