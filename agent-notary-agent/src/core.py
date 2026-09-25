"""
agent-notary-agent — Core business logic.

Verifiable delivery for the agent economy: commit-reveal content notarization
that turns escrow's `delivery_proof` from a caller-supplied string into a
cryptographically meaningful receipt. A seller COMMITS to the hash of its
deliverable before handover; after handover it REVEALS the content (or its
digest + salt); anyone can VERIFY that what was delivered is what was
promised. Composes directly with agent-escrow (release on verified reveal)
and agent-arbitration (a failed reveal is machine-checkable evidence).

Fleet-standard interface: async process(), async health(), sync describe().

--- INVARIANTS (spec-invariance contract) ---
N1  A commitment binds: commit_hash = SHA-256(salt || content_digest) is
    fixed at commit time and can never be altered.
N2  Reveal verifies iff SHA-256(salt || content_digest) equals the
    commitment — one bit of drift fails.
N3  Exactly-once reveal: a commitment is either PENDING, REVEALED, or
    EXPIRED; a second reveal returns the existing terminal record.
N4  A reveal after the commitment's deadline is refused (EXPIRED) — late
    delivery is machine-detectable.
N5  Notarized receipts are content-addressed and independently verifiable
    (verify recomputes everything from public fields + revealed salt).
N6  process() never raises on bad input — structured error envelope.
N7  The notary never stores raw content — only digests. Payload privacy by
    construction (callers pass SHA-256 digests, not documents).
N8  Commitment ids are unique and deterministic per (committer, nonce):
    the same (committer, nonce) can not create two different commitments.

--- ORC v0.1 registry (docs/standards/OUTCOME_RECEIPT_v0.1.md) ---
O1  seal_orc returns an Outcome Receipt that verifies at L1 with the fleet
    reference implementation (fleet_utils.orc); canonical form and hashes are
    byte-identical (pinned by a cross-implementation test).
O2  The registry stores only digest, commitment, issuer, profile, subject
    agent/tool and timestamps -- never the output (extends N7).
O3  get_commitment returns the registry record for a known commitment and a
    NotFound envelope otherwise; registered_at == the receipt's issued_at.
O4  Registration is idempotent per commitment; a commitment can never be
    re-bound to a different digest.
O5  attestation is "notarized" for caller-supplied outputs (the notary
    attests integrity + time, NOT correctness). "computed" is reachable only
    through seal_computed(), which is not in the dispatch table, so no
    external caller can claim Viridis computed their output.
O6  Floats are rejected and canonical output is capped at MAX_ORC_BYTES.
"""

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_HEX64 = set("0123456789abcdef")

ORC_VERSION = "0.1"
ORC_CANON = "orc-canon/1"
ORC_COMMIT_SCHEME = "sha256(salt||digest)"
MAX_ORC_BYTES = 262_144
DEFAULT_ISSUER = {"id": "did:web:viridisconservation.com", "name": "Viridis LLC"}


