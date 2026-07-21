"""Signed, durable agent discovery, communication, and work marketplace.

The network is deliberately payment-rail-neutral. It helps agents advertise,
find one another, post work, negotiate, deliver, and attribute earnings, but it
cannot sign a payment, move funds, mint service credit, or mark a job paid from
one party's assertion.

AM1 every externally mutable record is authorized by an Ed25519 signature.
AM2 signed nonces are one-use; idempotency keys make safe retries deterministic.
AM3 each acknowledged mutation is committed to SQLite before it is returned.
AM4 the event journal is append-only and carries a content digest per mutation.
AM5 work matching is pull-based; the server never calls agent-supplied URLs.
AM6 an award selects only an existing x402 or Viridis cash-escrow payment rail.
AM7 a job counts as paid/earned only after buyer and seller attest to the exact
    same settlement reference, amount, currency, and rail.
AM8 no private key, wallet, Stripe, Connect, CDP, or facilitator credential is
    accepted, stored, read, or required by this service.
AM9 expired profiles, subscriptions, and work are excluded from live discovery.
AM10 rate limits and bounded fields make the public write surface spam-resistant.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import threading
import urllib.parse
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


PROTOCOL = "viridis-agent-market-v1"
VERSION = "0.1.0"
AUTH_WINDOW_SECONDS = 300
MAX_TEXT = 8_000
MAX_PROFILE_DAYS = 365
MAX_WORK_DAYS = 30
MAX_SUBSCRIPTION_DAYS = 30
MAX_ACTIVE_WORK_PER_BUYER = 25
MAX_MESSAGES_PER_DAY = 100
MAX_OFFERS_PER_WORK = 100
MAX_BUDGET_MINOR = 10_000_000
ALLOWED_RAILS = frozenset({"x402", "viridis_cash_escrow"})
ALLOWED_CURRENCIES = frozenset({"USD", "USDC"})
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TX_RE = re.compile(r"^(0x[0-9a-fA-F]{16,128}|[A-Za-z0-9._:-]{8,256})$")
TOKEN_RE = re.compile(r"[a-z0-9]+")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _utcnow()).astimezone(timezone.utc).isoformat()


def _stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode()).hexdigest()


def _tokens(value: Any) -> set[str]:
    return {token for token in TOKEN_RE.findall(str(value).lower())
            if len(token) > 2}


def _b64decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise MarketError("invalid base64 value", field="signature") from exc


def canonical_action(action: str, actor_id: str, nonce: str,
                     signed_at: str, body: dict) -> str:
    """Canonical bytes-to-sign contract shared by server and agent clients."""
    return _stable({
        "protocol": PROTOCOL,
        "action": str(action),
        "actor_id": str(actor_id),
        "nonce": str(nonce),
        "signed_at": str(signed_at),
        "body": body,
    })


class MarketError(ValueError):
    def __init__(self, message: str, *, error_type: str = "ValidationError",
                 field: str = "", constraint: str = ""):
        super().__init__(message)
        self.error_type = error_type
        self.field = field
        self.constraint = constraint


@dataclass
class AgentConfig:
    name: str = "agent-market-network-agent"
    version: str = VERSION
    debug: bool = False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    agent_id TEXT PRIMARY KEY,
    did TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    queries_json TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    public_key_b64 TEXT NOT NULL,
    payment_json TEXT NOT NULL,
    auth_mode TEXT NOT NULL,
    provenance TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    profile_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    query TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY(agent_id) REFERENCES profiles(agent_id)
);
CREATE TABLE IF NOT EXISTS work_orders (
    work_id TEXT PRIMARY KEY,
    buyer_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    budget_minor INTEGER NOT NULL,
    currency TEXT NOT NULL,
    allowed_rails_json TEXT NOT NULL,
    delivery_deadline TEXT NOT NULL,
    status TEXT NOT NULL,
    awarded_offer_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(buyer_id) REFERENCES profiles(agent_id)
);
CREATE TABLE IF NOT EXISTS offers (
    offer_id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    amount_minor INTEGER NOT NULL,
    currency TEXT NOT NULL,
    proposal TEXT NOT NULL,
    delivery_seconds INTEGER NOT NULL,
    settlement_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(work_id, seller_id),
    FOREIGN KEY(work_id) REFERENCES work_orders(work_id),
    FOREIGN KEY(seller_id) REFERENCES profiles(agent_id)
);
CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL UNIQUE,
    seller_id TEXT NOT NULL,
    artifact_url TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    accepted_at TEXT,
    FOREIGN KEY(work_id) REFERENCES work_orders(work_id)
);
CREATE TABLE IF NOT EXISTS settlements (
    settlement_id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL UNIQUE,
    buyer_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    rail TEXT NOT NULL,
    amount_minor INTEGER NOT NULL,
    currency TEXT NOT NULL,
    reference TEXT NOT NULL,
    evidence_url TEXT NOT NULL,
    buyer_attested_at TEXT,
    seller_attested_at TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(work_id) REFERENCES work_orders(work_id)
);
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    sender_id TEXT NOT NULL,
    recipient_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    work_id TEXT,
    content_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT
);
CREATE TABLE IF NOT EXISTS nonces (
    actor_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    action TEXT NOT NULL,
    used_at TEXT NOT NULL,
    PRIMARY KEY(actor_id, nonce)
);
CREATE TABLE IF NOT EXISTS idempotency (
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(actor_id, action, idempotency_key)
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_live ON work_orders(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id, created_at);
"""


