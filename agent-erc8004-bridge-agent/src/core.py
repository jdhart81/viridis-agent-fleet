"""
agent-erc8004-bridge-agent — Core business logic.

The MCP-native bridge to ERC-8004, the on-chain agent identity/reputation/
validation standard (Ethereum Foundation + Google + Coinbase, mainnet Feb
2026, 170k+ registered agents). Strategy per the 2026-07-10 offering review:
we do NOT compete with a ratified standard backed by that network — we become
its most useful off-chain surface. This bridge lets any MCP caller resolve
ERC-8004 registrations, import their feedback into Viridis decay-weighted
scoring (a real improvement over raw feedback lists), bind on-chain identities
to fleet DIDs, and export our tamper-evident attestations as UNSIGNED
ERC-8004-shaped payloads ready for the caller's own signer.

Custody note: this bridge NEVER touches private keys and NEVER writes to any
chain. It is a read/format/score layer; anchoring is the caller's act.

Fleet-standard interface: async process(), async health(), sync describe().

--- INVARIANTS (spec-invariance contract) ---
B1  Deterministic bridge DIDs: the same (chain_id, token_id) always maps to
    the same DID (did:viridis:erc8004:<chain_id>:<token_id>); distinct
    (chain_id, token_id) map to distinct DIDs. Records are additionally
    content-addressed (record_hash over canonical JSON).
B2  Import is idempotent on (chain_id, token_id): re-import updates fields
    in place — the registry count never grows from a re-import.
B3  Scoring: decay-weighted score is always in [0.0, 1.0]; an agent with no
    feedback scores the neutral prior 0.5; positive feedback never lowers a
    score, negative never raises it; newer feedback outweighs older
    (half-life decay applied at query time).
B4  Exported attestations and bindings are content-addressed: verify()
    recomputes the SHA-256 and detects any tampering.
B5  No key custody, no chain writes: any input containing key material
    (private_key / secret / mnemonic / keystore) is REFUSED with a
    structured error; every exported payload is explicitly marked unsigned.
B6  process() never raises on bad input — structured error envelope, always.
B7  Resolution is total over imports: every imported registration is
    resolvable by bridge DID and by (chain_id, token_id), and returns the
    canonical record.
B8  Binding is symmetric: bind(fleet_did, erc8004_ref) produces the same
    content hash regardless of argument order — one binding, two directions.
B9  export_validation_response (ORC v0.1 evidence for the ERC-8004
    Validation Registry): responseHash = 0x + the receipt's commitment,
    tag = "orc/0.1", response is 100 ONLY if the bridge itself re-verifies
    the receipt at L1 AND the caller reports a successful replay; otherwise 0.
    Unsigned, no chain writes (B5 holds).
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KEY_MATERIAL_FIELDS = frozenset({
    "private_key", "privatekey", "secret", "secret_key", "mnemonic",
    "seed_phrase", "keystore", "signing_key",
})

TIERS = ((0.85, "TRUSTED"), (0.65, "RELIABLE"), (0.40, "NEUTRAL"),
         (0.20, "CAUTION"), (0.0, "UNTRUSTED"))


@dataclass
class AgentConfig:
    name: str
    version: str = "0.2.0"
    debug: bool = False
    half_life_days: float = 30.0
    prior_strength: float = 2.0   # Beta(1,1)-equivalent pseudo-counts


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utcnow()).isoformat()


HASH_EXCLUDED = frozenset({"content_hash", "issued_at"})
# issued_at is excluded from content hashes by design: a binding or
# attestation's identity is its content, not the second it was minted.


def _canonical_hash(payload: dict) -> str:
    body = json.dumps({k: v for k, v in payload.items()
                       if k not in HASH_EXCLUDED},
                      sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


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


@dataclass
class Feedback:
    value: float          # in [0,1]: 1 = positive, 0 = negative
    at: datetime
    source: str = ""
    weight: float = 1.0
    feedback_id: str = ""


@dataclass
class Registration:
    chain_id: int
    token_id: int
    agent_uri: str
    owner: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    imported_at: str = ""
    updated_at: str = ""
    feedback: List[Feedback] = field(default_factory=list)
    bindings: List[dict] = field(default_factory=list)

    @property
    def bridge_did(self) -> str:                          # B1
        return f"did:viridis:erc8004:{self.chain_id}:{self.token_id}"

    def public(self) -> dict:
        rec = {"bridge_did": self.bridge_did, "chain_id": self.chain_id,
               "token_id": self.token_id, "agent_uri": self.agent_uri,
               "owner": self.owner, "metadata": self.metadata,
               "imported_at": self.imported_at, "updated_at": self.updated_at,
               "feedback_count": len(self.feedback),
               "bindings": self.bindings}
        rec["record_hash"] = _canonical_hash(
            {k: v for k, v in rec.items() if k != "record_hash"})   # B1/B4
        return rec


class Erc8004BridgeCore(AgentCore):
    """Read/score/format bridge between MCP callers and ERC-8004 registries."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-erc8004-bridge-agent"))
        self._registry: Dict[str, Registration] = {}   # key = bridge DID

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"registrations": len(self._registry),
                       "feedback_records": sum(len(r.feedback)
                                               for r in self._registry.values())}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "capabilities": ["import_registration", "resolve", "import_feedback",
                             "score", "bind", "export_attestation", "verify",
                             "list", "export_validation_response"],
            "inputs": {"action": "one of capabilities", "...": "per action"},
            "outputs": {"status": "ok|error", "data": "per action"},
            "a2a_role": "identity-bridge",
        }

    # ------------------------------------------------------------------ #
    @staticmethod
    def _reject_key_material(input_data: dict) -> Optional[str]:      # B5
        def scan(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    kl = str(k).lower().replace("-", "_")
                    if kl in KEY_MATERIAL_FIELDS:
                        return f"{path}{k}"
                    found = scan(v, f"{path}{k}.")
                    if found:
                        return found
            return None
        return scan(input_data)

    def _get(self, input_data: dict) -> Registration:
        did = input_data.get("bridge_did")
        if did:
            reg = self._registry.get(did)
            if reg is None:
                raise ValidationError(f"unknown bridge_did '{did}'",
                                      field="bridge_did", value=did,
                                      constraint="an imported registration")
            return reg
        chain_id, token_id = input_data.get("chain_id"), input_data.get("token_id")
        if chain_id is None or token_id is None:
            raise ValidationError("provide bridge_did or chain_id+token_id",
                                  field="bridge_did|chain_id+token_id",
                                  value=None, constraint="required")
        key = f"did:viridis:erc8004:{int(chain_id)}:{int(token_id)}"
        reg = self._registry.get(key)
        if reg is None:
            raise ValidationError(f"unknown registration ({chain_id},{token_id})",
                                  field="chain_id,token_id",
                                  value=f"{chain_id},{token_id}",
                                  constraint="an imported registration")
        return reg

    # -- dispatch ---------------------------------------------------------
    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object",
                                 error_type="ValidationError", field="input",
                                 value=type(input_data).__name__, constraint="dict")
            leak = self._reject_key_material(input_data)                # B5
            if leak:
                return self._err(
                    f"key material refused (field '{leak}'): this bridge never "
                    "holds keys and never writes to any chain — sign exported "
                    "payloads with your own signer",
                    error_type="KeyMaterialRefused", field=leak,
                    constraint="no private keys, ever")
            action = input_data.get("action")
            handler = {
                "import_registration": self._import_registration,
                "resolve": self._resolve,
                "import_feedback": self._import_feedback,
                "score": self._score,
                "bind": self._bind,
                "export_attestation": self._export_attestation,
                "verify": self._verify,
                "list": self._list,
                "export_validation_response": self._export_validation_response,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'",
                                 error_type="ValidationError", field="action",
                                 value=action,
                                 constraint="one of: import_registration, resolve, "
                                            "import_feedback, score, bind, "
                                            "export_attestation, verify, list, "
                                            "export_validation_response")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError",
                             field=e.field, value=e.value, constraint=e.constraint)
        except Exception as e:                                           # B6
            self.logger.exception("erc8004-bridge process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # -- operations --------------------------------------------------------
    def _import_registration(self, d: dict) -> dict:
        for f in ("chain_id", "token_id", "agent_uri", "owner"):
            if d.get(f) in (None, ""):
                raise ValidationError(f"'{f}' is required", field=f,
                                      value=d.get(f), constraint="non-empty")
        try:
            chain_id, token_id = int(d["chain_id"]), int(d["token_id"])
        except (TypeError, ValueError):
            raise ValidationError("chain_id and token_id must be integers",
                                  field="chain_id,token_id",
                                  value=f"{d.get('chain_id')},{d.get('token_id')}",
                                  constraint="int")
        if chain_id < 0 or token_id < 0:
            raise ValidationError("chain_id and token_id must be >= 0",
                                  field="chain_id,token_id",
                                  value=f"{chain_id},{token_id}", constraint=">=0")
        key = f"did:viridis:erc8004:{chain_id}:{token_id}"
        now = _iso()
        existing = self._registry.get(key)
        if existing is not None:                                        # B2
            existing.agent_uri = str(d["agent_uri"])
            existing.owner = str(d["owner"])
            if isinstance(d.get("metadata"), dict):
                existing.metadata = d["metadata"]
            existing.updated_at = now
            return self._ok({**existing.public(), "idempotent_update": True})
        reg = Registration(chain_id=chain_id, token_id=token_id,
                           agent_uri=str(d["agent_uri"]), owner=str(d["owner"]),
                           metadata=d.get("metadata") or {},
                           imported_at=now, updated_at=now)
        self._registry[key] = reg                                       # B1/B7
        return self._ok({**reg.public(), "idempotent_update": False})

    def _resolve(self, d: dict) -> dict:                                # B7
        return self._ok(self._get(d).public())

    def _import_feedback(self, d: dict) -> dict:
        reg = self._get(d)
        items = d.get("feedback")
        if not isinstance(items, list) or not items:
            raise ValidationError("'feedback' must be a non-empty list",
                                  field="feedback", value=items,
                                  constraint="[{value, at, ...}]")
        seen = {f.feedback_id for f in reg.feedback if f.feedback_id}
        imported = skipped = 0
        for item in items:
            if not isinstance(item, dict):
                raise ValidationError("each feedback item must be an object",
                                      field="feedback[]", value=item,
                                      constraint="dict")
            fid = str(item.get("feedback_id") or "")
            if fid and fid in seen:
                skipped += 1
                continue
            raw = item.get("value")
            if isinstance(raw, bool):
                value = 1.0 if raw else 0.0
            else:
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    raise ValidationError("feedback value must be bool or number "
                                          "in [0,1]", field="feedback[].value",
                                          value=raw, constraint="0.0-1.0")
            if not 0.0 <= value <= 1.0:
                raise ValidationError("feedback value out of range",
                                      field="feedback[].value", value=value,
                                      constraint="0.0-1.0")
            at_raw = item.get("at")
            try:
                at = (datetime.fromisoformat(str(at_raw).replace("Z", "+00:00"))
                      if at_raw else _utcnow())
                if at.tzinfo is None:
                    at = at.replace(tzinfo=timezone.utc)
            except ValueError:
                raise ValidationError("feedback 'at' must be ISO-8601",
                                      field="feedback[].at", value=at_raw,
                                      constraint="ISO-8601")
            weight = float(item.get("weight", 1.0))
            if weight <= 0:
                raise ValidationError("feedback weight must be > 0",
                                      field="feedback[].weight", value=weight,
                                      constraint=">0")
            reg.feedback.append(Feedback(value=value, at=at,
                                         source=str(item.get("source", "")),
                                         weight=weight, feedback_id=fid))
            if fid:
                seen.add(fid)
            imported += 1
        reg.updated_at = _iso()
        return self._ok({"bridge_did": reg.bridge_did, "imported": imported,
                         "skipped_duplicates": skipped,
                         "feedback_count": len(reg.feedback)})

    # -- scoring (B3) -------------------------------------------------------
    def _decayed_counts(self, reg: Registration, now: datetime):
        hl = max(self.config.half_life_days, 1e-6)
        s = f = 0.0
        for fb in reg.feedback:
            age_days = max((now - fb.at).total_seconds() / 86400.0, 0.0)
            decay = 0.5 ** (age_days / hl)
            s += fb.value * fb.weight * decay
            f += (1.0 - fb.value) * fb.weight * decay
        return s, f

    @staticmethod
    def _tier(score: float) -> str:
        for cutoff, tier in TIERS:
            if score >= cutoff:
                return tier
        return "UNTRUSTED"

    def _score_value(self, reg: Registration, now: Optional[datetime] = None) -> float:
        now = now or _utcnow()
        s, f = self._decayed_counts(reg, now)
        prior = self.config.prior_strength
        score = (s + prior * 0.5) / (s + f + prior)      # Beta-smoothed, B3
        return min(max(score, 0.0), 1.0)

    def _score(self, d: dict) -> dict:
        reg = self._get(d)
        score = self._score_value(reg)
        return self._ok({"bridge_did": reg.bridge_did,
                         "score": round(score, 6), "tier": self._tier(score),
                         "feedback_count": len(reg.feedback),
                         "half_life_days": self.config.half_life_days,
                         "method": "decay-weighted Beta-smoothed "
                                   "(viridis trust-oracle math over "
                                   "ERC-8004 feedback)"})

    # -- binding (B8) --------------------------------------------------------
    def _bind(self, d: dict) -> dict:
        fleet_did = d.get("fleet_did")
        if not fleet_did or not str(fleet_did).startswith("did:"):
            raise ValidationError("'fleet_did' must be a DID",
                                  field="fleet_did", value=fleet_did,
                                  constraint="did:*")
        reg = self._get(d)
        pair = sorted([str(fleet_did), reg.bridge_did])          # B8: symmetric
        binding = {"type": "identity-binding",
                   "parties": pair,
                   "erc8004": {"chain_id": reg.chain_id,
                               "token_id": reg.token_id,
                               "owner": reg.owner},
                   "note": str(d.get("proof_note", "")),
                   "issued_at": _iso(),
                   "signed": False}                              # B5
        binding["content_hash"] = _canonical_hash(binding)
        reg.bindings.append(binding)
        reg.updated_at = _iso()
        return self._ok(binding)

    # -- export / verify (B4, B5) --------------------------------------------
    def _export_attestation(self, d: dict) -> dict:
        reg = self._get(d)
        score = self._score_value(reg)
        payload = {
            "standard": "ERC-8004",
            "registry": "validation",
            "subject": {"chain_id": reg.chain_id, "token_id": reg.token_id,
                        "bridge_did": reg.bridge_did},
            "claim": "viridis-decay-weighted-trust-score",
            "score": round(score, 6),
            "tier": self._tier(score),
            "feedback_count": len(reg.feedback),
            "issuer": self.config.name,
            "issued_at": _iso(),
            "signed": False,                                     # B5
            "anchoring": "sign and submit with YOUR OWN signer — this bridge "
                         "holds no keys and writes to no chain",
        }
        payload["content_hash"] = _canonical_hash(payload)              # B4
        return self._ok(payload)

    def _verify(self, d: dict) -> dict:                          # B4
        payload = d.get("payload")
        if not isinstance(payload, dict) or "content_hash" not in payload:
            raise ValidationError("'payload' must be an exported object with "
                                  "content_hash", field="payload", value=None,
                                  constraint="dict with content_hash")
        claimed = payload["content_hash"]
        recomputed = _canonical_hash(payload)
        return self._ok({"valid": claimed == recomputed,
                         "claimed": claimed, "recomputed": recomputed})

    @staticmethod
    def _orc_l1(receipt: Any) -> Dict[str, bool]:
        """Stdlib re-verification of an ORC v0.1 receipt at level 1."""
        out = {"digest_recomputes": False, "commitment_binds": False}
        try:
            dg, cm = receipt["digest"], receipt["commitment"]
            if (receipt.get("orc") != "0.1" or dg.get("alg") != "sha256"
                    or dg.get("canonicalization") != "orc-canon/1"
                    or cm.get("scheme") != "sha256(salt||digest)"):
                return out
            excl = set(dg.get("excludes") or [])
            content = {k: v for k, v in receipt["output"].items() if k not in excl}
            canon = json.dumps(content, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True)
            out["digest_recomputes"] = (
                hashlib.sha256(canon.encode()).hexdigest() == dg.get("value"))
            out["commitment_binds"] = (
                hashlib.sha256((str(cm["salt"]) + str(dg.get("value"))).encode())
                .hexdigest() == cm.get("value"))
        except (KeyError, TypeError, AttributeError):
            pass
        return out

    def _export_validation_response(self, d: dict) -> dict:      # B9
        receipt = d.get("receipt")
        if not isinstance(receipt, dict):
            raise ValidationError("'receipt' must be an ORC v0.1 object",
                                  field="receipt", value=type(receipt).__name__,
                                  constraint="object")
        rh = str(d.get("request_hash", "")).lower()
        rh = rh[2:] if rh.startswith("0x") else rh
        if len(rh) != 64 or any(c not in "0123456789abcdef" for c in rh):
            raise ValidationError("'request_hash' must be 32 bytes hex",
                                  field="request_hash", value=d.get("request_hash"),
                                  constraint="0x + 64 hex")
        uri = str(d.get("response_uri", ""))
        if not uri.startswith("https://"):
            raise ValidationError("'response_uri' must be an https URL where "
                                  "the receipt is published",
                                  field="response_uri", value=uri,
                                  constraint="https://...")
        replay_ok = d.get("replay_ok")
        if not isinstance(replay_ok, bool):
            raise ValidationError("'replay_ok' must be a boolean",
                                  field="replay_ok", value=replay_ok,
                                  constraint="bool")
        check = self._orc_l1(receipt)
        passed = replay_ok and all(check.values())
        commitment = str(receipt.get("commitment", {}).get("value", ""))
        payload = {
            "standard": "ERC-8004",
            "registry": "validation",
            "function": "validationResponse",
            "args": {"requestHash": "0x" + rh,
                     "response": 100 if passed else 0,
                     "responseURI": uri,
                     "responseHash": "0x" + commitment,
                     "tag": "orc/0.1"},
            "orc_check": check,
            "replay_ok": replay_ok,
            "issuer": self.config.name,
            "issued_at": _iso(),
            "signed": False,                                     # B5
            "anchoring": "sign and submit with YOUR OWN signer — this bridge "
                         "holds no keys and writes to no chain",
        }
        payload["content_hash"] = _canonical_hash(payload)              # B4
        return self._ok(payload)

    def _list(self, d: dict) -> dict:
        return self._ok({"count": len(self._registry),
                         "registrations": [r.public()
                                           for r in self._registry.values()]})


def build(config: Optional[AgentConfig] = None) -> Erc8004BridgeCore:
    return Erc8004BridgeCore(config)