def _orc_canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def _orc_has_float(v: Any) -> bool:
    if isinstance(v, float):
        return True
    if isinstance(v, dict):
        return any(_orc_has_float(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return any(_orc_has_float(x) for x in v)
    return False


@dataclass
class AgentConfig:
    name: str
    version: str = "0.2.0"
    debug: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utcnow()).isoformat()


def _is_sha256_hex(s: Any) -> bool:
    return (isinstance(s, str) and len(s) == 64
            and all(c in _HEX64 for c in s.lower()))


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
class Commitment:
    commitment_id: str
    committer: str
    nonce: str
    commit_hash: str              # SHA-256(salt || content_digest)
    context: str                  # e.g. escrow id / job reference
    deadline: str                 # ISO-8601
    state: str = "PENDING"        # PENDING -> REVEALED | EXPIRED
    committed_at: str = ""
    revealed_at: str = ""
    content_digest: str = ""      # set on reveal
    salt: str = ""                # set on reveal

    def public(self) -> dict:
        return {"commitment_id": self.commitment_id, "committer": self.committer,
                "commit_hash": self.commit_hash, "context": self.context,
                "deadline": self.deadline, "state": self.state,
                "committed_at": self.committed_at,
                "revealed_at": self.revealed_at,
                "content_digest": self.content_digest if self.state == "REVEALED" else "",
                "salt": self.salt if self.state == "REVEALED" else ""}


class NotaryAgentCore(AgentCore):
    """Commit-reveal notarization for verifiable A2A delivery."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-notary-agent"))
        self._commitments: Dict[str, Commitment] = {}
        self._by_key: Dict[str, str] = {}   # (committer,nonce) -> commitment_id
        self._orc_registry: Dict[str, dict] = {}   # commitment -> record (O2)
        self.orc_registry_base: str = ""   # set by the hosting gateway

    @staticmethod
    def _commit_hash(salt: str, content_digest: str) -> str:          # N1/N2
        return hashlib.sha256((salt + content_digest).encode()).hexdigest()

    async def health(self) -> dict:
        h = await super().health()
        states = [c.state for c in self._commitments.values()]
        h["checks"] = {"commitments": len(states),
                       "pending": states.count("PENDING"),
                       "revealed": states.count("REVEALED"),
                       "orc_registered": len(self._orc_registry)}
        return h

    def describe(self) -> dict:
        return {"name": self.config.name, "version": self.config.version,
                "capabilities": ["commit", "reveal", "verify", "status", "list",
                                 "seal_orc", "get_commitment"],
                "inputs": {"action": "one of capabilities", "...": "per action"},
                "outputs": {"status": "ok|error", "data": "per action"},
                "a2a_role": "notary"}

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object",
                                 error_type="ValidationError", field="input",
                                 value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {"commit": self._commit, "reveal": self._reveal,
                       "verify": self._verify, "status": self._status,
                       "list": self._list, "seal_orc": self._seal_orc,
                       "get_commitment": self._get_commitment}.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'",
                                 error_type="ValidationError", field="action",
                                 value=action,
                                 constraint="one of: commit, reveal, verify, "
                                            "status, list, seal_orc, "
                                            "get_commitment")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError",
                             field=e.field, value=e.value, constraint=e.constraint)
        except Exception as e:                                        # N6
            self.logger.exception("notary process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # -- operations ----------------------------------------------------------
    def _commit(self, d: dict) -> dict:
        committer = d.get("committer")
        nonce = d.get("nonce")
        commit_hash = str(d.get("commit_hash", "")).lower()
        if not committer or not nonce:
            raise ValidationError("'committer' and 'nonce' are required",
                                  field="committer,nonce", value=None,
                                  constraint="non-empty")
        if not _is_sha256_hex(commit_hash):
            raise ValidationError("'commit_hash' must be 64 hex chars "
                                  "(SHA-256 of salt||content_digest) — the "
                                  "notary never sees raw content",
                                  field="commit_hash", value=d.get("commit_hash"),
                                  constraint="sha256 hex")
        deadline = d.get("deadline")
        try:
            datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise ValidationError("'deadline' must be ISO-8601",
                                  field="deadline", value=deadline,
                                  constraint="ISO-8601")
        key = f"{committer}:{nonce}"
        if key in self._by_key:                                       # N8
            existing = self._commitments[self._by_key[key]]
            if existing.commit_hash == commit_hash:
                return self._ok({**existing.public(), "idempotent": True})
            raise ValidationError(
                f"(committer, nonce) already bound to a DIFFERENT commitment "
                f"({existing.commitment_id}) — a commitment binds (N1)",
                field="nonce", value=nonce, constraint="unique per commitment")
        cid = "ncm_" + hashlib.sha256(key.encode()).hexdigest()[:16]  # N8
        c = Commitment(commitment_id=cid, committer=str(committer),
                       nonce=str(nonce), commit_hash=commit_hash,
                       context=str(d.get("context", "")),
                       deadline=str(deadline), committed_at=_iso())
        self._commitments[cid] = c
        self._by_key[key] = cid
        return self._ok({**c.public(), "idempotent": False})

    def _get(self, d: dict) -> Commitment:
        cid = d.get("commitment_id")
        c = self._commitments.get(cid or "")
        if c is None:
            raise ValidationError(f"unknown commitment_id '{cid}'",
                                  field="commitment_id", value=cid,
                                  constraint="an existing commitment")
        return c

    def _reveal(self, d: dict) -> dict:
        c = self._get(d)
        if c.state != "PENDING":                                      # N3
            return self._ok({**c.public(), "idempotent": True})
        now = d.get("_now")   # test hook
        now_dt = datetime.fromisoformat(now) if now else _utcnow()
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        dl = datetime.fromisoformat(c.deadline.replace("Z", "+00:00"))
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        if now_dt > dl:                                               # N4
            c.state = "EXPIRED"
            return self._err("reveal after deadline — commitment EXPIRED "
                             "(late delivery is machine-detectable)",
                             error_type="Expired", field="deadline",
                             value=c.deadline, constraint="reveal <= deadline")
        salt = str(d.get("salt", ""))
        content_digest = str(d.get("content_digest", "")).lower()
        if not salt or not _is_sha256_hex(content_digest):            # N7
            raise ValidationError("'salt' and 'content_digest' (sha256 hex) "
                                  "are required", field="salt,content_digest",
                                  value=None, constraint="non-empty, sha256 hex")
        if self._commit_hash(salt, content_digest) != c.commit_hash:  # N2
            return self._err("reveal does not match commitment — content "
                             "differs from what was promised",
                             error_type="CommitmentMismatch",
                             field="commit_hash", value=c.commit_hash,
                             constraint="sha256(salt||content_digest)")
        c.state = "REVEALED"
        c.revealed_at = _iso()
        c.salt = salt
        c.content_digest = content_digest
        return self._ok({**c.public(),
                         "delivery_proof": f"notary:{c.commitment_id}:"
                                           f"{c.content_digest}"})

    def _verify(self, d: dict) -> dict:                               # N5
        c = self._get(d)
        if c.state != "REVEALED":
            return self._ok({"valid": False, "state": c.state,
                             "reason": "not revealed"})
        recomputed = self._commit_hash(c.salt, c.content_digest)
        expected_digest = d.get("content_digest")
        digest_matches = (str(expected_digest).lower() == c.content_digest
                          if expected_digest else True)
        return self._ok({"valid": recomputed == c.commit_hash and digest_matches,
                         "commit_hash": c.commit_hash,
                         "recomputed": recomputed,
                         "digest_checked": bool(expected_digest)})

    def _status(self, d: dict) -> dict:
        return self._ok(self._get(d).public())

    def _list(self, d: dict) -> dict:
        state = d.get("state")
        items = [c.public() for c in self._commitments.values()
                 if state is None or c.state == state]
        return self._ok({"count": len(items), "commitments": items})


    # -- ORC v0.1 ------------------------------------------------------------
    def _orc_seal(self, d: dict, attestation: str) -> dict:
        output = d.get("output")
        if not isinstance(output, dict):
            raise ValidationError("'output' must be a JSON object",
                                  field="output", value=type(output).__name__,
                                  constraint="object")
        if _orc_has_float(output):                                    # O6
            raise ValidationError("floats are not allowed in 'output'; use "
                                  "integers or decimal strings",
                                  field="output", value=None,
                                  constraint="no floats (ORC R6)")
        subject = d.get("subject")
        subject = {} if subject is None else subject
        if not isinstance(subject, dict):
            raise ValidationError("'subject' must be an object", field="subject",
                                  value=type(subject).__name__, constraint="object")
        excludes = d.get("excludes")
        excludes = [] if excludes is None else excludes
        if (not isinstance(excludes, list)
                or not all(isinstance(x, str) for x in excludes)):
            raise ValidationError("'excludes' must be a list of strings",
                                  field="excludes", value=excludes,
                                  constraint="list[str]")
        bindings = d.get("bindings")
        bindings = {} if bindings is None else bindings
        if not isinstance(bindings, dict):
            raise ValidationError("'bindings' must be an object", field="bindings",
                                  value=type(bindings).__name__, constraint="object")
        profile = str(d.get("profile") or "generic")
        content = {k: v for k, v in output.items() if k not in set(excludes)}
        canon = _orc_canonical(content)
        if len(canon) > MAX_ORC_BYTES:                                # O6
            raise ValidationError("output too large to seal", field="output",
                                  value=len(canon),
                                  constraint=f"<= {MAX_ORC_BYTES} canonical bytes")
        digest = hashlib.sha256(canon.encode()).hexdigest()
        salt = str(d.get("_salt") or secrets.token_hex(32))
        if not _is_sha256_hex(salt):
            raise ValidationError("salt must be 64 hex chars", field="salt",
                                  value=None, constraint="sha256 hex")
        salt = salt.lower()
        commitment = self._commit_hash(salt, digest)
        existing = self._orc_registry.get(commitment)
        if existing is not None and existing["digest"] != digest:     # O4
            raise ValidationError("commitment already bound to a different digest",
                                  field="commitment", value=commitment,
                                  constraint="one digest per commitment")
        issuer = dict(DEFAULT_ISSUER)
        now = existing["registered_at"] if existing else _iso()
        record = existing or {
            "commitment": commitment, "digest": digest, "issuer": issuer,
            "profile": profile, "attestation": attestation,           # O5
            "subject": {"agent": str(subject.get("agent", "")),
                        "tool": str(subject.get("tool", ""))},
            "registered_at": now}                                     # O2
        self._orc_registry[commitment] = record
        receipt = {
            "orc": ORC_VERSION, "profile": profile, "issuer": issuer,
            "subject": json.loads(json.dumps(subject)),
            "output": json.loads(json.dumps(output)),
            "digest": {"alg": "sha256", "canonicalization": ORC_CANON,
                       "excludes": list(excludes), "value": digest},
            "commitment": {"scheme": ORC_COMMIT_SCHEME, "salt": salt,
                           "value": commitment},
            "bindings": json.loads(json.dumps(bindings)),
            "issued_at": now,                                         # O3
        }
        if self.orc_registry_base:
            receipt["issuer_proof"] = {
                "method": "registry",
                "url": self.orc_registry_base.rstrip("/") + "/" + commitment}
        return self._ok({"receipt": receipt, "registered": dict(record),
                         "idempotent": existing is not None})

    def _seal_orc(self, d: dict) -> dict:
        return self._orc_seal(d, "notarized")

    async def seal_computed(self, d: dict) -> dict:
        """Gateway-internal only (O5): for outputs a Viridis engine computed.
        Deliberately absent from the process() dispatch table."""
        try:
            return self._orc_seal(d, "computed")
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError",
                             field=e.field, value=e.value, constraint=e.constraint)

    def _get_commitment(self, d: dict) -> dict:
        c = str(d.get("commitment", "")).lower()
        if not _is_sha256_hex(c):
            raise ValidationError("'commitment' must be 64 hex chars",
                                  field="commitment", value=d.get("commitment"),
                                  constraint="sha256 hex")
        rec = self._orc_registry.get(c)
        if rec is None:                                               # O3
            return self._err("unknown commitment", error_type="NotFound",
                             field="commitment", value=c,
                             constraint="a commitment sealed by this notary")
        return self._ok(dict(rec))


def build(config: Optional[AgentConfig] = None) -> NotaryAgentCore:
    return NotaryAgentCore(config)