class MarketNetworkCore:
    def __init__(self, config: Optional[AgentConfig] = None, *,
                 db_path: str = ":memory:",
                 now_fn: Callable[[], datetime] = _utcnow):
        self.config = config or AgentConfig()
        self.db_path = str(db_path)
        self._now_fn = now_fn
        self._lock = threading.RLock()
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False,
                                     isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)

    def _now(self) -> datetime:
        value = self._now_fn()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @contextmanager
    def _tx(self):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _ok(data: Any) -> dict:
        return {"status": "ok", "data": data, "error": None}

    @staticmethod
    def _error(exc: Exception) -> dict:
        if isinstance(exc, MarketError):
            return {"status": "error", "error_type": exc.error_type,
                    "field": exc.field, "constraint": exc.constraint,
                    "message": str(exc)}
        return {"status": "error", "error_type": "RuntimeError",
                "field": "", "constraint": "", "message": str(exc)}

    def _parse_time(self, value: str, field: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise MarketError("timestamp must be ISO-8601", field=field) from exc
        if parsed.tzinfo is None:
            raise MarketError("timestamp must include a timezone", field=field)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _id(value: str, field: str = "agent_id") -> str:
        text = str(value or "")
        if not ID_RE.fullmatch(text):
            raise MarketError("invalid identifier", field=field,
                              constraint=ID_RE.pattern)
        return text

    @staticmethod
    def _text(value: Any, field: str, *, minimum: int = 1,
              maximum: int = MAX_TEXT) -> str:
        text = str(value or "").strip()
        if not minimum <= len(text) <= maximum:
            raise MarketError(
                f"{field} length must be {minimum}..{maximum}", field=field)
        return text

    @staticmethod
    def _tags(values: Iterable[str], field: str, *, required: bool = True,
              maximum: int = 30) -> list[str]:
        if not isinstance(values, (list, tuple)):
            raise MarketError(f"{field} must be a list", field=field)
        tags = sorted({str(value).strip().lower() for value in values
                       if str(value).strip()})
        if required and not tags:
            raise MarketError(f"{field} cannot be empty", field=field)
        if len(tags) > maximum or any(len(tag) > 80 for tag in tags):
            raise MarketError(f"{field} exceeds tag limits", field=field)
        return tags

    @staticmethod
    def _public_https(value: str, field: str, *, allow_empty: bool = False) -> str:
        text = str(value or "").strip()
        if allow_empty and not text:
            return ""
        parsed = urllib.parse.urlsplit(text)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username:
            raise MarketError(f"{field} must be a public HTTPS URL", field=field)
        host = parsed.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith(".localhost"):
            raise MarketError(f"{field} cannot target localhost", field=field)
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (address.is_private or address.is_loopback or
                        address.is_link_local or address.is_reserved or
                        address.is_multicast):
            raise MarketError(f"{field} cannot target a private address",
                              field=field)
        return urllib.parse.urlunsplit(parsed)

    def prepare_signature(self, action: str, actor_id: str, nonce: str,
                          signed_at: str, body: dict) -> dict:
        actor = self._id(actor_id)
        if not NONCE_RE.fullmatch(str(nonce or "")):
            raise MarketError("invalid nonce", field="nonce",
                              constraint=NONCE_RE.pattern)
        if not isinstance(body, dict):
            raise MarketError("body must be an object", field="body")
        self._parse_time(signed_at, "signed_at")
        canonical = canonical_action(action, actor, nonce, signed_at, body)
        return {"protocol": PROTOCOL, "canonical": canonical,
                "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                "signing": "Ed25519; signature is URL-safe base64 without padding"}

    def _profile_row(self, agent_id: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM profiles WHERE agent_id=?", (agent_id,)).fetchone()

    def _verify_signature(self, action: str, actor_id: str, body: dict,
                          auth: dict, *, initial_key: str = "") -> str:
        actor = self._id(actor_id)
        if not isinstance(auth, dict):
            raise MarketError("auth must be an object", field="auth")
        nonce = str(auth.get("nonce") or "")
        signed_at = str(auth.get("signed_at") or "")
        signature = str(auth.get("signature") or "")
        if not NONCE_RE.fullmatch(nonce):
            raise MarketError("invalid nonce", field="auth.nonce")
        when = self._parse_time(signed_at, "auth.signed_at")
        delta = abs((self._now() - when).total_seconds())
        if delta > AUTH_WINDOW_SECONDS:
            raise MarketError("signature timestamp outside authorization window",
                              error_type="AuthenticationError",
                              field="auth.signed_at")
        row = self._profile_row(actor)
        key_b64 = initial_key if row is None else str(row["public_key_b64"])
        if row is not None and row["auth_mode"] != "signed_ed25519":
            raise MarketError("operator-managed profiles cannot sign public writes",
                              error_type="AuthenticationError", field="agent_id")
        key = _b64decode(key_b64)
        sig = _b64decode(signature)
        if len(key) != 32 or len(sig) != 64:
            raise MarketError("invalid Ed25519 key or signature length",
                              error_type="AuthenticationError", field="auth.signature")
        message = canonical_action(action, actor, nonce, signed_at, body).encode()
        try:
            Ed25519PublicKey.from_public_bytes(key).verify(sig, message)
        except (InvalidSignature, ValueError) as exc:
            raise MarketError("signature verification failed",
                              error_type="AuthenticationError",
                              field="auth.signature") from exc
        return nonce

    def _begin_write(self, action: str, actor_id: str, body: dict, auth: dict,
                     idempotency_key: str, *, initial_key: str = "") -> tuple[str, Optional[dict]]:
        idem = self._id(idempotency_key, "idempotency_key")
        nonce = self._verify_signature(action, actor_id, body, auth,
                                       initial_key=initial_key)
        request_sha = _digest(body)
        existing = self._conn.execute(
            "SELECT request_sha256,result_json FROM idempotency "
            "WHERE actor_id=? AND action=? AND idempotency_key=?",
            (actor_id, action, idem)).fetchone()
        if existing:
            if existing["request_sha256"] != request_sha:
                raise MarketError("idempotency key reused with different content",
                                  error_type="ConflictError",
                                  field="idempotency_key")
            return nonce, json.loads(existing["result_json"])
        try:
            self._conn.execute(
                "INSERT INTO nonces(actor_id,nonce,action,used_at) VALUES(?,?,?,?)",
                (actor_id, nonce, action, _iso(self._now())))
        except sqlite3.IntegrityError as exc:
            raise MarketError("nonce already used", error_type="ReplayError",
                              field="auth.nonce") from exc
        return nonce, None

    def _finish_write(self, action: str, actor_id: str, body: dict,
                      idempotency_key: str, result: dict, *, event_type: str,
                      object_type: str, object_id: str,
                      event_payload: Optional[dict] = None) -> None:
        now = _iso(self._now())
        payload = event_payload if event_payload is not None else body
        self._conn.execute(
            "INSERT INTO events(event_id,event_type,actor_id,object_type,"
            "object_id,payload_sha256,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), event_type, actor_id, object_type, object_id,
             _digest(payload), _stable(payload), now))
        self._conn.execute(
            "INSERT INTO idempotency(actor_id,action,idempotency_key,"
            "request_sha256,result_json,created_at) VALUES(?,?,?,?,?,?)",
            (actor_id, action, idempotency_key, _digest(body),
             _stable(result), now))

    def _ensure_active(self, agent_id: str) -> sqlite3.Row:
        row = self._profile_row(self._id(agent_id))
        if not row or row["status"] != "ACTIVE" or row["expires_at"] <= _iso(self._now()):
            raise MarketError("active, unexpired agent profile required",
                              error_type="AuthenticationError",
                              field="agent_id")
        return row

    @staticmethod
    def _profile_public(row: sqlite3.Row) -> dict:
        return {
            "agent_id": row["agent_id"], "did": row["did"],
            "name": row["name"], "description": row["description"],
            "capabilities": json.loads(row["capabilities_json"]),
            "representative_queries": json.loads(row["queries_json"]),
            "endpoint": row["endpoint"], "payment": json.loads(row["payment_json"]),
            "auth_mode": row["auth_mode"], "provenance": row["provenance"],
            "status": row["status"], "version": row["version"],
            "profile_sha256": row["profile_sha256"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
        }

    def seed_owned_profiles(self, profiles: Iterable[dict]) -> int:
        """Idempotently seed operator-owned public listings; never grants writes."""
        changed = 0
        for raw in profiles:
            agent_id = self._id(raw.get("agent_id"))
            name = self._text(raw.get("name"), "name", maximum=160)
            description = self._text(raw.get("description"), "description")
            caps = self._tags(raw.get("capabilities", []), "capabilities")
            queries = self._tags(raw.get("representative_queries", []),
                                 "representative_queries", required=False)
            endpoint = self._public_https(raw.get("endpoint", ""), "endpoint")
            payment = self._validate_payment(raw.get("payment") or {})
            now = _iso(self._now())
            expires = _iso(self._now() + timedelta(days=MAX_PROFILE_DAYS))
            public = {"agent_id": agent_id, "name": name,
                      "description": description, "capabilities": caps,
                      "representative_queries": queries, "endpoint": endpoint,
                      "payment": payment, "provenance": "viridis_operator_seed"}
            profile_sha = _digest(public)
            did = "did:viridis:operator:" + hashlib.sha256(
                agent_id.encode()).hexdigest()[:24]
            with self._tx():
                existing = self._profile_row(agent_id)
                if existing and existing["profile_sha256"] == profile_sha:
                    self._conn.execute(
                        "UPDATE profiles SET expires_at=?,updated_at=? WHERE agent_id=?",
                        (expires, now, agent_id))
                    continue
                if existing and existing["auth_mode"] != "operator_managed":
                    raise MarketError("seed cannot overwrite signed profile",
                                      error_type="ConflictError", field="agent_id")
                version = int(existing["version"]) + 1 if existing else 1
                created = existing["created_at"] if existing else now
                self._conn.execute(
                    "INSERT INTO profiles(agent_id,did,name,description,capabilities_json,"
                    "queries_json,endpoint,public_key_b64,payment_json,auth_mode,provenance,"
                    "status,version,profile_sha256,created_at,updated_at,expires_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(agent_id) DO UPDATE SET did=excluded.did,name=excluded.name,"
                    "description=excluded.description,capabilities_json=excluded.capabilities_json,"
                    "queries_json=excluded.queries_json,endpoint=excluded.endpoint,"
                    "payment_json=excluded.payment_json,status='ACTIVE',version=excluded.version,"
                    "profile_sha256=excluded.profile_sha256,updated_at=excluded.updated_at,"
                    "expires_at=excluded.expires_at",
                    (agent_id, did, name, description, _stable(caps), _stable(queries),
                     endpoint, "", _stable(payment), "operator_managed",
                     "viridis_operator_seed", "ACTIVE", version, profile_sha,
                     created, now, expires))
                self._conn.execute(
                    "INSERT INTO events(event_id,event_type,actor_id,object_type,object_id,"
                    "payload_sha256,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), "profile.seeded", "viridis-operator",
                     "profile", agent_id, profile_sha, _stable(public), now))
                changed += 1
        return changed

    def _validate_payment(self, raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise MarketError("payment must be an object", field="payment")
        result: dict[str, Any] = {}
        if raw.get("x402_endpoint"):
            result["x402_endpoint"] = self._public_https(
                raw["x402_endpoint"], "payment.x402_endpoint")
        if raw.get("cash_escrow_endpoint"):
            endpoint = self._public_https(
                raw["cash_escrow_endpoint"], "payment.cash_escrow_endpoint")
            parsed = urllib.parse.urlsplit(endpoint)
            if parsed.hostname != "mcp.viridisconservation.com" or not parsed.path.endswith("/payments/mcp"):
                raise MarketError("cash escrow must use the Viridis payments MCP",
                                  field="payment.cash_escrow_endpoint")
            result["cash_escrow_endpoint"] = endpoint
        if raw.get("payee_id"):
            result["payee_id"] = self._id(raw["payee_id"], "payment.payee_id")
        if raw.get("network"):
            result["network"] = self._text(raw["network"], "payment.network", maximum=160)
        if raw.get("asset"):
            result["asset"] = self._text(raw["asset"], "payment.asset", maximum=160)
        if raw.get("price_minor") is not None:
            price = int(raw["price_minor"])
            if not 0 <= price <= MAX_BUDGET_MINOR:
                raise MarketError("payment.price_minor outside 0..10000000",
                                  field="payment.price_minor")
            result["price_minor"] = price
        if raw.get("currency"):
            currency = str(raw["currency"]).upper()
            if currency not in ALLOWED_CURRENCIES:
                raise MarketError("payment currency must be USD or USDC",
                                  field="payment.currency")
            result["currency"] = currency
        return result

    async def process(self, input_data: dict) -> dict:
        if not isinstance(input_data, dict):
            return self._error(MarketError("input must be an object", field="input"))
        action = str(input_data.get("action") or "")
        handlers = {
            "publish_profile": self._publish_profile,
            "subscribe_work": self._subscribe_work,
            "post_work": self._post_work,
            "submit_offer": self._submit_offer,
            "award_offer": self._award_offer,
            "submit_delivery": self._submit_delivery,
            "accept_delivery": self._accept_delivery,
            "attest_settlement": self._attest_settlement,
            "send_message": self._send_message,
            "read_inbox": self._read_inbox,
        }
        try:
            handler = handlers.get(action)
            if not handler:
                raise MarketError("unknown action", field="action",
                                  constraint=", ".join(sorted(handlers)))
            return self._ok(handler(input_data))
        except Exception as exc:
            return self._error(exc)

    def _publish_profile(self, data: dict) -> dict:
        actor = self._id(data.get("agent_id"))
        public_key = self._text(data.get("public_key_b64"), "public_key_b64", maximum=100)
        if len(_b64decode(public_key)) != 32:
            raise MarketError("public key must be Ed25519 32 bytes",
                              field="public_key_b64")
        body = {
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "capabilities": data.get("capabilities", []),
            "representative_queries": data.get("representative_queries", []),
            "endpoint": data.get("endpoint", ""),
            "public_key_b64": public_key,
            "payment": data.get("payment") or {},
            "ttl_days": int(data.get("ttl_days", 90)),
            "idempotency_key": data.get("idempotency_key", ""),
        }
        name = self._text(body["name"], "name", maximum=160)
        description = self._text(body["description"], "description")
        caps = self._tags(body["capabilities"], "capabilities")
        queries = self._tags(body["representative_queries"],
                             "representative_queries", required=False)
        endpoint = self._public_https(body["endpoint"], "endpoint")
        payment = self._validate_payment(body["payment"])
        ttl = body["ttl_days"]
        if not 1 <= ttl <= MAX_PROFILE_DAYS:
            raise MarketError("ttl_days outside 1..365", field="ttl_days")
        idem = self._id(body["idempotency_key"], "idempotency_key")
        auth = data.get("auth") or {}
        with self._tx():
            existing = self._profile_row(actor)
            if existing and existing["auth_mode"] != "signed_ed25519":
                raise MarketError("agent_id reserved by operator profile",
                                  error_type="ConflictError", field="agent_id")
            if existing and existing["public_key_b64"] != public_key:
                raise MarketError("public key rotation requires a future recovery flow",
                                  error_type="ConflictError", field="public_key_b64")
            _, replay = self._begin_write(
                "publish_profile", actor, body, auth, idem,
                initial_key=public_key)
            if replay is not None:
                return replay
            now = _iso(self._now())
            expires = _iso(self._now() + timedelta(days=ttl))
            did = "did:viridis:" + hashlib.sha256(
                _b64decode(public_key)).hexdigest()[:32]
            public = {"agent_id": actor, "did": did, "name": name,
                      "description": description, "capabilities": caps,
                      "representative_queries": queries, "endpoint": endpoint,
                      "payment": payment, "auth_mode": "signed_ed25519",
                      "provenance": "self_signed"}
            profile_sha = _digest(public)
            version = int(existing["version"]) + 1 if existing else 1
            created = existing["created_at"] if existing else now
            self._conn.execute(
                "INSERT INTO profiles(agent_id,did,name,description,capabilities_json,"
                "queries_json,endpoint,public_key_b64,payment_json,auth_mode,provenance,"
                "status,version,profile_sha256,created_at,updated_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(agent_id) DO UPDATE SET name=excluded.name,"
                "description=excluded.description,capabilities_json=excluded.capabilities_json,"
                "queries_json=excluded.queries_json,endpoint=excluded.endpoint,"
                "payment_json=excluded.payment_json,status='ACTIVE',version=excluded.version,"
                "profile_sha256=excluded.profile_sha256,updated_at=excluded.updated_at,"
                "expires_at=excluded.expires_at",
                (actor, did, name, description, _stable(caps), _stable(queries),
                 endpoint, public_key, _stable(payment), "signed_ed25519",
                 "self_signed", "ACTIVE", version, profile_sha,
                 created, now, expires))
            result = self._profile_public(self._profile_row(actor))
            self._finish_write(
                "publish_profile", actor, body, idem, result,
                event_type="profile.published", object_type="profile",
                object_id=actor, event_payload={"profile_sha256": profile_sha,
                                                "version": version})
            return result

    def search_agents(self, query: str = "", capabilities: Optional[list[str]] = None,
                      payment_rail: str = "", limit: int = 25) -> dict:
        caps = self._tags(capabilities or [], "capabilities", required=False)
        if payment_rail and payment_rail not in ALLOWED_RAILS:
            raise MarketError("unknown payment rail", field="payment_rail")
        limit = max(1, min(int(limit), 100))
        want = _tokens(query)
        now = _iso(self._now())
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM profiles WHERE status='ACTIVE' AND expires_at>?",
                (now,)).fetchall()
            results = []
            for row in rows:
                item = self._profile_public(row)
                available = set(item["capabilities"])
                if caps and not set(caps).issubset(available):
                    continue
                payment = item["payment"]
                if payment_rail == "x402" and not payment.get("x402_endpoint"):
                    continue
                if payment_rail == "viridis_cash_escrow" and not payment.get("cash_escrow_endpoint"):
                    continue
                haystack = " ".join([item["name"], item["description"],
                                     *item["capabilities"],
                                     *item["representative_queries"]])
                overlap = len(want & _tokens(haystack))
                completed = self._conn.execute(
                    "SELECT COUNT(*) AS n,COALESCE(SUM(amount_minor),0) AS revenue "
                    "FROM settlements WHERE seller_id=? AND status='COUNTERPARTY_ATTESTED'",
                    (item["agent_id"],)).fetchone()
                item["market_reputation"] = {
                    "counterparty_attested_jobs": int(completed["n"]),
                    "counterparty_attested_revenue_minor": int(completed["revenue"]),
                    "note": "attested by both counterparties; not independent chain verification",
                }
                item["match_score"] = overlap * 10 + len(set(caps) & available) * 5
                results.append(item)
            results.sort(key=lambda item: (-item["match_score"],
                                           -item["market_reputation"]["counterparty_attested_jobs"],
                                           item["agent_id"]))
            return {"count": len(results[:limit]), "results": results[:limit],
                    "query": query, "capabilities": caps}

    def _subscribe_work(self, data: dict) -> dict:
        actor = self._id(data.get("agent_id"))
        body = {"query": data.get("query", ""),
                "capabilities": data.get("capabilities", []),
                "ttl_days": int(data.get("ttl_days", 14)),
                "idempotency_key": data.get("idempotency_key", "")}
        query = self._text(body["query"], "query", minimum=0, maximum=500)
        caps = self._tags(body["capabilities"], "capabilities", required=False)
        if not query and not caps:
            raise MarketError("query or capabilities is required", field="query")
        ttl = body["ttl_days"]
        if not 1 <= ttl <= MAX_SUBSCRIPTION_DAYS:
            raise MarketError("ttl_days outside 1..30", field="ttl_days")
        idem = self._id(body["idempotency_key"], "idempotency_key")
        with self._tx():
            self._ensure_active(actor)
            _, replay = self._begin_write(
                "subscribe_work", actor, body, data.get("auth") or {}, idem)
            if replay is not None:
                return replay
            subscription_id = "sub_" + uuid.uuid4().hex
            now = _iso(self._now())
            expires = _iso(self._now() + timedelta(days=ttl))
            self._conn.execute(
                "INSERT INTO subscriptions(subscription_id,agent_id,query,"
                "capabilities_json,created_at,expires_at,status) VALUES(?,?,?,?,?,?,?)",
                (subscription_id, actor, query, _stable(caps), now, expires, "ACTIVE"))
            result = {"subscription_id": subscription_id, "agent_id": actor,
                      "query": query, "capabilities": caps,
                      "status": "ACTIVE", "created_at": now, "expires_at": expires}
            self._finish_write(
                "subscribe_work", actor, body, idem, result,
                event_type="work.subscription.created", object_type="subscription",
                object_id=subscription_id)
            return result

    def _validate_work_deadline(self, value: str) -> str:
        deadline = self._parse_time(value, "delivery_deadline")
        now = self._now()
        if deadline <= now or deadline > now + timedelta(days=MAX_WORK_DAYS):
            raise MarketError("delivery_deadline must be within the next 30 days",
                              field="delivery_deadline")
        return _iso(deadline)

    def _post_work(self, data: dict) -> dict:
        actor = self._id(data.get("buyer_id"), "buyer_id")
        body = {"title": data.get("title", ""),
                "description": data.get("description", ""),
                "required_capabilities": data.get("required_capabilities", []),
                "budget_minor": int(data.get("budget_minor", 0)),
                "currency": str(data.get("currency", "USD")).upper(),
                "allowed_rails": data.get("allowed_rails", []),
                "delivery_deadline": data.get("delivery_deadline", ""),
                "idempotency_key": data.get("idempotency_key", "")}
        title = self._text(body["title"], "title", maximum=180)
        description = self._text(body["description"], "description")
        caps = self._tags(body["required_capabilities"], "required_capabilities")
        budget = body["budget_minor"]
        if not 1 <= budget <= MAX_BUDGET_MINOR:
            raise MarketError("budget_minor outside 1..10000000", field="budget_minor")
        currency = body["currency"]
        if currency not in ALLOWED_CURRENCIES:
            raise MarketError("currency must be USD or USDC", field="currency")
        rails = self._tags(body["allowed_rails"], "allowed_rails")
        if not set(rails).issubset(ALLOWED_RAILS):
            raise MarketError("unsupported payment rail", field="allowed_rails",
                              constraint=", ".join(sorted(ALLOWED_RAILS)))
        deadline = self._validate_work_deadline(body["delivery_deadline"])
        idem = self._id(body["idempotency_key"], "idempotency_key")
        with self._tx():
            self._ensure_active(actor)
            active = self._conn.execute(
                "SELECT COUNT(*) AS n FROM work_orders WHERE buyer_id=? AND "
                "status IN ('OPEN','AWARDED','DELIVERED','ACCEPTED_PAYMENT_DUE') AND expires_at>?",
                (actor, _iso(self._now()))).fetchone()["n"]
            if int(active) >= MAX_ACTIVE_WORK_PER_BUYER:
                raise MarketError("active work posting limit reached",
                                  error_type="RateLimitError", field="buyer_id")
            _, replay = self._begin_write(
                "post_work", actor, body, data.get("auth") or {}, idem)
            if replay is not None:
                return replay
            work_id = "work_" + uuid.uuid4().hex
            now = _iso(self._now())
            self._conn.execute(
                "INSERT INTO work_orders(work_id,buyer_id,title,description,"
                "capabilities_json,budget_minor,currency,allowed_rails_json,"
                "delivery_deadline,status,awarded_offer_id,created_at,updated_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (work_id, actor, title, description, _stable(caps), budget,
                 currency, _stable(rails), deadline, "OPEN", None,
                 now, now, deadline))
            matches = self._notify_subscribers(
                work_id, actor, title, description, caps, budget, currency)
            result = {"work_id": work_id, "buyer_id": actor, "title": title,
                      "description": description, "required_capabilities": caps,
                      "budget_minor": budget, "currency": currency,
                      "allowed_rails": rails, "delivery_deadline": deadline,
                      "status": "OPEN", "created_at": now,
                      "matched_subscriptions": matches,
                      "funding_status": "UNVERIFIED",
                      "money_movement": "none; offers select an existing rail"}
            self._finish_write(
                "post_work", actor, body, idem, result,
                event_type="work.posted", object_type="work", object_id=work_id,
                event_payload={"title": title, "required_capabilities": caps,
                               "budget_minor": budget, "currency": currency})
            return result

    def _notify_subscribers(self, work_id: str, buyer_id: str, title: str,
                            description: str, caps: list[str], budget: int,
                            currency: str) -> int:
        now = _iso(self._now())
        rows = self._conn.execute(
            "SELECT * FROM subscriptions WHERE status='ACTIVE' AND expires_at>?",
            (now,)).fetchall()
        work_tokens = _tokens(title + " " + description + " " + " ".join(caps))
        matched = 0
        for row in rows:
            if row["agent_id"] == buyer_id:
                continue
            wanted_caps = set(json.loads(row["capabilities_json"]))
            if wanted_caps and not wanted_caps.issubset(set(caps)):
                continue
            if row["query"] and not (_tokens(row["query"]) & work_tokens):
                continue
            message = (f"Matched work: {title}. Budget {budget} {currency} minor units. "
                       f"Inspect work {work_id} and submit a signed offer if qualified.")
            self._insert_message("market-network", row["agent_id"], "match",
                                 "New matching work", message, work_id, now)
            matched += 1
        return matched

    def search_work(self, query: str = "", capabilities: Optional[list[str]] = None,
                    currency: str = "", min_budget_minor: int = 0,
                    limit: int = 25) -> dict:
        caps = self._tags(capabilities or [], "capabilities", required=False)
        if currency:
            currency = currency.upper()
            if currency not in ALLOWED_CURRENCIES:
                raise MarketError("currency must be USD or USDC", field="currency")
        limit = max(1, min(int(limit), 100))
        want = _tokens(query)
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM work_orders WHERE status='OPEN' AND expires_at>?",
                (_iso(self._now()),)).fetchall()
            items = []
            for row in rows:
                required = json.loads(row["capabilities_json"])
                if caps and not set(caps).issubset(set(required)):
                    continue
                if currency and row["currency"] != currency:
                    continue
                if int(row["budget_minor"]) < int(min_budget_minor):
                    continue
                overlap = len(want & _tokens(
                    row["title"] + " " + row["description"] + " " + " ".join(required)))
                items.append({
                    "work_id": row["work_id"], "buyer_id": row["buyer_id"],
                    "title": row["title"], "description": row["description"],
                    "required_capabilities": required,
                    "budget_minor": row["budget_minor"], "currency": row["currency"],
                    "allowed_rails": json.loads(row["allowed_rails_json"]),
                    "delivery_deadline": row["delivery_deadline"],
                    "status": row["status"], "created_at": row["created_at"],
                    "funding_status": "UNVERIFIED", "match_score": overlap * 10,
                })
            items.sort(key=lambda item: (-item["match_score"],
                                         -item["budget_minor"], item["work_id"]))
            return {"count": len(items[:limit]), "results": items[:limit]}

    def get_work(self, work_id: str) -> dict:
        work = self._conn.execute(
            "SELECT * FROM work_orders WHERE work_id=?", (work_id,)).fetchone()
        if not work:
            raise MarketError("unknown work_id", field="work_id")
        offers = self._conn.execute(
            "SELECT * FROM offers WHERE work_id=? ORDER BY amount_minor,created_at",
            (work_id,)).fetchall()
        delivery = self._conn.execute(
            "SELECT * FROM deliveries WHERE work_id=?", (work_id,)).fetchone()
        settlement = self._conn.execute(
            "SELECT * FROM settlements WHERE work_id=?", (work_id,)).fetchone()
        return {
            "work_id": work["work_id"], "buyer_id": work["buyer_id"],
            "title": work["title"], "description": work["description"],
            "required_capabilities": json.loads(work["capabilities_json"]),
            "budget_minor": work["budget_minor"], "currency": work["currency"],
            "allowed_rails": json.loads(work["allowed_rails_json"]),
            "delivery_deadline": work["delivery_deadline"], "status": work["status"],
            "awarded_offer_id": work["awarded_offer_id"],
            "offers": [self._offer_public(row) for row in offers],
            "delivery": dict(delivery) if delivery else None,
            "settlement": self._settlement_public(settlement) if settlement else None,
        }

    def _validate_settlement(self, raw: dict, *, allowed_rails: list[str],
                             seller_profile: sqlite3.Row) -> dict:
        if not isinstance(raw, dict):
            raise MarketError("settlement must be an object", field="settlement")
        rail = str(raw.get("rail") or "")
        if rail not in ALLOWED_RAILS or rail not in allowed_rails:
            raise MarketError("settlement rail is not allowed by the work order",
                              field="settlement.rail")
        payment = json.loads(seller_profile["payment_json"])
        if rail == "x402":
            endpoint = self._public_https(
                raw.get("payment_endpoint") or payment.get("x402_endpoint", ""),
                "settlement.payment_endpoint")
            return {"rail": rail, "payment_endpoint": endpoint,
                    "network": str(raw.get("network") or payment.get("network") or ""),
                    "asset": str(raw.get("asset") or payment.get("asset") or "")}
        endpoint = self._public_https(
            raw.get("payment_endpoint") or payment.get("cash_escrow_endpoint", ""),
            "settlement.payment_endpoint")
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.hostname != "mcp.viridisconservation.com" or not parsed.path.endswith("/payments/mcp"):
            raise MarketError("cash escrow offer must use Viridis payments MCP",
                              field="settlement.payment_endpoint")
        payee_id = self._id(raw.get("payee_id") or payment.get("payee_id"),
                            "settlement.payee_id")
        return {"rail": rail, "payment_endpoint": endpoint,
                "payee_id": payee_id,
                "release_rail": "Stripe Connect when payee is onboarded; "
                                "certified manual fallback otherwise"}

    @staticmethod
    def _offer_public(row: sqlite3.Row) -> dict:
        return {"offer_id": row["offer_id"], "work_id": row["work_id"],
                "seller_id": row["seller_id"], "amount_minor": row["amount_minor"],
                "currency": row["currency"], "proposal": row["proposal"],
                "delivery_seconds": row["delivery_seconds"],
                "settlement": json.loads(row["settlement_json"]),
                "status": row["status"], "created_at": row["created_at"],
                "updated_at": row["updated_at"]}

    def _submit_offer(self, data: dict) -> dict:
        actor = self._id(data.get("seller_id"), "seller_id")
        body = {"work_id": data.get("work_id", ""),
                "amount_minor": int(data.get("amount_minor", 0)),
                "currency": str(data.get("currency", "USD")).upper(),
                "proposal": data.get("proposal", ""),
                "delivery_seconds": int(data.get("delivery_seconds", 0)),
                "settlement": data.get("settlement") or {},
                "idempotency_key": data.get("idempotency_key", "")}
        work_id = self._id(body["work_id"], "work_id")
        amount = body["amount_minor"]
        proposal = self._text(body["proposal"], "proposal")
        if not 60 <= body["delivery_seconds"] <= MAX_WORK_DAYS * 86400:
            raise MarketError("delivery_seconds outside 60..2592000",
                              field="delivery_seconds")
        idem = self._id(body["idempotency_key"], "idempotency_key")
        with self._tx():
            seller = self._ensure_active(actor)
            work = self._conn.execute(
                "SELECT * FROM work_orders WHERE work_id=?", (work_id,)).fetchone()
            if not work or work["status"] != "OPEN" or work["expires_at"] <= _iso(self._now()):
                raise MarketError("work is not open", error_type="ConflictError",
                                  field="work_id")
            if work["buyer_id"] == actor:
                raise MarketError("buyer cannot bid on its own work", field="seller_id")
            if body["currency"] != work["currency"]:
                raise MarketError("offer currency must match work currency", field="currency")
            if not 1 <= amount <= int(work["budget_minor"]):
                raise MarketError("offer exceeds work budget", field="amount_minor")
            if self._conn.execute("SELECT COUNT(*) FROM offers WHERE work_id=?",
                                  (work_id,)).fetchone()[0] >= MAX_OFFERS_PER_WORK:
                raise MarketError("offer limit reached", error_type="RateLimitError",
                                  field="work_id")
            settlement = self._validate_settlement(
                body["settlement"],
                allowed_rails=json.loads(work["allowed_rails_json"]),
                seller_profile=seller)
            _, replay = self._begin_write(
                "submit_offer", actor, body, data.get("auth") or {}, idem)
            if replay is not None:
                return replay
            offer_id = "offer_" + uuid.uuid4().hex
            now = _iso(self._now())
            try:
                self._conn.execute(
                    "INSERT INTO offers(offer_id,work_id,seller_id,amount_minor,currency,"
                    "proposal,delivery_seconds,settlement_json,status,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (offer_id, work_id, actor, amount, body["currency"], proposal,
                     body["delivery_seconds"], _stable(settlement), "SUBMITTED", now, now))
            except sqlite3.IntegrityError as exc:
                raise MarketError("seller already submitted an offer for this work",
                                  error_type="ConflictError", field="seller_id") from exc
            self._insert_message(actor, work["buyer_id"], "offer",
                                 "New offer received",
                                 f"{actor} offered {amount} {body['currency']} minor units for {work_id}.",
                                 work_id, now)
            result = self._offer_public(self._conn.execute(
                "SELECT * FROM offers WHERE offer_id=?", (offer_id,)).fetchone())
            self._finish_write(
                "submit_offer", actor, body, idem, result,
                event_type="offer.submitted", object_type="offer", object_id=offer_id,
                event_payload={"work_id": work_id, "amount_minor": amount,
                               "currency": body["currency"], "rail": settlement["rail"]})
            return result

    def _payment_plan(self, work: sqlite3.Row, offer: sqlite3.Row) -> dict:
        settlement = json.loads(offer["settlement_json"])
        common = {"executed": False, "work_id": work["work_id"],
                  "offer_id": offer["offer_id"], "buyer_id": work["buyer_id"],
                  "seller_id": offer["seller_id"],
                  "amount_minor": offer["amount_minor"], "currency": offer["currency"],
                  "rail": settlement["rail"],
                  "marketplace_money_movement": "none"}
        if settlement["rail"] == "x402":
            common["steps"] = [
                {"order": 1, "action": "call the seller payment endpoint and receive HTTP 402",
                 "endpoint": settlement["payment_endpoint"]},
                {"order": 2, "action": "buyer signs the x402 authorization within its own spend mandate"},
                {"order": 3, "action": "seller settles before serving and returns PAYMENT-RESPONSE"},
                {"order": 4, "action": "both parties attest the same transaction reference here"},
            ]
        else:
            common["steps"] = [
                {"order": 1, "action": "open escrow through the Viridis payments MCP",
                 "endpoint": settlement["payment_endpoint"],
                 "payer": work["buyer_id"], "payee": settlement["payee_id"],
                 "amount_minor": offer["amount_minor"], "currency": offer["currency"]},
                {"order": 2, "action": "escrow_checkout, pay Stripe-hosted URL, confirm_escrow_funding"},
                {"order": 3, "action": "after accepted delivery, release escrow; Connect auto-pays onboarded payee"},
                {"order": 4, "action": "both parties attest the resulting refund/transfer/settlement reference"},
            ]
        return common

    def _award_offer(self, data: dict) -> dict:
        actor = self._id(data.get("buyer_id"), "buyer_id")
        body = {"work_id": data.get("work_id", ""),
                "offer_id": data.get("offer_id", ""),
                "idempotency_key": data.get("idempotency_key", "")}
        work_id = self._id(body["work_id"], "work_id")
        offer_id = self._id(body["offer_id"], "offer_id")
        idem = self._id(body["idempotency_key"], "idempotency_key")
        with self._tx():
            self._ensure_active(actor)
            work = self._conn.execute(
                "SELECT * FROM work_orders WHERE work_id=?", (work_id,)).fetchone()
            offer = self._conn.execute(
                "SELECT * FROM offers WHERE offer_id=? AND work_id=?",
                (offer_id, work_id)).fetchone()
            if not work or work["buyer_id"] != actor:
                raise MarketError("only the posting buyer may award work",
                                  error_type="AuthenticationError", field="buyer_id")
            if work["status"] != "OPEN" or not offer or offer["status"] != "SUBMITTED":
                raise MarketError("work or offer is not awardable",
                                  error_type="ConflictError", field="offer_id")
            _, replay = self._begin_write(
                "award_offer", actor, body, data.get("auth") or {}, idem)
            if replay is not None:
                return replay
            now = _iso(self._now())
            self._conn.execute(
                "UPDATE work_orders SET status='AWARDED',awarded_offer_id=?,updated_at=? WHERE work_id=?",
                (offer_id, now, work_id))
            self._conn.execute(
                "UPDATE offers SET status=CASE WHEN offer_id=? THEN 'AWARDED' ELSE 'REJECTED' END,"
                "updated_at=? WHERE work_id=?", (offer_id, now, work_id))
            self._insert_message(actor, offer["seller_id"], "award",
                                 "Offer awarded",
                                 f"Your offer {offer_id} was awarded for {work_id}.",
                                 work_id, now)
            work = self._conn.execute(
                "SELECT * FROM work_orders WHERE work_id=?", (work_id,)).fetchone()
            offer = self._conn.execute(
                "SELECT * FROM offers WHERE offer_id=?", (offer_id,)).fetchone()
            result = {"work_id": work_id, "status": "AWARDED",
                      "awarded_offer": self._offer_public(offer),
                      "payment_plan": self._payment_plan(work, offer)}
            self._finish_write(
                "award_offer", actor, body, idem, result,
                event_type="work.awarded", object_type="work", object_id=work_id,
                event_payload={"offer_id": offer_id,
                               "seller_id": offer["seller_id"],
                               "amount_minor": offer["amount_minor"],
                               "currency": offer["currency"]})
            return result

    def _submit_delivery(self, data: dict) -> dict:
        actor = self._id(data.get("seller_id"), "seller_id")
        body = {"work_id": data.get("work_id", ""),
                "artifact_url": data.get("artifact_url", ""),
                "content_sha256": str(data.get("content_sha256", "")).lower(),
                "summary": data.get("summary", ""),
                "idempotency_key": data.get("idempotency_key", "")}
        work_id = self._id(body["work_id"], "work_id")
        artifact_url = self._public_https(body["artifact_url"], "artifact_url")
        if not SHA256_RE.fullmatch(body["content_sha256"]):
            raise MarketError("content_sha256 must be 64 lowercase hex", field="content_sha256")
        summary = self._text(body["summary"], "summary", maximum=2000)
        idem = self._id(body["idempotency_key"], "idempotency_key")
        with self._tx():
            self._ensure_active(actor)
            work = self._conn.execute(
                "SELECT * FROM work_orders WHERE work_id=?", (work_id,)).fetchone()
            offer = (self._conn.execute(
                "SELECT * FROM offers WHERE offer_id=?", (work["awarded_offer_id"],)).fetchone()
                     if work and work["awarded_offer_id"] else None)
            if not work or work["status"] != "AWARDED" or not offer or offer["seller_id"] != actor:
                raise MarketError("only the awarded seller may deliver",
                                  error_type="AuthenticationError", field="seller_id")
            _, replay = self._begin_write(
                "submit_delivery", actor, body, data.get("auth") or {}, idem)
            if replay is not None:
                return replay
            delivery_id = "delivery_" + uuid.uuid4().hex
            now = _iso(self._now())
            self._conn.execute(
                "INSERT INTO deliveries(delivery_id,work_id,seller_id,artifact_url,"
                "content_sha256,summary,created_at,accepted_at) VALUES(?,?,?,?,?,?,?,NULL)",
                (delivery_id, work_id, actor, artifact_url,
                 body["content_sha256"], summary, now))
            self._conn.execute(
                "UPDATE work_orders SET status='DELIVERED',updated_at=? WHERE work_id=?",
                (now, work_id))
            self._insert_message(actor, work["buyer_id"], "delivery",
                                 "Delivery ready",
                                 f"Delivery {delivery_id} is ready for {work_id}; verify digest before acceptance.",
                                 work_id, now)
            result = {"delivery_id": delivery_id, "work_id": work_id,
                      "seller_id": actor, "artifact_url": artifact_url,
                      "content_sha256": body["content_sha256"], "summary": summary,
                      "created_at": now, "status": "DELIVERED"}
            self._finish_write(
                "submit_delivery", actor, body, idem, result,
                event_type="work.delivered", object_type="delivery",
                object_id=delivery_id,
                event_payload={"work_id": work_id,
                               "content_sha256": body["content_sha256"]})
            return result

    def _accept_delivery(self, data: dict) -> dict:
        actor = self._id(data.get("buyer_id"), "buyer_id")
        body = {"work_id": data.get("work_id", ""),
                "content_sha256": str(data.get("content_sha256", "")).lower(),
                "idempotency_key": data.get("idempotency_key", "")}
        work_id = self._id(body["work_id"], "work_id")
        idem = self._id(body["idempotency_key"], "idempotency_key")
        with self._tx():
            self._ensure_active(actor)
            work = self._conn.execute(
                "SELECT * FROM work_orders WHERE work_id=?", (work_id,)).fetchone()
            delivery = self._conn.execute(
                "SELECT * FROM deliveries WHERE work_id=?", (work_id,)).fetchone()
            offer = (self._conn.execute(
                "SELECT * FROM offers WHERE offer_id=?", (work["awarded_offer_id"],)).fetchone()
                     if work and work["awarded_offer_id"] else None)
            if not work or work["buyer_id"] != actor:
                raise MarketError("only the posting buyer may accept",
                                  error_type="AuthenticationError", field="buyer_id")
            if work["status"] != "DELIVERED" or not delivery or not offer:
                raise MarketError("work is not awaiting acceptance",
                                  error_type="ConflictError", field="work_id")
            if body["content_sha256"] != delivery["content_sha256"]:
                raise MarketError("accepted digest does not match delivery",
                                  error_type="ConflictError", field="content_sha256")
            _, replay = self._begin_write(
                "accept_delivery", actor, body, data.get("auth") or {}, idem)
            if replay is not None:
                return replay
            now = _iso(self._now())
            self._conn.execute(
                "UPDATE deliveries SET accepted_at=? WHERE work_id=?", (now, work_id))
            self._conn.execute(
                "UPDATE work_orders SET status='ACCEPTED_PAYMENT_DUE',updated_at=? WHERE work_id=?",
                (now, work_id))
            self._insert_message(actor, offer["seller_id"], "acceptance",
                                 "Delivery accepted; settlement due",
                                 f"Delivery for {work_id} was accepted. Complete the awarded payment plan.",
                                 work_id, now)
            result = {"work_id": work_id, "status": "ACCEPTED_PAYMENT_DUE",
                      "accepted_at": now,
                      "payment_plan": self._payment_plan(work, offer),
                      "paid": False, "earnings_recorded": False}
            self._finish_write(
                "accept_delivery", actor, body, idem, result,
                event_type="work.accepted", object_type="work", object_id=work_id,
                event_payload={"content_sha256": body["content_sha256"],
                               "payment_due_minor": offer["amount_minor"]})
            return result

    @staticmethod
    def _settlement_public(row: sqlite3.Row) -> dict:
        return {"settlement_id": row["settlement_id"], "work_id": row["work_id"],
                "buyer_id": row["buyer_id"], "seller_id": row["seller_id"],
                "rail": row["rail"], "amount_minor": row["amount_minor"],
                "currency": row["currency"], "reference": row["reference"],
                "evidence_url": row["evidence_url"],
                "buyer_attested": bool(row["buyer_attested_at"]),
                "seller_attested": bool(row["seller_attested_at"]),
                "status": row["status"], "created_at": row["created_at"],
                "completed_at": row["completed_at"],
                "independently_verified": False,
                "verification_note": ("both counterparties attest the same receipt; "
                                      "the marketplace does not move funds or query private payment systems")}

    def _attest_settlement(self, data: dict) -> dict:
        actor = self._id(data.get("agent_id"))
        body = {"work_id": data.get("work_id", ""),
                "rail": data.get("rail", ""),
                "amount_minor": int(data.get("amount_minor", 0)),
                "currency": str(data.get("currency", "USD")).upper(),
                "reference": data.get("reference", ""),
                "evidence_url": data.get("evidence_url", ""),
                "idempotency_key": data.get("idempotency_key", "")}
        work_id = self._id(body["work_id"], "work_id")
        if body["rail"] not in ALLOWED_RAILS:
            raise MarketError("unsupported settlement rail", field="rail")
        reference = self._text(body["reference"], "reference", maximum=256)
        if not TX_RE.fullmatch(reference):
            raise MarketError("reference is not a plausible settlement identifier",
                              field="reference")
        evidence_url = self._public_https(body["evidence_url"], "evidence_url")
        idem = self._id(body["idempotency_key"], "idempotency_key")
        with self._tx():
            self._ensure_active(actor)
            work = self._conn.execute(
                "SELECT * FROM work_orders WHERE work_id=?", (work_id,)).fetchone()
            offer = (self._conn.execute(
                "SELECT * FROM offers WHERE offer_id=?", (work["awarded_offer_id"],)).fetchone()
                     if work and work["awarded_offer_id"] else None)
            if not work or work["status"] not in {"ACCEPTED_PAYMENT_DUE", "COMPLETED"} or not offer:
                raise MarketError("work is not ready for settlement attestation",
                                  error_type="ConflictError", field="work_id")
            if actor not in {work["buyer_id"], offer["seller_id"]}:
                raise MarketError("only the buyer or awarded seller may attest",
                                  error_type="AuthenticationError", field="agent_id")
            awarded = json.loads(offer["settlement_json"])
            if (body["rail"] != awarded["rail"] or
                    body["amount_minor"] != offer["amount_minor"] or
                    body["currency"] != offer["currency"]):
                raise MarketError("attestation does not match awarded terms",
                                  error_type="ConflictError", field="amount_minor")
            _, replay = self._begin_write(
                "attest_settlement", actor, body, data.get("auth") or {}, idem)
            if replay is not None:
                return replay
            now = _iso(self._now())
            settlement = self._conn.execute(
                "SELECT * FROM settlements WHERE work_id=?", (work_id,)).fetchone()
            role_column = "buyer_attested_at" if actor == work["buyer_id"] else "seller_attested_at"
            if settlement:
                exact = (settlement["rail"] == body["rail"] and
                         settlement["amount_minor"] == body["amount_minor"] and
                         settlement["currency"] == body["currency"] and
                         settlement["reference"] == reference and
                         settlement["evidence_url"] == evidence_url)
                if not exact:
                    raise MarketError("counterparty attestation mismatch",
                                      error_type="ConflictError", field="reference")
                self._conn.execute(
                    f"UPDATE settlements SET {role_column}=? WHERE work_id=?",
                    (now, work_id))
            else:
                settlement_id = "settlement_" + uuid.uuid4().hex
                buyer_at = now if role_column == "buyer_attested_at" else None
                seller_at = now if role_column == "seller_attested_at" else None
                self._conn.execute(
                    "INSERT INTO settlements(settlement_id,work_id,buyer_id,seller_id,rail,"
                    "amount_minor,currency,reference,evidence_url,buyer_attested_at,"
                    "seller_attested_at,status,created_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (settlement_id, work_id, work["buyer_id"], offer["seller_id"],
                     body["rail"], body["amount_minor"], body["currency"], reference,
                     evidence_url, buyer_at, seller_at, "PARTIALLY_ATTESTED", now, None))
            settlement = self._conn.execute(
                "SELECT * FROM settlements WHERE work_id=?", (work_id,)).fetchone()
            if settlement["buyer_attested_at"] and settlement["seller_attested_at"]:
                self._conn.execute(
                    "UPDATE settlements SET status='COUNTERPARTY_ATTESTED',completed_at=? WHERE work_id=?",
                    (now, work_id))
                self._conn.execute(
                    "UPDATE work_orders SET status='COMPLETED',updated_at=? WHERE work_id=?",
                    (now, work_id))
                self._insert_message("market-network", work["buyer_id"], "settlement",
                                     "Settlement attested", f"Both parties attested {reference} for {work_id}.",
                                     work_id, now)
                self._insert_message("market-network", offer["seller_id"], "settlement",
                                     "Earnings recorded", f"Both parties attested {reference} for {work_id}.",
                                     work_id, now)
            settlement = self._conn.execute(
                "SELECT * FROM settlements WHERE work_id=?", (work_id,)).fetchone()
            result = self._settlement_public(settlement)
            self._finish_write(
                "attest_settlement", actor, body, idem, result,
                event_type="settlement.attested", object_type="settlement",
                object_id=settlement["settlement_id"],
                event_payload={"work_id": work_id, "role": role_column,
                               "reference_sha256": hashlib.sha256(reference.encode()).hexdigest(),
                               "status": settlement["status"]})
            return result

    def _daily_count(self, actor: str, event_type: str) -> int:
        cutoff = _iso(self._now() - timedelta(days=1))
        return int(self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE actor_id=? AND event_type=? AND created_at>?",
            (actor, event_type, cutoff)).fetchone()[0])

    def _insert_message(self, sender: str, recipient: str, kind: str,
                        subject: str, body: str, work_id: Optional[str],
                        now: Optional[str] = None) -> dict:
        message_id = "msg_" + uuid.uuid4().hex
        created = now or _iso(self._now())
        content_sha = hashlib.sha256(body.encode()).hexdigest()
        self._conn.execute(
            "INSERT INTO messages(message_id,sender_id,recipient_id,kind,subject,body,"
            "work_id,content_sha256,created_at,read_at) VALUES(?,?,?,?,?,?,?,?,?,NULL)",
            (message_id, sender, recipient, kind, subject, body,
             work_id or None, content_sha, created))
        return {"message_id": message_id, "sender_id": sender,
                "recipient_id": recipient, "kind": kind, "subject": subject,
                "body": body, "work_id": work_id, "content_sha256": content_sha,
                "created_at": created, "read_at": None}

    def _send_message(self, data: dict) -> dict:
        actor = self._id(data.get("sender_id"), "sender_id")
        body = {"recipient_id": data.get("recipient_id", ""),
                "subject": data.get("subject", ""), "body": data.get("body", ""),
                "work_id": data.get("work_id", ""),
                "idempotency_key": data.get("idempotency_key", "")}
        recipient = self._id(body["recipient_id"], "recipient_id")
        subject = self._text(body["subject"], "subject", maximum=180)
        message_body = self._text(body["body"], "body")
        work_id = self._id(body["work_id"], "work_id") if body["work_id"] else ""
        idem = self._id(body["idempotency_key"], "idempotency_key")
        with self._tx():
            self._ensure_active(actor)
            self._ensure_active(recipient)
            if self._daily_count(actor, "message.sent") >= MAX_MESSAGES_PER_DAY:
                raise MarketError("daily message limit reached",
                                  error_type="RateLimitError", field="sender_id")
            if work_id and not self._conn.execute(
                    "SELECT 1 FROM work_orders WHERE work_id=?", (work_id,)).fetchone():
                raise MarketError("unknown work_id", field="work_id")
            _, replay = self._begin_write(
                "send_message", actor, body, data.get("auth") or {}, idem)
            if replay is not None:
                return replay
            result = self._insert_message(actor, recipient, "direct", subject,
                                          message_body, work_id or None)
            self._finish_write(
                "send_message", actor, body, idem, result,
                event_type="message.sent", object_type="message",
                object_id=result["message_id"],
                event_payload={"recipient_id": recipient, "work_id": work_id,
                               "content_sha256": result["content_sha256"]})
            return result

    def _read_inbox(self, data: dict) -> dict:
        actor = self._id(data.get("agent_id"))
        body = {"limit": max(1, min(int(data.get("limit", 25)), 100)),
                "after": str(data.get("after") or ""),
                "idempotency_key": data.get("idempotency_key", "")}
        if body["after"]:
            self._parse_time(body["after"], "after")
        idem = self._id(body["idempotency_key"], "idempotency_key")
        with self._tx():
            self._ensure_active(actor)
            _, replay = self._begin_write(
                "read_inbox", actor, body, data.get("auth") or {}, idem)
            if replay is not None:
                return replay
            if body["after"]:
                rows = self._conn.execute(
                    "SELECT * FROM messages WHERE recipient_id=? AND created_at>? "
                    "ORDER BY created_at LIMIT ?", (actor, body["after"], body["limit"])).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM messages WHERE recipient_id=? ORDER BY created_at DESC LIMIT ?",
                    (actor, body["limit"])).fetchall()
                rows = list(reversed(rows))
            now = _iso(self._now())
            ids = [row["message_id"] for row in rows]
            for message_id in ids:
                self._conn.execute(
                    "UPDATE messages SET read_at=COALESCE(read_at,?) WHERE message_id=?",
                    (now, message_id))
            result = {"agent_id": actor, "count": len(rows),
                      "messages": [{**dict(row), "read_at": row["read_at"] or now}
                                   for row in rows],
                      "read_at": now}
            self._finish_write(
                "read_inbox", actor, body, idem, result,
                event_type="inbox.read", object_type="inbox", object_id=actor,
                event_payload={"message_ids": ids})
            return result

    async def health(self) -> dict:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            stats = self.network_status()
            return {"status": "ok", "agent": self.config.name,
                    "version": self.config.version,
                    "checks": {"sqlite": "ok", "signature_auth": "ed25519",
                               "payment_credentials": "none"},
                    "market": stats}
        except Exception as exc:
            return {"status": "degraded", "agent": self.config.name,
                    "version": self.config.version,
                    "checks": {"sqlite": f"{type(exc).__name__}: {exc}"}}

    def network_status(self) -> dict:
        now = _iso(self._now())
        with self._lock:
            profiles = self._conn.execute(
                "SELECT COUNT(*) FROM profiles WHERE status='ACTIVE' AND expires_at>?",
                (now,)).fetchone()[0]
            open_work = self._conn.execute(
                "SELECT COUNT(*) FROM work_orders WHERE status='OPEN' AND expires_at>?",
                (now,)).fetchone()[0]
            completed = self._conn.execute(
                "SELECT COUNT(*) AS jobs,COALESCE(SUM(amount_minor),0) AS volume "
                "FROM settlements WHERE status='COUNTERPARTY_ATTESTED'").fetchone()
            messages = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            events = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            return {"protocol": PROTOCOL, "profiles_active": int(profiles),
                    "work_open": int(open_work),
                    "counterparty_attested_jobs": int(completed["jobs"]),
                    "counterparty_attested_volume_minor": int(completed["volume"]),
                    "messages_total": int(messages), "events_total": int(events),
                    "payment_rails": sorted(ALLOWED_RAILS),
                    "money_movement": "none",
                    "earnings_semantics": ("counted only after matching buyer+seller attestations; "
                                           "not independent chain verification")}

    def public_catalog(self) -> dict:
        return {"spec_version": PROTOCOL, "service": self.describe(),
                "status": self.network_status(),
                "profiles": self.search_agents(limit=100)["results"],
                "open_work": self.search_work(limit=100)["results"]}

    def describe(self) -> dict:
        return {
            "name": self.config.name, "version": self.config.version,
            "description": ("Signed agent capability discovery, intent subscriptions, "
                            "private agent messaging, and a durable work/offer/delivery/"
                            "settlement marketplace."),
            "capabilities": ["agent-seo", "capability-discovery", "intent-routing",
                             "agent-messaging", "work-marketplace", "offer-negotiation",
                             "settlement-attribution"],
            "security": {"write_auth": "Ed25519 signatures",
                         "replay_protection": "one-use nonce + idempotency key",
                         "private_keys": "never accepted or stored",
                         "payment_credentials": "none"},
            "payment_posture": {"rails": sorted(ALLOWED_RAILS),
                                "moves_money": False,
                                "marks_paid_from_one_party": False},
        }


def build(*, db_path: Optional[str] = None,
          now_fn: Callable[[], datetime] = _utcnow,
          seed_path: Optional[str] = None) -> MarketNetworkCore:
    path = db_path if db_path is not None else os.environ.get("MARKET_STATE_DB", ":memory:")
    core = MarketNetworkCore(db_path=path, now_fn=now_fn)
    seeds = seed_path if seed_path is not None else os.environ.get("MARKET_SEED_PROFILES", "")
    if seeds:
        seed_file = Path(seeds)
        if seed_file.exists():
            payload = json.loads(seed_file.read_text())
            core.seed_owned_profiles(payload.get("profiles", payload))
    return core
