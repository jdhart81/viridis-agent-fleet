"""Maxwell v1 request-bound SHA-256 puzzles. No energy or trust claims.

This is a new wire protocol, not the older Argon2id-labelled scaffold.
Run the guard at the protected endpoint; never make a paid remote call for
each hostile request. Authentication, authorization and quotas remain required.
"""
import base64
import contextlib
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time


SCHEME = "maxwell-sha256-v1"
MAX_BODY = 65536
MAX_TOKEN = 2048


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def binding(tenant, subject, method, target, body):
    """Subject comes from server authentication/session logic, never a body field.

    Target includes the exact path AND query. Forward exactly these body bytes.
    """
    if not isinstance(body, bytes) or len(body) > MAX_BODY:
        raise ValueError("body exceeds 65536 bytes")
    for value in (tenant, subject, method, target):
        if not isinstance(value, str) or not 1 <= len(value) <= 512:
            raise ValueError("invalid request binding")
    return hashlib.sha256(canonical([tenant, subject, method, target,
                                    hashlib.sha256(body).hexdigest()])).hexdigest()


def valid_work(token, nonce, bits):
    if not isinstance(nonce, str) or re.fullmatch(r"0|[1-9][0-9]{0,15}", nonce) is None:
        return False
    digest = hashlib.sha256((token + "." + nonce).encode("ascii")).digest()
    return int.from_bytes(digest, "big") < (1 << (256 - bits))


def solve(challenge, max_attempts=262144, max_seconds=1.0):
    """Opt-in client helper; never automatically burn unbounded client compute."""
    if (challenge.get("scheme") != SCHEME
            or type(challenge.get("difficulty_bits")) is not int
            or not 1 <= challenge["difficulty_bits"] <= 20
            or not isinstance(challenge.get("token"), str)
            or len(challenge["token"]) > MAX_TOKEN
            or not challenge["token"].isascii()):
        raise ValueError("unsupported challenge")
    if (type(max_attempts) is not int or not 1 <= max_attempts <= 1048576
            or not isinstance(max_seconds, (int, float))
            or not 0 < max_seconds <= 5):
        raise ValueError("invalid solve budget")
    start = time.perf_counter()
    for nonce in range(max_attempts):
        if time.perf_counter() - start >= max_seconds:
            break
        if valid_work(challenge["token"], str(nonce), challenge["difficulty_bits"]):
            return {"token": challenge["token"], "nonce": str(nonce),
                    "attempts": nonce + 1, "elapsed_ms": (time.perf_counter() - start) * 1000}
    return {"status": "budget_exhausted", "solution": None}


class Guard:
    """Single-host guard with durable, atomic consumption across local workers.

    Stateless issuance; bounded consumed-token table. Each process has a fixed
    token bucket ahead of verification. Configure upstream aggregate limits
    across processes. A multi-host deployment requires a shared atomic store.
    """
    def __init__(self, key, db_path, *, bits=12, ttl=60, capacity=10000,
                 max_checks_per_second=100, clock=time.time):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("configure at least 32 secret bytes")
        if (type(bits) is not int or not 1 <= bits <= 20
                or type(ttl) is not int or not 1 <= ttl <= 120
                or type(capacity) is not int or not 1 <= capacity <= 100000
                or type(max_checks_per_second) is not int
                or not 1 <= max_checks_per_second <= 10000):
            raise ValueError("invalid guard limits")
        self.key, self.bits, self.ttl, self.capacity = key, bits, ttl, capacity
        self.clock = clock
        self.rate = max_checks_per_second
        self.tokens, self.last = float(self.rate), time.monotonic()
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(db_path), timeout=1, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS consumed (id TEXT PRIMARY KEY, expires INTEGER NOT NULL)")
        self.db.execute("CREATE INDEX IF NOT EXISTS expiry ON consumed(expires)")
        self.db.commit()

    def close(self):
        self.db.close()

    def _admit(self):
        now = time.monotonic()
        with self.lock:
            self.tokens = min(self.rate, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True

    def issue(self, request_binding):
        if not self._admit():
            return {"status": "busy", "retry_after_seconds": 1}
        if not isinstance(request_binding, str) or re.fullmatch("[a-f0-9]{64}", request_binding) is None:
            raise ValueError("invalid binding digest")
        now = int(self.clock())
        payload = {"v": 1, "id": secrets.token_hex(16), "binding": request_binding,
                   "bits": self.bits, "iat": now, "exp": now + self.ttl}
        encoded = base64.urlsafe_b64encode(canonical(payload)).decode().rstrip("=")
        signature = hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()
        return {"scheme": SCHEME, "token": encoded + "." + signature,
                "difficulty_bits": self.bits, "expires_at": payload["exp"],
                "expected_hash_attempts": 2 ** self.bits,
                "authorization_granted": False}

    def verify(self, token, nonce, request_binding):
        if not self._admit():
            return {"admitted": False, "reason": "busy"}
        if (not isinstance(token, str) or len(token) > MAX_TOKEN
                or not token.isascii()):
            return {"admitted": False, "reason": "invalid"}
        try:
            encoded, signature = token.split(".")
            expected = hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            payload = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4),
                                                 altchars=b"-_", validate=True))
            now = int(self.clock())
            if (payload["v"] != 1 or payload["bits"] != self.bits
                    or payload["binding"] != request_binding
                    or not payload["iat"] <= now < payload["exp"]
                    or not 0 < payload["exp"] - payload["iat"] <= self.ttl
                    or not valid_work(token, nonce, payload["bits"])):
                raise ValueError("proof")
        except (ValueError, KeyError, TypeError, UnicodeError):
            return {"admitted": False, "reason": "invalid"}
        # The only write is after valid work. Do not evict live entries: doing
        # so would revive already consumed proofs. Capacity exhaustion denies.
        with self.lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                self.db.execute("DELETE FROM consumed WHERE expires <= ?", (now,))
                if self.db.execute("SELECT count(*) FROM consumed").fetchone()[0] >= self.capacity:
                    self.db.rollback()
                    return {"admitted": False, "reason": "capacity"}
                self.db.execute("INSERT INTO consumed VALUES (?, ?)", (payload["id"], payload["exp"]))
                self.db.commit()
            except sqlite3.IntegrityError:
                self.db.rollback()
                return {"admitted": False, "reason": "replay"}
            except sqlite3.Error:
                with contextlib.suppress(sqlite3.Error):
                    self.db.rollback()
                return {"admitted": False, "reason": "store_unavailable"}
        return {"admitted": True, "reason": "work_verified", "authorization_granted": False}
