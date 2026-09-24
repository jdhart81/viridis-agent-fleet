"""
agent-provenance-agent — Core business logic.

Birth certificates and bloodlines for the agent economy. The founding happens
exactly once: this agent issues content-addressed GENESIS CERTIFICATES with
strictly monotone sequence numbers (the founding cohort is provably first),
records parent -> child lineage as agents spawn agents, and — the safety
mechanism nobody else has — cascades RECALLS down the family tree: when an
ancestor is found compromised, every descendant is flagged, and new agents
born to a recalled parent are quarantined at birth.

Provenance turns the fleet's "living ecology" (agents spawning agents) from a
risk into an audited genealogy. Pairs with agent-identity-registry-agent
(identity says WHO you are; provenance says WHERE YOU CAME FROM).

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input.

--- INVARIANTS (spec-invariance contract) ---
V1  Genesis certificates are content-addressed and immutable: the certificate
    hash is reproducible from its contents; verify_certificate recomputes it.
V2  Sequence is strictly monotone: every certificate gets genesis_index =
    previous + 1, never reused, never reordered. Epoch 0 (the founding
    cohort) is the first FOUNDING_COHORT_SIZE registrations — determined by
    index alone, forever.
V3  Lineage is acyclic by construction: a parent must already be registered
    (so ancestry only points backward in time) and self-parenting is
    rejected.
V4  Recall cascades: recalling an agent flags it AND all transitive
    descendants; the response reports exactly which.
V5  Recalled lineage is sticky: an agent registered with a recalled (or
    flagged) parent is quarantined at birth.
V6  verify_certificate recomputes the content hash; any tampering is
    detected.
V7  Registration is idempotent on agent_id: re-registering returns the
    original certificate — an agent is born once.
V8  Unknown agent_id -> error envelope, never a crash.

--- ARTIFACT DOMAIN INVARIANTS (separate from V1-V8) ---
A1  Artifact registration is a separate namespace and never consumes a genesis
    index, changes the founding cohort, or enters agent recall lineage.
A2  Artifact records are content-addressed; record_hash commits to the artifact
    digest, producer, parent hashes, relation, metadata digest, and timestamp.
A3  Parent hashes form an acyclic content-addressed DAG; self and transitive
    cycles are rejected, including when a formerly external parent is added.
A4  artifact_id is idempotent only for an identical canonical integrity
    payload; conflicting reuse fails closed. artifact_hash remains unique.
A5  verify_artifact recomputes the record hash and detects tampering.
A6  Artifact state uses built-in dict/list values only for rollback-safe
    persistence; parent hashes are canonicalized deterministically.
A7  Unknown artifacts and malformed content digests fail loud with an error
    envelope, never a crash.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FOUNDING_COHORT_SIZE = 100  # epoch 0: the first hundred. Once.
EPOCH_SIZE = 1000           # subsequent epochs


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
def _cert_hash(content: dict) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _epoch(index: int) -> int:
    if index < FOUNDING_COHORT_SIZE:
        return 0
    return 1 + (index - FOUNDING_COHORT_SIZE) // EPOCH_SIZE


def _require_sha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 \
            or any(c not in "0123456789abcdef" for c in value):
        raise ValidationError(
            f"'{field_name}' must be a bare lowercase SHA-256 hex digest",
            field=field_name, value=value,
            constraint="64 lowercase hex characters")
    return value


_ARTIFACT_CONTENT_FIELDS = (
    "artifact_id", "artifact_hash", "producer_agent_id", "parent_hashes",
    "relation", "metadata_digest", "registered_at",
)


@dataclass
class Record:
    agent_id: str
    genesis_index: int
    epoch: int
    parent_id: Optional[str]
    artifact_hash: str
    born_at: str
    cert_hash: str
    quarantined: bool = False
    recalled: bool = False
    recall_reason: str = ""
    children: List[str] = field(default_factory=list)

    def certificate(self) -> dict:
        return {
            "agent_id": self.agent_id, "genesis_index": self.genesis_index,
            "epoch": self.epoch, "founding_cohort": self.epoch == 0,
            "parent_id": self.parent_id, "artifact_hash": self.artifact_hash,
            "born_at": self.born_at, "cert_hash": self.cert_hash,
        }

    def public(self) -> dict:
        return {**self.certificate(), "quarantined": self.quarantined,
                "recalled": self.recalled, "recall_reason": self.recall_reason,
                "children": list(self.children)}


class ProvenanceAgentCore(AgentCore):
    """Genesis certificates, lineage, and cascading recalls for agents."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-provenance-agent"))
        self._records: Dict[str, Record] = {}
        self._order: List[str] = []
        # Separate artifact DAG. Built-in containers only, so old-image
        # rollbacks can unpickle snapshots written by this version.
        self._artifacts: Dict[str, dict] = {}
        self._artifact_order: List[str] = []
        self._artifact_hash_index: Dict[str, str] = {}

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object", error_type="ValidationError",
                                 field="input", value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "register_genesis": self._register,
                "get_certificate": self._get_certificate,
                "verify_certificate": self._verify_certificate,
                "lineage": self._lineage,
                "recall": self._recall,
                "list": self._list,
                "register_artifact": self._register_artifact,
                "get_artifact": self._get_artifact,
                "verify_artifact": self._verify_artifact,
                "list_artifacts": self._list_artifacts,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'", error_type="ValidationError",
                                 field="action", value=action,
                                 constraint="one of: register_genesis, get_certificate, "
                                            "verify_certificate, lineage, recall, list, "
                                            "register_artifact, get_artifact, "
                                            "verify_artifact, list_artifacts")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError", field=e.field,
                             value=e.value, constraint=e.constraint)
        except Exception as e:  # noqa: BLE001
            self.logger.exception("provenance process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ------------------------------------------------------------------ #
    def _record(self, data: dict, key: str = "agent_id") -> Record:
        aid = data.get(key)
        rec = self._records.get(aid)
        if rec is None:  # V8
            raise ValidationError("unknown agent", field=key, value=aid,
                                  constraint="must be registered")
        return rec

    def _register(self, data: dict) -> dict:
        aid = data.get("agent_id")
        if not aid or not isinstance(aid, str):
            raise ValidationError("missing 'agent_id'", field="agent_id",
                                  constraint="non-empty str")
        if aid in self._records:  # V7 born once
            return self._ok({**self._records[aid].public(), "created": False})
        parent_id = data.get("parent_id")
        quarantined = False
        if parent_id is not None:
            if parent_id == aid:  # V3
                raise ValidationError("an agent cannot be its own parent",
                                      field="parent_id", value=parent_id,
                                      constraint="!= agent_id")
            parent = self._records.get(parent_id)
            if parent is None:  # V3 parent must pre-exist -> acyclic
                raise ValidationError("parent not registered", field="parent_id",
                                      value=parent_id, constraint="must be registered first")
            if parent.recalled or parent.quarantined:  # V5 sticky
                quarantined = True
        artifact_hash = data.get("artifact_hash", "")
        index = len(self._order)  # V2 strictly monotone
        content = {"agent_id": aid, "genesis_index": index, "epoch": _epoch(index),
                   "parent_id": parent_id, "artifact_hash": artifact_hash,
                   "born_at": _utcnow()}
        rec = Record(**content, cert_hash=_cert_hash(content),  # V1
                     quarantined=quarantined)
        self._records[aid] = rec
        self._order.append(aid)
        if parent_id:
            self._records[parent_id].children.append(aid)
        return self._ok({**rec.public(), "created": True})

    def _get_certificate(self, data: dict) -> dict:
        return self._ok(self._record(data).public())

    def _verify_certificate(self, data: dict) -> dict:  # V1/V6
        cert = data.get("certificate")
        if not isinstance(cert, dict) or "cert_hash" not in cert:
            raise ValidationError("certificate must be a dict with cert_hash",
                                  field="certificate", value=cert, constraint="dict")
        content = {k: cert.get(k) for k in ("agent_id", "genesis_index", "epoch",
                                            "parent_id", "artifact_hash", "born_at")}
        valid = _cert_hash(content) == cert["cert_hash"]
        registered = self._records.get(cert.get("agent_id"))
        matches_ledger = bool(registered and registered.cert_hash == cert["cert_hash"])
        return self._ok({"valid": valid and matches_ledger,
                         "hash_ok": valid, "on_ledger": matches_ledger})

    def _descendants(self, aid: str) -> List[str]:
        out, stack = [], list(self._records[aid].children)
        while stack:
            child = stack.pop()
            out.append(child)
            stack.extend(self._records[child].children)
        return out

    def _lineage(self, data: dict) -> dict:
        rec = self._record(data)
        ancestors = []
        cur = rec.parent_id
        while cur is not None:
            ancestors.append(cur)
            cur = self._records[cur].parent_id
        return self._ok({"agent_id": rec.agent_id, "ancestors": ancestors,
                         "descendants": self._descendants(rec.agent_id),
                         "generation": len(ancestors)})

    def _recall(self, data: dict) -> dict:  # V4
        rec = self._record(data)
        reason = data.get("reason", "")
        rec.recalled = True
        rec.recall_reason = reason
        flagged = self._descendants(rec.agent_id)
        for d in flagged:
            self._records[d].quarantined = True
        return self._ok({"agent_id": rec.agent_id, "recalled": True,
                         "reason": reason, "descendants_quarantined": flagged,
                         "quarantine_count": len(flagged)})

    def _list(self, data: dict) -> dict:
        epoch = data.get("epoch")
        items = [self._records[a].public() for a in self._order
                 if epoch is None or self._records[a].epoch == epoch]
        return self._ok({"count": len(items), "records": items,
                         "founding_cohort_size": FOUNDING_COHORT_SIZE})

    # ------------------------------------------------------------------ #
    # Artifact domain (A1-A7) — content lineage, never agent genealogy.
    def _artifact_reaches(self, start_hash: str, target_hash: str) -> bool:
        """Follow registered parent edges from start; external roots stop."""
        stack = [start_hash]
        seen = set()
        while stack:
            current = stack.pop()
            if current == target_hash:
                return True
            if current in seen:
                continue
            seen.add(current)
            artifact_id = self._artifact_hash_index.get(current)
            if artifact_id is not None:
                stack.extend(self._artifacts[artifact_id]["parent_hashes"])
        return False

    def _artifact_would_cycle(self, artifact_hash: str,
                              parent_hashes: List[str]) -> bool:
        return any(self._artifact_reaches(parent, artifact_hash)
                   for parent in parent_hashes)

    def _register_artifact(self, data: dict) -> dict:
        artifact_id = data.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise ValidationError("missing 'artifact_id'", field="artifact_id",
                                  value=artifact_id, constraint="non-empty str")
        artifact_hash = _require_sha256(data.get("artifact_hash"), "artifact_hash")
        producer = data.get("producer_agent_id")
        if not isinstance(producer, str) or not producer.strip():
            raise ValidationError("'producer_agent_id' must be a non-empty string",
                                  field="producer_agent_id", value=producer,
                                  constraint="non-empty str")
        parents = data.get("parent_hashes", [])
        if not isinstance(parents, list):
            raise ValidationError("'parent_hashes' must be a list",
                                  field="parent_hashes", value=parents,
                                  constraint="list[sha256 hex]")
        canonical_parents = sorted(set(
            _require_sha256(parent, "parent_hashes") for parent in parents
        ))
        relation = data.get("relation", "derived_from")
        if not isinstance(relation, str) or not relation.strip():
            raise ValidationError("'relation' must be a non-empty string",
                                  field="relation", value=relation,
                                  constraint="non-empty str")
        metadata_digest = data.get("metadata_digest", "")
        if metadata_digest != "":
            metadata_digest = _require_sha256(metadata_digest, "metadata_digest")

        producer = producer.strip()
        relation = relation.strip()
        if artifact_id in self._artifacts:  # A4 exact replay or conflict
            existing = self._artifacts[artifact_id]
            submitted = {
                "artifact_hash": artifact_hash,
                "producer_agent_id": producer,
                "parent_hashes": canonical_parents,
                "relation": relation,
                "metadata_digest": metadata_digest,
            }
            conflicts = [field for field, value in submitted.items()
                         if existing.get(field) != value]
            if conflicts:
                return self._err(
                    f"artifact_id '{artifact_id}' already exists with conflicting "
                    f"integrity fields: {', '.join(conflicts)}",
                    error_type="ConflictError", field="artifact_id",
                    value=artifact_id,
                    constraint=("existing artifact_id requires identical "
                                "artifact_hash, producer_agent_id, parent_hashes, "
                                "relation, and metadata_digest"))
            return self._ok({**existing, "created": False})

        existing_id = self._artifact_hash_index.get(artifact_hash)
        if existing_id is not None:
            raise ValidationError("artifact_hash is already registered",
                                  field="artifact_hash", value=artifact_hash,
                                  constraint=f"unique (owned by {existing_id})")
        if artifact_hash in canonical_parents:
            raise ValidationError("artifact cannot be its own parent",
                                  field="parent_hashes", value=parents,
                                  constraint="must not contain artifact_hash")
        if self._artifact_would_cycle(artifact_hash, canonical_parents):
            raise ValidationError("parent hashes would create an artifact cycle",
                                  field="parent_hashes", value=parents,
                                  constraint="acyclic content-addressed DAG")

        content = {
            "artifact_id": artifact_id,
            "artifact_hash": artifact_hash,
            "producer_agent_id": producer,
            "parent_hashes": canonical_parents,
            "relation": relation,
            "metadata_digest": metadata_digest,
            "registered_at": _utcnow(),
        }
        record = {**content, "record_hash": _cert_hash(content)}
        self._artifacts[artifact_id] = record
        self._artifact_order.append(artifact_id)
        self._artifact_hash_index[artifact_hash] = artifact_id
        return self._ok({**record, "created": True})

    def _get_artifact(self, data: dict) -> dict:
        artifact_id = data.get("artifact_id")
        record = self._artifacts.get(artifact_id)
        if record is None:  # A7
            raise ValidationError("unknown artifact", field="artifact_id",
                                  value=artifact_id, constraint="must exist")
        return self._ok(dict(record))

    def _verify_artifact(self, data: dict) -> dict:
        artifact = data.get("artifact")
        if not isinstance(artifact, dict) or "record_hash" not in artifact:
            raise ValidationError("artifact must be a dict with record_hash",
                                  field="artifact", value=artifact,
                                  constraint="registered artifact dict")
        content = {key: artifact.get(key) for key in _ARTIFACT_CONTENT_FIELDS}
        try:
            artifact_hash = _require_sha256(content["artifact_hash"],
                                               "artifact_hash")
            parents = content["parent_hashes"]
            parents_ok = (isinstance(parents, list)
                          and parents == sorted(set(parents)))
            if parents_ok:
                for parent in parents:
                    _require_sha256(parent, "parent_hashes")
            metadata = content["metadata_digest"]
            metadata_ok = metadata == ""
            if not metadata_ok:
                _require_sha256(metadata, "metadata_digest")
                metadata_ok = True
            dag_ok = bool(parents_ok and metadata_ok
                          and artifact_hash not in parents
                          and not self._artifact_would_cycle(artifact_hash,
                                                             parents))
        except ValidationError:
            dag_ok = False
        hash_ok = _cert_hash(content) == artifact.get("record_hash")
        registered = self._artifacts.get(content.get("artifact_id"))
        on_ledger = bool(registered
                         and registered["record_hash"] == artifact.get("record_hash"))
        return self._ok({"artifact_id": content.get("artifact_id"),
                         "valid": hash_ok and on_ledger and dag_ok,
                         "hash_ok": hash_ok, "on_ledger": on_ledger,
                         "dag_ok": dag_ok})

    def _list_artifacts(self, data: dict) -> dict:
        producer = data.get("producer_agent_id")
        if producer is not None and (not isinstance(producer, str)
                                     or not producer.strip()):
            raise ValidationError("producer_agent_id must be a non-empty string",
                                  field="producer_agent_id", value=producer,
                                  constraint="non-empty str or null")
        items = [dict(self._artifacts[artifact_id])
                 for artifact_id in self._artifact_order
                 if producer is None
                 or self._artifacts[artifact_id]["producer_agent_id"] == producer]
        return self._ok({"count": len(items), "artifacts": items,
                         "producer_agent_id": producer})

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"registered": len(self._records),
                       "recalled": sum(1 for r in self._records.values() if r.recalled),
                       "quarantined": sum(1 for r in self._records.values()
                                          if r.quarantined),
                       "artifacts": len(self._artifacts)}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Genesis certificates, lineage, and cascading recalls: "
                           "birth certificates + bloodlines for the agent economy.",
            "capabilities": ["register_genesis", "get_certificate",
                             "verify_certificate", "lineage", "recall", "list",
                             "register_artifact", "get_artifact",
                             "verify_artifact", "list_artifacts"],
            "inputs": {"action": "str", "agent_id": "str", "parent_id": "str|null",
                       "artifact_hash": "str", "certificate": "dict",
                       "reason": "str", "epoch": "int", "artifact_id": "str",
                       "producer_agent_id": "str", "parent_hashes": "list[str]",
                       "relation": "str", "metadata_digest": "sha256 hex|empty",
                       "artifact": "dict"},
            "outputs": {"status": "str (ok|error)", "data": "dict"},
            "a2a_role": "provenance",
        }


def build(config: Optional[AgentConfig] = None) -> ProvenanceAgentCore:
    return ProvenanceAgentCore(config)
