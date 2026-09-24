"""
agent-identity-registry-agent — Core business logic.

The "passport + directory" of the agent-to-agent economy. Agents register a
verifiable identity, advertise capabilities and prices, and become discoverable
by other agents. This is the supply-side complement to intent-routing
(wavefunction-search does demand-side matching); together they form a market.

It is the hub the other two novel A2A agents plug into:
    identity (who you are) -> trust-oracle (whether to deal with you) -> escrow (safe txn).

Fleet-standard interface: async process(), async health(), sync describe().

--- INVARIANTS (spec-invariance contract) ---
R1  DID is deterministic + content-addressed:
        did:viridis:<first16 hex of sha256(agent_id|pubkey)>
    Same (agent_id, pubkey) always yields the same DID.
R2  register is idempotent on agent_id: re-registering updates the record and
    bumps a monotonic version counter; it never creates a duplicate.
R3  discover returns only ACTIVE (non-revoked) records, and every returned
    record matches ALL requested capability tags (AND semantics).
R4  discover results are sorted deterministically: by capability-match count
    desc, then reputation_hint desc, then did asc — stable ordering.
R5  resolve on unknown id/did -> error envelope, never a crash.
R6  revoke is terminal for discovery (status=REVOKED) but the record is
    retained for audit (resolve still returns it with its status).
R7  capabilities is a non-empty list of short string tags; enforced at register.
R8  process() never raises on bad input — returns a structured error envelope.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ACTIVE, REVOKED = "ACTIVE", "REVOKED"


@dataclass
class AgentConfig:
    name: str
    version: str = "0.1.1"
    debug: bool = False


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
                "value": value, "constraint": constraint, "message": message, "timestamp": _iso()}

    def _ok(self, data=None) -> dict:
        return {"status": "ok", "data": data, "error": None, "timestamp": _iso()}


@dataclass
class Registration:
    agent_id: str
    did: str
    name: str
    capabilities: List[str]
    endpoint: str
    pubkey: str
    pricing: Dict[str, Any] = field(default_factory=dict)
    reputation_hint: float = 0.5
    status: str = ACTIVE
    version: int = 1
    created_at: str = field(default_factory=_iso)
    updated_at: str = field(default_factory=_iso)

    def public(self) -> dict:
        return {
            "agent_id": self.agent_id, "did": self.did, "name": self.name,
            "capabilities": list(self.capabilities), "endpoint": self.endpoint,
            "pricing": self.pricing, "reputation_hint": self.reputation_hint,
            "status": self.status, "version": self.version,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


class IdentityRegistryCore(AgentCore):
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-identity-registry-agent"))
        self._by_id: Dict[str, Registration] = {}
        self._by_did: Dict[str, str] = {}  # did -> agent_id

    @staticmethod
    def _make_did(agent_id: str, pubkey: str) -> str:  # R1
        h = hashlib.sha256(f"{agent_id}|{pubkey}".encode()).hexdigest()[:16]
        return f"did:viridis:{h}"

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object", error_type="ValidationError",
                                 field="input", value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "register": self._register,
                "resolve": self._resolve,
                "discover": self._discover,
                "revoke": self._revoke,
                "list": self._list,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'", error_type="ValidationError",
                                 field="action", value=action,
                                 constraint="one of: register, resolve, discover, revoke, list")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError", field=e.field,
                             value=e.value, constraint=e.constraint)
        except Exception as e:
            self.logger.exception("identity-registry process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    def _require(self, data, f):
        if f not in data:
            raise ValidationError(f"missing '{f}'", field=f, constraint="required")
        return data[f]

    def _register(self, data: dict) -> dict:
        agent_id = self._require(data, "agent_id")
        caps = data.get("capabilities")
        if not isinstance(caps, list) or not caps or not all(isinstance(c, str) and c for c in caps):  # R7
            raise ValidationError("capabilities must be a non-empty list of string tags",
                                  field="capabilities", value=caps, constraint="list[str], len>=1")
        pubkey = data.get("pubkey", "")
        did = self._make_did(agent_id, pubkey)
        existing = self._by_id.get(agent_id)
        if existing:  # R2 idempotent update
            existing.name = data.get("name", existing.name)
            existing.capabilities = [c.lower() for c in caps]
            existing.endpoint = data.get("endpoint", existing.endpoint)
            existing.pubkey = pubkey or existing.pubkey
            existing.pricing = data.get("pricing", existing.pricing)
            existing.reputation_hint = float(data.get("reputation_hint", existing.reputation_hint))
            existing.did = did
            existing.status = ACTIVE
            existing.version += 1
            existing.updated_at = _iso()
            self._by_did[did] = agent_id
            return self._ok({**existing.public(), "created": False})
        reg = Registration(
            agent_id=agent_id, did=did, name=data.get("name", agent_id),
            capabilities=[c.lower() for c in caps], endpoint=data.get("endpoint", ""),
            pubkey=pubkey, pricing=data.get("pricing", {}),
            reputation_hint=float(data.get("reputation_hint", 0.5)),
        )
        self._by_id[agent_id] = reg
        self._by_did[did] = agent_id
        return self._ok({**reg.public(), "created": True})

    def _find(self, ident: str) -> Optional[Registration]:
        if ident in self._by_id:
            return self._by_id[ident]
        if ident in self._by_did:
            return self._by_id[self._by_did[ident]]
        return None

    def _resolve(self, data: dict) -> dict:
        ident = data.get("agent_id") or data.get("did")
        if not ident:
            raise ValidationError("provide agent_id or did", field="agent_id", constraint="required")
        reg = self._find(ident)
        if reg is None:  # R5
            raise ValidationError("unknown identity", field="agent_id", value=ident, constraint="must exist")
        return self._ok(reg.public())

    def _discover(self, data: dict) -> dict:
        want = [c.lower() for c in data.get("capabilities", []) if isinstance(c, str)]
        limit = int(data.get("limit", 25))
        matches = []
        for reg in self._by_id.values():
            if reg.status != ACTIVE:  # R3
                continue
            regset = set(reg.capabilities)
            if want and not set(want).issubset(regset):  # R3 AND semantics
                continue
            match_count = len(set(want) & regset) if want else len(regset)
            matches.append((match_count, reg))
        matches.sort(key=lambda t: (-t[0], -t[1].reputation_hint, t[1].did))  # R4
        results = [{**reg.public(), "match_count": mc} for mc, reg in matches[:limit]]
        return self._ok({"count": len(results), "results": results})

    def _revoke(self, data: dict) -> dict:
        ident = data.get("agent_id") or data.get("did")
        reg = self._find(ident) if ident else None
        if reg is None:
            raise ValidationError("unknown identity", field="agent_id", value=ident, constraint="must exist")
        reg.status = REVOKED  # R6
        reg.updated_at = _iso()
        return self._ok(reg.public())

    def _list(self, data: dict) -> dict:
        status = data.get("status")
        items = [r.public() for r in self._by_id.values() if status is None or r.status == status]
        return self._ok({"count": len(items), "registrations": items})

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Verifiable agent identity (DIDs) + capability advertising & discovery.",
            "capabilities": ["register", "resolve", "discover", "revoke", "list"],
            "inputs": {"action": "str", "agent_id": "str", "capabilities": "list[str]",
                       "endpoint": "str", "pubkey": "str", "pricing": "dict"},
            "outputs": {"status": "str (ok|error)", "data": "dict"},
            "a2a_role": "identity",
        }

    async def health(self) -> dict:
        h = await super().health()
        active = sum(1 for r in self._by_id.values() if r.status == ACTIVE)
        h["checks"] = {"registered": len(self._by_id), "active": active}
        return h


def build(config: Optional[AgentConfig] = None) -> IdentityRegistryCore:
    return IdentityRegistryCore(config)
