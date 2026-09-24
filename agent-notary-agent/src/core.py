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
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_HEX64 = set("0123456789abcdef")


@dataclass
class AgentConfig:
    name: str
    version: str = "0.1.0"
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

    @staticmethod
    def _commit_hash(salt: str, content_digest: str) -> str:          # N1/N2
        return hashlib.sha256((salt + content_digest).encode()).hexdigest()

    async def health(self) -> dict:
        h = await super().health()
        states = [c.state for c in self._commitments.values()]
        h["checks"] = {"commitments": len(states),
                       "pending": states.count("PENDING"),
                       "revealed": states.count("REVEALED")}
        return h

    def describe(self) -> dict:
        return {"name": self.config.name, "version": self.config.version,
                "capabilities": ["commit", "reveal", "verify", "status", "list"],
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
                       "list": self._list}.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'",
                                 error_type="ValidationError", field="action",
                                 value=action,
                                 constraint="one of: commit, reveal, verify, "
                                            "status, list")
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


def build(config: Optional[AgentConfig] = None) -> NotaryAgentCore:
    return NotaryAgentCore(config)
