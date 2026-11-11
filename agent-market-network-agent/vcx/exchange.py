"""Durable, simulation-only Compute Exchange within Agent Market Network.

All financial changes share one SQLite IMMEDIATE transaction with job state,
nonce consumption and idempotency results. Execution is a fixed pure allowlist;
no provider URL, executable, credential, payment rail or payout is accepted.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from fleet_utils.orc import canonical, seal
from .identity import MarketIdentity
from .ledger import SimulationLedger
from .providers import ProviderRegistry, _bounded_json

ACTIVE = {"RESERVED", "AUTHORIZED", "RUNNING", "SUBMITTED", "VERIFIED", "DISPUTED"}
TERMINAL = {"SETTLED", "REFUNDED", "CANCELLED", "EXPIRED", "REJECTED",
            "EXECUTION_FAILED", "VERIFICATION_FAILED"}
ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,119}$")
EXCHANGE_RE = re.compile(r"^sim-[a-z0-9]{4,40}$")
# Only these states occupy seller capacity, and only while their lease is live.
SLOT_STATES = "('RESERVED','AUTHORIZED','RUNNING')"
# The buyer may withdraw only before a result exists. Delivered work is settled
# by the deterministic contract, or frozen by a dispute for a third-party decision.
CANCELLABLE = {"CREATED", "QUOTED", "RESERVED", "AUTHORIZED", "RUNNING"}
LOG = logging.getLogger("viridis.vcx")
SCHEMA = """
CREATE TABLE IF NOT EXISTS vcx_listings (
 id TEXT PRIMARY KEY, seller TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vcx_jobs (
 id TEXT PRIMARY KEY, buyer TEXT NOT NULL, state TEXT NOT NULL,
 listing_id TEXT NOT NULL DEFAULT '', expires INTEGER NOT NULL DEFAULT 0,
 data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS vcx_active ON vcx_jobs(listing_id,state);
CREATE TABLE IF NOT EXISTS vcx_actions (
 actor TEXT NOT NULL, action TEXT NOT NULL, idem TEXT NOT NULL,
 digest TEXT NOT NULL, result TEXT NOT NULL, auth TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(actor,action,idem));
CREATE TABLE IF NOT EXISTS vcx_nonces (
 actor TEXT NOT NULL, nonce TEXT NOT NULL, PRIMARY KEY(actor,nonce));
CREATE TABLE IF NOT EXISTS vcx_events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL,
 state TEXT NOT NULL, at INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vcx_payment_notices (
 event_id TEXT PRIMARY KEY, digest TEXT NOT NULL, job TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vcx_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value, name, lo=0, hi=10**12):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"invalid {name}")
    return value


def ident(value):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError("invalid identifier")
    return value


def fields(body, allowed, required=()):
    if not isinstance(body, dict) or set(body) - set(allowed) - {"idempotency_key"}:
        raise ValueError("unsupported fields; credentials and arbitrary metadata are forbidden")
    if set(required) - set(body):
        raise ValueError("missing required fields")


class ComputeExchange:
    """Construct only in a trusted local process with an existing Market core.

    Owner bootstrap, payment notification and recovery methods are server-only;
    process() exposes only signed agent operations. There is no live mode.
    """

    def __init__(self, market, db_path, *, now_fn=time.time, fee_bps=500,
                 reservation_seconds=60, execution_seconds=30,
                 score_weights=None, receipt_signer=None, exchange_id=None):
        self.identity = MarketIdentity(market)
        self.market = market
        self.providers = ProviderRegistry()
        self.now_fn = now_fn
        self.fee_bps = integer(fee_bps, "fee_bps", 0, 10000)
        self.reservation_seconds = integer(reservation_seconds, "reservation_seconds", 1, 3600)
        self.execution_seconds = integer(execution_seconds, "execution_seconds", 1, 3600)
        self.weights = score_weights or {"price": 30, "reliability": 40, "latency": 20, "energy": 10}
        if set(self.weights) != {"price", "reliability", "latency", "energy"}:
            raise ValueError("invalid score weights")
        for v in self.weights.values():
            integer(v, "score weight", 0, 100)
        if sum(self.weights.values()) != 100:
            raise ValueError("score weights must sum to 100")
        self.receipt_signer = receipt_signer  # caller-owned key; never loaded from arguments/environment
        self._lock = threading.RLock()
        if str(db_path) == ":memory:":
            raise ValueError("durable file database required")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), isolation_level=None,
                                    check_same_thread=False, timeout=20)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        if "auth" not in {row[1] for row in self.conn.execute("PRAGMA table_info(vcx_actions)")}:
            self.conn.execute("ALTER TABLE vcx_actions ADD COLUMN auth TEXT NOT NULL DEFAULT ''")
        # One durable identity per state database. Every signed action names it,
        # so an envelope signed for this exchange is invalid on any other.
        wanted = exchange_id or "sim-" + uuid.uuid4().hex[:16]
        if not isinstance(wanted, str) or not EXCHANGE_RE.fullmatch(wanted):
            raise ValueError("invalid exchange_id")
        self.conn.execute("INSERT OR IGNORE INTO vcx_meta VALUES('exchange_id',?)", (wanted,))
        self.exchange_id = self.conn.execute(
            "SELECT value FROM vcx_meta WHERE key='exchange_id'").fetchone()[0]
        if exchange_id and exchange_id != self.exchange_id:
            raise ValueError("state database belongs to a different exchange_id")
        self.ledger = SimulationLedger(self.conn)

    def close(self):
        self.conn.close()

    def now(self):
        value = self.now_fn()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("clock requires timezone")
            value = value.timestamp()
        return int(value)

    @contextmanager
    def tx(self):
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    @contextmanager
    def snapshot(self):
        """Consistent read view across independently connected workers."""
        with self._lock:
            self.conn.execute("BEGIN")
            try:
                yield
            finally:
                self.conn.execute("ROLLBACK")

    def seed_account(self, actor, amount_minor, policy):
        """Trusted owner bootstrap; deliberately absent from process/MCP."""
        self.identity.profile(actor)
        with self.tx():
            return self.ledger.seed_account(actor, amount_minor, policy)

    def update_policy(self, actor, policy, change_id):
        """Trusted owner control; deliberately absent from process/MCP."""
        with self.tx():
            return self.ledger.update_policy(actor, policy, change_id)

    def freeze_account(self, actor, frozen, change_id):
        """Trusted owner kill switch; deliberately absent from process/MCP."""
        with self.tx():
            return self.ledger.set_frozen(actor, frozen, change_id)

    def signed_action(self, action):
        """Canonical action name a caller signs: mode, exchange and operation."""
        return "vcx." + self.exchange_id + "." + str(action)

    def _clock(self):
        return datetime.fromtimestamp(self.now(), timezone.utc)

    def _in_use(self, listing_id):
        return self.conn.execute(
            "SELECT count(*) FROM vcx_jobs WHERE listing_id=? AND state IN " + SLOT_STATES
            + " AND expires>?", (listing_id, self.now())).fetchone()[0]

    @staticmethod
    def _view(result):
        """Response boundary: a delivery is disclosed only once it is settled."""
        if isinstance(result, dict):
            if isinstance(result.get("recovered"), list):
                return {**result, "recovered": [ComputeExchange._view(x) for x in result["recovered"]]}
            if "execution_token" in result:  # internal fencing value; never leaves the process
                result = {k: v for k, v in result.items() if k != "execution_token"}
            if "job_id" in result and "output" in result and result.get("state") != "SETTLED":
                result = {k: v for k, v in result.items() if k != "output"}
                result["output_withheld_until_settlement"] = True
        return result

    def _load_job(self, job_id, actor=None):
        row = self.conn.execute("SELECT data FROM vcx_jobs WHERE id=?", (ident(job_id),)).fetchone()
        if row is None:
            raise ValueError("unknown job")
        job = json.loads(row[0])
        if actor is not None and actor not in {job["buyer_id"], job.get("seller_id")}:
            raise ValueError("job access denied")
        return job

    def _save(self, job, state=None, event=None):
        if state:
            job["state"] = state
        job["updated_at"] = self.now()
        self.conn.execute(
            "INSERT INTO vcx_jobs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "state=excluded.state,listing_id=excluded.listing_id,expires=excluded.expires,data=excluded.data",
            (job["job_id"], job["buyer_id"], job["state"], job.get("listing_id", ""),
             job.get("lease_until", 0), canonical(job)))
        self.conn.execute("INSERT INTO vcx_events(job,state,at,data) VALUES(?,?,?,?)",
                          (job["job_id"], job["state"], self.now(), canonical({"listing_id": job.get("listing_id", ""),
                                                  "seller_id": job.get("seller_id", ""),
                                                  "attempt": job.get("attempt", 0), **(event or {})})))
        return job

    def _listing(self, listing_id):
        row = self.conn.execute("SELECT data FROM vcx_listings WHERE id=?", (ident(listing_id),)).fetchone()
        if row is None:
            raise ValueError("unknown listing")
        return json.loads(row[0])

    def _active_listing(self, listing, job=None):
        if not listing["available_from"] <= self.now() < listing["expires_at"]:
            raise ValueError("listing unavailable or expired")
        profile = self.identity.profile(listing["seller_id"])
        if profile["profile_sha256"] != listing["profile_sha256"]:
            raise ValueError("listing identity changed; register new capacity")
        if job:
            if listing["service_id"] != job["service_id"]:
                raise ValueError("service mismatch")
            if not set(job["required_capabilities"]).issubset(listing["capabilities"]):
                raise ValueError("capability mismatch")
            if listing["reliability_bps"] < job["min_reliability_bps"]:
                raise ValueError("reliability constraint")
            if listing["latency_seconds"] > job["max_latency_seconds"]:
                raise ValueError("latency constraint")
            if self.now() + listing["latency_seconds"] > job["deadline"]:
                raise ValueError("deadline constraint")
            if job.get("security_posture"):
                posture = self.identity.security_posture(listing["seller_id"])
                if job["security_posture"] not in posture["postures"]:
                    raise ValueError("current security attestation required")
        return profile

    def list_capacity(self):
        with self.snapshot():
            result = []
            for row in self.conn.execute("SELECT data FROM vcx_listings ORDER BY id"):
                listing = json.loads(row[0])
                try:
                    self._active_listing(listing)
                except ValueError:
                    continue
                listing["observed_reliability"] = {
                    "settled_jobs": self.conn.execute(
                        "SELECT count(*) FROM vcx_events WHERE json_extract(data,'$.listing_id')=? AND state='SETTLED'",
                        (listing["listing_id"],)).fetchone()[0],
                    "failed_jobs": self.conn.execute(
                        "SELECT count(*) FROM vcx_events WHERE json_extract(data,'$.listing_id')=? AND state IN "
                        "('EXECUTION_FAILED','VERIFICATION_FAILED','REFUNDED') "
                        "AND json_extract(data,'$.fault')='seller'",
                        (listing["listing_id"],)).fetchone()[0],
                    "scope": "local_simulation_only"}
                result.append(listing)
            return {"mode": "simulation", "exchange_id": self.exchange_id,
                    "signed_action_prefix": self.signed_action(""),
                    "capacity": result, "services": self.providers.services()}

    def process(self, request):
        """Fleet-compatible safe result envelope; all private operations are signed."""
        name = "unknown"
        try:
            if not isinstance(request, dict) or set(request) - {"action", "actor_id", "body", "auth"}:
                raise ValueError("invalid exchange request")
            action = request.get("action")
            if action == "list_capacity":
                return {"status": "ok", "data": self.list_capacity()}
            reads = {"get_compute_job": self._read_job,
                     "get_compute_budget": self._read_budget,
                     "get_compute_earnings": self._read_earnings}
            handlers = {
                "register_capacity": self._register,
                "request_compute": self._request,
                "get_compute_quotes": self._quotes,
                "reserve_compute": self._reserve,
                "authorize_compute": self._authorize,
                "verify_compute_result": self._verify,
                "settle_compute": self._settle,
                "cancel_compute": self._cancel,
                "refund_compute": self._refund,
                "dispute_compute": self._dispute,
                "reinvest_compute": self._reinvest,
                "recover_compute_jobs": self._recover_actor,
            }
            if (not isinstance(action, str) or
                    (action not in reads and action not in handlers and action != "execute_compute_job")):
                raise ValueError("unknown exchange action")
            name = action
            actor = ident(request.get("actor_id"))
            body = request.get("body")
            if not isinstance(body, dict) or len(_bounded_json(body, 40000)) > 40000:
                raise ValueError("invalid exchange body")
            auth = request.get("auth")
            signed = self.signed_action(action)
            self.identity.verify(signed, actor, body, auth, self._clock())
            if action in reads:
                # Reads consume their nonce too: a captured read cannot be replayed.
                with self.tx():
                    self.identity.verify(signed, actor, body, auth, self._clock())
                    self._nonce(actor, auth)
                    return {"status": "ok", "data": self._view(reads[action](actor, body))}
            if action == "execute_compute_job":
                return {"status": "ok", "data": self._view(self._execute(actor, body, auth))}
            with self.tx():
                self.identity.verify(signed, actor, body, auth, self._clock())
                replay = self._begin(action, actor, body, auth)
                if replay is not None:
                    return {"status": "ok", "data": self._view(replay)}
                result = handlers[action](actor, body)
                self._finish(action, actor, body, result, auth)
                return {"status": "ok", "data": self._view(result)}
        except (ValueError, sqlite3.IntegrityError) as exc:
            # Do not echo input, exception strings, paths, credentials or provider errors.
            LOG.info("vcx rejected action=%s kind=%s code=%s", name, type(exc).__name__,
                     getattr(exc, "code", ""))
            return {"status": "error", "error_type": "ExchangeRejected",
                    "message": "Exchange request rejected; check schema, signature, state, budget and policy."}
        except Exception as exc:
            # An internal fault is never reported as a caller mistake, and never silently.
            LOG.error("vcx internal fault action=%s kind=%s", name, type(exc).__name__)
            return {"status": "error", "error_type": "ExchangeInternalError",
                    "message": "Exchange could not complete the request; no state was changed."}

    def _nonce(self, actor, auth):
        try:
            self.conn.execute("INSERT INTO vcx_nonces VALUES(?,?)", (actor, ident(auth.get("nonce"))))
        except sqlite3.IntegrityError:
            raise ValueError("nonce already used") from None

    def _begin(self, action, actor, body, auth):
        idem = ident(body.get("idempotency_key"))
        row = self.conn.execute("SELECT digest,result FROM vcx_actions WHERE actor=? AND action=? AND idem=?",
                                (actor, action, idem)).fetchone()
        if row:
            if row["digest"] != digest(body):
                raise ValueError("idempotency conflict")
            result = json.loads(row["result"])
            if result.get("execution_pending") is True:
                return self._load_job(result["job_id"], actor)
            return result
        self._nonce(actor, auth)
        return None

    def _finish(self, action, actor, body, result, auth):
        # The signed envelope is kept with the outcome as evidence of what was authorized.
        changed = self.conn.execute(
            "INSERT INTO vcx_actions(actor,action,idem,digest,result,auth) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(actor,action,idem) "
            "DO UPDATE SET result=excluded.result WHERE vcx_actions.digest=excluded.digest",
            (actor, action, body["idempotency_key"], digest(body), canonical(result),
             canonical({"signed_action": self.signed_action(action), **auth})))
        if changed.rowcount != 1:
            raise ValueError("idempotency conflict")

    def _register(self, actor, body):
        allowed = {"listing_id", "service_id", "description", "capabilities", "price_minor",
                   "currency", "available_from", "expires_at", "latency_seconds",
                   "reliability_bps", "energy_millijoules", "max_concurrent_jobs", "authorized_capacity"}
        fields(body, allowed, allowed)
        if body["authorized_capacity"] is not True or body["currency"] != "USD":
            raise ValueError("authorized simulated task capacity only")
        listing_id = ident(body["listing_id"])
        if self.conn.execute("SELECT 1 FROM vcx_listings WHERE id=?", (listing_id,)).fetchone():
            raise ValueError("immutable listing already exists")
        meta = next((x for x in self.providers.services() if x["service_id"] == body["service_id"]), None)
        if meta is None:
            raise ValueError("service not allowlisted")
        profile = self.identity.profile(actor)
        self.ledger.budget(actor)  # owner-authorized simulation earnings account required
        caps = body["capabilities"]
        if not isinstance(caps, list) or not caps or len(caps) > 16 or any(not isinstance(c, str) for c in caps):
            raise ValueError("invalid capabilities")
        if not set(caps).issubset(profile["capabilities"]) or not set(caps).issubset(meta["capabilities"]):
            raise ValueError("capabilities outside signed profile")
        # Free-text descriptions are a canonical service label; no arbitrary data channel.
        if body["description"] != meta["description"]:
            raise ValueError("description must match allowlisted service")
        integer(body["price_minor"], "price", 1, 10**8)
        integer(body["reliability_bps"], "reliability", 0, 10000)
        integer(body["latency_seconds"], "latency", 1, 3600)
        integer(body["energy_millijoules"], "energy", 0, 10**12)
        integer(body["max_concurrent_jobs"], "capacity", 1, 100)
        integer(body["available_from"], "availability")
        integer(body["expires_at"], "expiry")
        if body["expires_at"] <= max(self.now(), body["available_from"]):
            raise ValueError("invalid availability interval")
        listing = {k: v for k, v in body.items() if k != "idempotency_key"}
        listing.update(seller_id=actor, profile_sha256=profile["profile_sha256"],
                       task_schema=meta["task_schema"], service_version=meta["version"],
                       resource_requirements={"runtime": "trusted_local_python", "network_access": False,
                                              "max_input_bytes": 32768, "max_output_bytes": 100000},
                       security_requirements="signed_profile_and_fixed_pure_provider",
                       reliability_provenance="seller_declared_simulation", energy_provenance="seller_declared_simulation")
        self.conn.execute("INSERT INTO vcx_listings VALUES(?,?,?)", (listing_id, actor, canonical(listing)))
        return listing

    def _request(self, actor, body):
        required = {"request_id", "service_id", "payload", "max_price_minor", "required_capabilities", "deadline"}
        fields(body, required | {"max_latency_seconds", "min_reliability_bps", "security_posture", "prefer_energy"}, required)
        ident(body["request_id"])
        payload = self.providers.validate(body["service_id"], body["payload"])
        integer(body["max_price_minor"], "max price", 1, 10**8)
        integer(body["deadline"], "deadline", self.now()+1, self.now()+86400)
        caps = body["required_capabilities"]
        if not isinstance(caps, list) or len(caps) > 16 or any(not isinstance(c, str) or not ID_RE.fullmatch(c) for c in caps):
            raise ValueError("invalid capabilities")
        latency = integer(body.get("max_latency_seconds", 3600), "latency", 1, 3600)
        reliability = integer(body.get("min_reliability_bps", 0), "reliability", 0, 10000)
        posture = body.get("security_posture", "")
        if posture not in {"", "SCANNED", "RUNTIME_GUARDED", "INCIDENT_EVIDENCE_AVAILABLE"}:
            raise ValueError("invalid security posture")
        if type(body.get("prefer_energy", False)) is not bool:
            raise ValueError("invalid energy preference")
        job_id = "vcx-" + digest([actor, body["request_id"]])[:32]
        terms = {k: v for k, v in body.items() if k != "idempotency_key"}
        old = self.conn.execute("SELECT data FROM vcx_jobs WHERE id=?", (job_id,)).fetchone()
        if old:
            job = json.loads(old[0])
            if job["request_digest"] != digest(terms):
                raise ValueError("request conflict")
            return job
        job = {"job_id": job_id, "buyer_id": actor, "mode": "simulation", "currency": "USD",
               "balance_kind": "simulation", "state": "CREATED", "request_digest": digest(terms),
               "buyer_profile_sha256": self.identity.profile(actor)["profile_sha256"],
               "service_id": body["service_id"], "payload": payload,
               "max_price_minor": body["max_price_minor"], "required_capabilities": caps,
               "deadline": body["deadline"], "max_latency_seconds": latency,
               "min_reliability_bps": reliability, "security_posture": posture,
               "prefer_energy": body.get("prefer_energy", False), "created_at": self.now(),
               "attempt": 0, "excluded_listings": []}
        return self._save(job)

    def _buyer(self, actor, body, allowed=(), states=None):
        fields(body, {"job_id", *allowed}, {"job_id"})
        job = self._load_job(body["job_id"], actor)
        if actor != job["buyer_id"] or (states and job["state"] not in states):
            raise ValueError("wrong buyer or state")
        return job

    def _quotes(self, actor, body):
        job = self._buyer(actor, body, {"reassign"}, {"CREATED", "QUOTED", "EXECUTION_FAILED", "EXPIRED", "VERIFICATION_FAILED", "REJECTED"})
        if job["state"] in TERMINAL and not body.get("reassign"):
            raise ValueError("explicit reassignment required")
        if self.now() >= job["deadline"]:
            raise ValueError("job deadline elapsed")
        self._recover()  # expired leases never hold capacity or budget
        quotes = []
        for row in self.conn.execute("SELECT data FROM vcx_listings ORDER BY id"):
            listing = json.loads(row[0])
            if listing["listing_id"] in job["excluded_listings"] or listing["seller_id"] == actor:
                continue
            try:
                self._active_listing(listing, job)
            except ValueError:
                continue
            if listing["price_minor"] > job["max_price_minor"]:
                continue
            if self._in_use(listing["listing_id"]) >= listing["max_concurrent_jobs"]:
                continue
            parts = {
                "price": (job["max_price_minor"] - listing["price_minor"]) * 10000 // job["max_price_minor"],
                "reliability": listing["reliability_bps"],
                "latency": (job["max_latency_seconds"] - listing["latency_seconds"]) * 10000 // job["max_latency_seconds"],
                "energy": 100000000 // (10000 + listing["energy_millijoules"]) if job["prefer_energy"] else 0}
            terms = {"job_id": job["job_id"], "listing_id": listing["listing_id"],
                     "seller_id": listing["seller_id"], "price_minor": listing["price_minor"],
                     "fee_bps": self.fee_bps, "profile_sha256": listing["profile_sha256"],
                     "expires_at": min(job["deadline"], listing["expires_at"], self.now()+self.reservation_seconds),
                     "score_components_bps": parts, "score_weights": self.weights,
                     "score": sum(parts[k]*self.weights[k] for k in parts)}
            quotes.append({**terms, "quote_id": "quote-"+digest(terms)[:32]})
        quotes.sort(key=lambda x: (-x["score"], x["price_minor"], x["listing_id"]))
        job["quotes"] = quotes
        self._save(job, "QUOTED" if quotes else "REJECTED")
        return {"job_id": job["job_id"], "quotes": quotes, "mode": "simulation"}

    def _reserve(self, actor, body):
        job = self._buyer(actor, body, {"quote_id"}, {"QUOTED"})
        quote = next((x for x in job["quotes"] if x["quote_id"] == body.get("quote_id")), None)
        if not quote or self.now() >= quote["expires_at"]:
            raise ValueError("unknown or expired quote")
        listing = self._listing(quote["listing_id"])
        self._active_listing(listing, job)
        self._recover()
        if self._in_use(listing["listing_id"]) >= listing["max_concurrent_jobs"]:
            raise ValueError("capacity exhausted")
        job["attempt"] += 1
        job["hold_id"] = job["job_id"] + ":" + str(job["attempt"])
        self.ledger.reserve(job["hold_id"], actor, quote["price_minor"])
        # Remove previous attempt result and acceptance before reassignment.
        for key in ["output", "output_sha256", "verification", "receipt", "payment_confirmed", "execution_token",
                    "started_at", "submitted_at", "fault", "outcome_reason"]:
            job.pop(key, None)
        job.update(listing_id=quote["listing_id"], seller_id=quote["seller_id"], price_minor=quote["price_minor"],
                   fee_bps=quote["fee_bps"], quote=quote, service_version=listing["service_version"], lease_until=min(self.now()+self.reservation_seconds, job["deadline"]))
        return self._save(job, "RESERVED")

    def _authorize(self, actor, body):
        job = self._buyer(actor, body, states={"RESERVED"})
        if self.now() >= job["lease_until"]:
            raise ValueError("reservation expired")
        self._active_listing(self._listing(job["listing_id"]), job)
        job["payment_confirmed"] = True  # reserved simulated budget, never external funds
        return self._save(job, "AUTHORIZED", {"confirmation": "simulation_budget_only"})

    def confirm_simulated_payment(self, job_id, event_id, amount_minor):
        """Server-only test notification; cannot authorize/spend or mint balances."""
        ident(event_id)
        integer(amount_minor, "amount", 1)
        terms = {"job_id": job_id, "amount_minor": amount_minor, "mode": "simulation"}
        with self.tx():
            old = self.conn.execute("SELECT digest FROM vcx_payment_notices WHERE event_id=?", (event_id,)).fetchone()
            if old:
                if old[0] != digest(terms):
                    raise ValueError("payment event conflict")
                return {"mode": "simulation", "replayed": True}
            job = self._load_job(job_id)
            if job["state"] != "AUTHORIZED" or job["price_minor"] != amount_minor:
                raise ValueError("invalid simulation confirmation")
            self.conn.execute("INSERT INTO vcx_payment_notices VALUES(?,?,?)", (event_id, digest(terms), job_id))
            return {"mode": "simulation", "replayed": False}

    def _execute(self, actor, body, auth):
        fields(body, {"job_id"}, {"job_id"})
        action = "execute_compute_job"
        with self.tx():
            self.identity.verify(self.signed_action(action), actor, body, auth, self._clock())
            replay = self._begin(action, actor, body, auth)
            if replay is not None:
                return replay
            job = self._buyer(actor, body, states={"AUTHORIZED"})
            if self.now() >= job["lease_until"]:
                raise ValueError("authorization expired")
            self._active_listing(self._listing(job["listing_id"]), job)
            job.update(execution_token=uuid.uuid4().hex, started_at=self.now(),
                       lease_until=min(self.now()+self.execution_seconds, job["deadline"]))
            self._save(job, "RUNNING")
            # Freeze canonical execution terms before leaving the transaction.
            # Recovery/replays read the authoritative current job; they never run it twice.
            self._finish(action, actor, body,
                         {"job_id": job["job_id"], "execution_pending": True}, auth)
        # Only bounded, deterministic in-process test/Fleet services. No arbitrary workload runs.
        try:
            output = self.providers.execute(job["service_id"], job["payload"])
            canonical_output = canonical(output)
            if len(canonical_output) > 100000:
                raise ValueError("oversized result")
            failed = False
        except Exception:
            output = None
            failed = True
        with self.tx():
            current = self._load_job(job["job_id"])
            if current["state"] != "RUNNING" or current.get("execution_token") != job["execution_token"]:
                raise ValueError("execution fenced by cancellation or recovery")
            current.pop("execution_token", None)  # the fence is passed; the token is never kept or disclosed
            if self.now() >= current["lease_until"]:
                # v0.1 runs the provider in this process: a timeout is the host's, not the seller's.
                result = self._end(current, "EXECUTION_FAILED", "execution_timeout", "exchange")
            elif failed:
                result = self._end(current, "EXECUTION_FAILED", "provider_failed", "seller")
            else:
                current.update(output=output, output_sha256=digest(output), submitted_at=self.now())
                result = self._save(current, "SUBMITTED")
            self._finish(action, actor, body, result, auth)
            return result

    def _party(self, actor, body, states):
        """Buyer or the job's current seller; either may drive accepted work to payment."""
        fields(body, {"job_id"}, {"job_id"})
        job = self._load_job(body["job_id"], actor)
        if job["state"] not in states:
            raise ValueError("wrong state")
        return job

    def _check(self, job):
        """Deterministic acceptance. In v0.1 the exchange recomputes the same fixed function."""
        valid = self.providers.verify(job["service_id"], job["payload"], job["output"])
        valid = bool(valid and digest(job["output"]) == job["output_sha256"])
        job["verification"] = {"accepted": valid, "method": "deterministic_service_contract",
                               "performed_by": "exchange_recomputation",
                               "at": self.now(), "independent_research_validation": False}
        return valid

    def _verify(self, actor, body):
        # No lease expiry here: a delivered result is judged by the contract, not by the buyer's delay.
        job = self._party(actor, body, {"SUBMITTED"})
        if not self._check(job):
            return self._end(job, "VERIFICATION_FAILED", "contract_rejected", "seller")
        return self._save(job, "VERIFIED")

    def _receipt(self, job):
        settlement = job.get("settlement") or {}
        output = {k: job.get(k) for k in ["job_id", "buyer_id", "seller_id", "service_id", "listing_id",
                  "service_version", "price_minor", "currency", "fee_bps", "created_at", "started_at",
                  "submitted_at", "output_sha256", "verification", "fault", "outcome_reason"]}
        output.update(mode="simulation", balance_kind="simulation", settlement_state=job["state"],
                      quote_id=job.get("quote", {}).get("quote_id"),
                      input_sha256=digest(job["payload"]),
                      fee_minor=settlement.get("fee_minor"),
                      seller_net_minor=settlement.get("seller_net_minor"),
                      identity_references={"buyer_profile_sha256": job.get("buyer_profile_sha256"),
                                           "seller_profile_sha256": job.get("quote", {}).get("profile_sha256")},
                      resource_usage={"measured_energy": False, "input_bytes": len(canonical(job["payload"]).encode()),
                                      "output_bytes": len(canonical(job.get("output", {})).encode())},
                      closed_at=self.now(),
                      settled_at=self.now() if job["state"] == "SETTLED" else None,
                      exchange_id=self.exchange_id, attempt=job["attempt"])
        receipt = seal(output, issuer={"id": "vcx-local-simulation"},
                       subject={"id": job["job_id"]}, profile="vcx-delivery/0.2",
                       bindings={"payment": {"rail": "simulation", "redeemable": False}},
                       salt=digest([job["job_id"], job["attempt"], job["state"]]),
                       issued_at=datetime.fromtimestamp(self.now(), timezone.utc).isoformat())
        if self.receipt_signer:
            signed = self.receipt_signer.auth("vcx.receipt", "vcx-local-simulation", receipt)
            receipt = {"receipt": receipt, "signature": signed,
                       "public_key_b64": self.receipt_signer.public_key_b64,
                       "trust": "caller_configured_issuer_required"}
        return receipt

    def _do_settle(self, job):
        job["settlement"] = self.ledger.settle(job["hold_id"], job["buyer_id"], job["seller_id"],
                                               job["price_minor"], job["fee_bps"])
        job["state"] = "SETTLED"
        job["lease_until"] = 0
        job["receipt"] = self._receipt(job)
        return self._save(job)

    def _settle(self, actor, body):
        # Accepted work is paid: verified work settles whenever either party, or recovery, asks.
        job = self._party(actor, body, {"VERIFIED", "SETTLED"})
        if job["state"] == "SETTLED":
            return job
        return self._do_settle(job)

    def _end(self, job, state, reason, fault="none"):
        """Close without payment. ``fault`` is seller, buyer, exchange or none."""
        if job["state"] in ACTIVE:
            self.ledger.release(job["hold_id"], job["buyer_id"], job["price_minor"], reason)
        job.update(state=state, lease_until=0, outcome_reason=reason, fault=fault)
        job.pop("execution_token", None)
        if job.get("listing_id") and fault == "seller":
            job["excluded_listings"] = sorted(set(job["excluded_listings"]+[job["listing_id"]]))
        job["receipt"] = self._receipt(job)
        job.pop("output", None)  # unpaid work is never disclosed; its hash stays in the receipt
        return self._save(job, event={"fault": fault, "reason": reason})

    def _cancel(self, actor, body):
        job = self._buyer(actor, body)
        if job["state"] == "CANCELLED":
            return job
        if job["state"] not in CANCELLABLE:
            raise ValueError("delivered, disputed or terminal work cannot be cancelled")
        return self._end(job, "CANCELLED", "buyer_cancelled", "buyer")

    def _dispute(self, actor, body):
        # A dispute freezes the hold. It never releases it: the buyer cannot grant its own refund.
        job = self._buyer(actor, body, states={"SUBMITTED", "VERIFIED", "DISPUTED"})
        if job["state"] == "DISPUTED":
            return job
        job["disputed_from"] = job["state"]
        return self._save(job, "DISPUTED", {"reason": "buyer_requested_contract_review"})

    def _refund(self, actor, body):
        """Seller concession of a disputed job. Buyers cannot call this successfully."""
        fields(body, {"job_id"}, {"job_id"})
        job = self._load_job(body["job_id"], actor)
        if actor != job.get("seller_id") or job["state"] not in {"DISPUTED", "REFUNDED"}:
            raise ValueError("only the seller may concede a disputed job")
        if job["state"] == "REFUNDED":
            return job
        return self._end(job, "REFUNDED", "seller_conceded_dispute", "seller")

    def resolve_dispute(self, job_id, outcome, resolver_ref):
        """Trusted third-party decision; deliberately absent from process/MCP.

        ``settle`` is only possible when the deterministic contract accepts the
        delivery. ``resolver_ref`` names the arbitration record for the audit trail.
        """
        ident(resolver_ref)
        if outcome not in {"settle", "refund"}:
            raise ValueError("invalid dispute outcome")
        with self.tx():
            job = self._load_job(job_id)
            done = job.get("dispute_resolution")
            if done:
                if (done["outcome"], done["resolver_ref"]) != (outcome, resolver_ref):
                    raise ValueError("dispute already resolved")
                return job
            if job["state"] != "DISPUTED":
                raise ValueError("job is not disputed")
            job["dispute_resolution"] = {"outcome": outcome, "resolver_ref": resolver_ref,
                                         "at": self.now(), "decided_by": "trusted_local_resolver"}
            if outcome == "refund":
                return self._end(job, "REFUNDED", "arbitrated_refund", "seller")
            if not self._check(job):
                raise ValueError("contract does not accept this delivery")
            return self._do_settle(job)

    def _reinvest(self, actor, body):
        fields(body, {"amount_minor"}, {"amount_minor"})
        return self.ledger.reinvest(actor, body["amount_minor"], body["idempotency_key"])

    def recover(self, actor=None):
        """Trusted scheduler recovery; no re-execution after an ambiguous interruption."""
        with self.tx():
            return self._recover(actor)

    def _recover(self, actor=None):
        # Disputed jobs are frozen for a decision and are never auto-resolved here.
        rows = self.conn.execute("SELECT id FROM vcx_jobs WHERE state IN "
                                 "('RESERVED','AUTHORIZED','RUNNING','SUBMITTED','VERIFIED') "
                                 "AND expires<=?" + (" AND buyer=?" if actor else ""),
                                 (self.now(), actor) if actor else (self.now(),)).fetchall()
        results = []
        for row in rows:
            job = self._load_job(row[0])
            state = job["state"]
            if state in {"RESERVED", "AUTHORIZED"}:      # the buyer let its own lease lapse
                results.append(self._end(job, "EXPIRED", "recovered_expired_lease", "buyer"))
            elif state == "RUNNING":                     # interrupted host execution
                results.append(self._end(job, "EXECUTION_FAILED", "recovered_expired_lease", "exchange"))
            elif state == "SUBMITTED" and not self._check(job):
                results.append(self._end(job, "VERIFICATION_FAILED", "contract_rejected", "seller"))
            else:                                        # delivered and accepted work is paid
                results.append(self._do_settle(job))
        return {"mode": "simulation", "recovered": results}

    def _recover_actor(self, actor, body):
        fields(body, set())
        return self._recover(actor)

    def reconcile(self):
        """Trusted read-only audit of capital conservation and job/hold agreement."""
        with self._lock:
            self.conn.execute("BEGIN")
            try:
                report = self.ledger.reconcile()
                errors = list(report["errors"])
                for row in self.conn.execute("SELECT data FROM vcx_jobs"):
                    job = json.loads(row[0])
                    if not job.get("hold_id"):
                        continue
                    hold = self.conn.execute(
                        "SELECT buyer,price_minor,state FROM vcx_capital_holds WHERE job=?",
                        (job["hold_id"],)).fetchone()
                    expected = ("HELD" if job["state"] in ACTIVE else
                                "SETTLED" if job["state"] == "SETTLED" else "RELEASED")
                    if (not hold or tuple(hold) != (job["buyer_id"], job["price_minor"], expected)):
                        errors.append("job_hold_mismatch:"+job["job_id"])
                report.update(errors=errors, conserved=not errors,
                              status="ok" if not errors else "error")
                return report
            finally:
                self.conn.execute("ROLLBACK")

    def _read_job(self, actor, body):
        fields(body, {"job_id"}, {"job_id"})
        return self._load_job(body["job_id"], actor)

    def _read_budget(self, actor, body):
        fields(body, set())
        return self.ledger.budget(actor)

    def _read_earnings(self, actor, body):
        fields(body, set())
        return self.ledger.earnings(actor)
