#!/usr/bin/env python3
"""
StateStore — durable persistence adapter for the Viridis Agent Stable gateway.

Closes the round-1 gap named in viridis_mcp_gateway.py ("stateless-restart
semantics; the persistence adapter is a tracked follow-up"). An escrow that
forgets escrows on restart cannot be sold as trust infrastructure; this module
makes every agent's state survive container restarts, image updates, and
droplet reboots — with ZERO changes to the 13 agent cores.

Design: gateway-level write-through snapshots.
  - Each agent core keeps its stdlib in-memory state (by design).
  - The gateway wraps each core's `process()`; after any call that CHANGES
    state, the new state is persisted to SQLite BEFORE the result is returned
    to the caller (durable-before-ack).
  - At boot, each core's state is restored from the last snapshot.

--- INVARIANTS (spec-invariance contract) ---
PS1  Durable-before-ack: if process() returns a result that changed agent
     state, that state has already been committed to disk (WAL, synchronous
     FULL). A crash immediately after the response loses nothing.
PS2  Round-trip identity: restore(save(state)) == state for every picklable
     state attribute. Verified per boot: restore failure of one agent never
     corrupts another's state.
PS3  Never break the fleet contract: no persistence error (save, restore,
     disk full, corrupt blob) ever raises into a tool call or crashes the
     gateway. Failures degrade to in-memory semantics with a CRITICAL log,
     and are surfaced via status() so /healthz can report them.
PS4  Namespace isolation: exactly one row per agent name; agents cannot read
     or clobber each other's state.
PS5  Monotonic sequence: each save increments a per-agent seq; restore always
     loads the latest committed snapshot.
PS6  Ephemeral attributes are excluded deterministically: EXCLUDED_ATTRS
     (config, logger, process — recreated by build()/attach(), so code
     upgrades win over stale snapshots) plus any attribute that fails to
     pickle (logged once).
PS7  No-op writes are skipped: read-only actions (status/list/verify) do not
     touch disk (fingerprint comparison), so persistence adds no IO to reads.
PS8  Module-context correctness: the gateway loads every agent's core as
     `src.core` and EVICTS it before loading the next (adapter isolation), so
     pickle-by-reference would bind all classes to the LAST agent's module.
     save/restore therefore accept the agent's own module dict and swap it
     into sys.modules around each pickle operation, so each agent's state
     always (de)serializes against its own classes.
PS9  Atomic group commit: capital-path mutations that span more than one core
     can persist all changed snapshots in one SQLite transaction. Any failure
     rolls the transaction back and returns False, allowing the caller to undo
     in-memory reservations before granting service.

Usage (see viridis_mcp_gateway.build_app):
    store = StateStore.open_default()          # STATE_DB env / /data / local
    store.restore(name, core)                  # at boot, before serving
    store.attach(name, core)                   # wraps core.process
    ...
    store.status()                             # for /healthz
"""
from __future__ import annotations

import contextlib
import functools
import hashlib
import inspect
import logging
import os
import pickle
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("viridis.state_store")

# Recreated by build()/attach() on every boot; excluding them means code
# upgrades always win over stale snapshots.
EXCLUDED_ATTRS = frozenset({"config", "logger", "process"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_state (
    agent      TEXT PRIMARY KEY,
    seq        INTEGER NOT NULL,
    snapshot   BLOB NOT NULL,
    sha256     TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    """SQLite-backed write-through snapshot store for agent cores."""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._last_sha: Dict[str, str] = {}      # PS7 fingerprint cache
        self._skipped_attrs: Dict[str, set] = {}  # PS6 log-once bookkeeping
        self._errors: Dict[str, str] = {}         # PS3 surfaced via status()
        self._modules: Dict[str, Dict[str, Any]] = {}  # PS8 per-agent module ctx
        self.available = False
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")  # PS1: durable commits
            self._conn.execute(_SCHEMA)
            self._conn.commit()
            self.available = True
        except Exception as e:  # PS3: never crash the gateway
            self._errors["__open__"] = f"{type(e).__name__}: {e}"
            logger.critical("StateStore UNAVAILABLE (%s) — running in-memory. "
                            "State will NOT survive restart.", e)

    # ------------------------------------------------------------------ #
    # construction helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def open_default(cls) -> "StateStore":
        """STATE_DB env var, else /data (docker volume), else local file."""
        env = os.environ.get("STATE_DB")
        if env:
            return cls(env)
        preferred = Path("/data/viridis_state.db")
        try:
            preferred.parent.mkdir(parents=True, exist_ok=True)
            probe = preferred.parent / ".write_probe"
            probe.write_text("ok")
            probe.unlink()
            return cls(str(preferred))
        except Exception:
            local = Path(__file__).resolve().parent / "viridis_state.db"
            logger.warning("/data not writable — using local state db %s "
                           "(fine for dev; mount a volume in production)", local)
            return cls(str(local))

    # ------------------------------------------------------------------ #
    # PS8 — per-agent module context
    # ------------------------------------------------------------------ #
    def register_modules(self, name: str, modules: Dict[str, Any]) -> None:
        """Register the module dict an agent's classes live in (e.g.
        {"src": <mod>, "src.core": <mod>}), captured right after the gateway
        loads that agent's adapter. Swapped into sys.modules around every
        pickle operation for that agent."""
        self._modules[name] = dict(modules)

    @contextlib.contextmanager
    def _module_context(self, name: str):
        ctx = self._modules.get(name)
        if not ctx:
            yield
            return
        saved: Dict[str, Any] = {}
        sentinel = object()
        for key, mod in ctx.items():
            saved[key] = sys.modules.get(key, sentinel)
            sys.modules[key] = mod
        try:
            yield
        finally:
            for key, prev in saved.items():
                if prev is sentinel:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = prev

    # ------------------------------------------------------------------ #
    # snapshot / restore
    # ------------------------------------------------------------------ #
    def _snapshot_state(self, name: str, core: Any) -> Dict[str, Any]:
        """Picklable subset of the core's instance state (PS6)."""
        state: Dict[str, Any] = {}
        skipped = self._skipped_attrs.setdefault(name, set())
        for attr, value in vars(core).items():
            if attr in EXCLUDED_ATTRS:
                continue
            try:
                pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
                state[attr] = value
            except Exception:
                if attr not in skipped:
                    skipped.add(attr)
                    logger.warning("state_store[%s]: attribute %r is not "
                                   "picklable — excluded from persistence",
                                   name, attr)
        return state

    def save(self, name: str, core: Any) -> bool:
        """Persist the core's current state. Returns True iff a durable
        write happened (False = no change or store unavailable). PS3: never
        raises."""
        if not self.available:
            return False
        try:
            with self._module_context(name):    # PS8
                blob = pickle.dumps(self._snapshot_state(name, core),
                                    protocol=pickle.HIGHEST_PROTOCOL)
            sha = hashlib.sha256(blob).hexdigest()
            if self._last_sha.get(name) == sha:   # PS7: skip no-op writes
                return False
            with self._lock:
                cur = self._conn.execute(
                    "SELECT seq FROM agent_state WHERE agent=?", (name,))
                row = cur.fetchone()
                seq = (row[0] + 1) if row else 1   # PS5
                self._conn.execute(
                    "INSERT INTO agent_state(agent, seq, snapshot, sha256, updated_at) "
                    "VALUES(?,?,?,?,?) ON CONFLICT(agent) DO UPDATE SET "
                    "seq=excluded.seq, snapshot=excluded.snapshot, "
                    "sha256=excluded.sha256, updated_at=excluded.updated_at",
                    (name, seq, blob, sha, _utcnow()))
                self._conn.commit()                # PS1: committed before ack
            self._last_sha[name] = sha
            self._errors.pop(name, None)
            return True
        except Exception as e:  # PS3
            self._errors[name] = f"{type(e).__name__}: {e}"
            logger.critical("state_store[%s]: SAVE FAILED (%s) — state is "
                            "in-memory only until the next successful save",
                            name, e)
            return False

    def save_many(self, cores: Dict[str, Any]) -> bool:
        """Atomically persist snapshots for multiple cores (PS9).

        Returns True only when at least one changed snapshot was durably
        committed. It never raises. Callers on a money/entitlement path must
        treat False as a failed commit and revert their in-memory reservation.
        """
        if not self.available or not isinstance(cores, dict) or not cores:
            return False
        prepared: Dict[str, tuple[bytes, str]] = {}
        try:
            for name, core in cores.items():
                if not isinstance(name, str) or not name:
                    raise ValueError("save_many names must be non-empty strings")
                with self._module_context(name):
                    blob = pickle.dumps(self._snapshot_state(name, core),
                                        protocol=pickle.HIGHEST_PROTOCOL)
                sha = hashlib.sha256(blob).hexdigest()
                if self._last_sha.get(name) != sha:
                    prepared[name] = (blob, sha)
            if not prepared:
                return False
            with self._lock:
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                    for name, (blob, sha) in prepared.items():
                        cur = self._conn.execute(
                            "SELECT seq FROM agent_state WHERE agent=?", (name,))
                        row = cur.fetchone()
                        seq = (row[0] + 1) if row else 1
                        self._conn.execute(
                            "INSERT INTO agent_state(agent, seq, snapshot, sha256, updated_at) "
                            "VALUES(?,?,?,?,?) ON CONFLICT(agent) DO UPDATE SET "
                            "seq=excluded.seq, snapshot=excluded.snapshot, "
                            "sha256=excluded.sha256, updated_at=excluded.updated_at",
                            (name, seq, blob, sha, _utcnow()))
                    self._conn.commit()
                except Exception:
                    self._conn.rollback()
                    raise
            for name, (_, sha) in prepared.items():
                self._last_sha[name] = sha
                self._errors.pop(name, None)
            self._errors.pop("__group__", None)
            return True
        except Exception as e:  # PS3/PS9
            label = ",".join(sorted(cores)) if isinstance(cores, dict) else "__group__"
            self._errors["__group__"] = f"{type(e).__name__}: {e} ({label})"
            logger.critical("state_store group SAVE FAILED (%s) — no grouped "
                            "snapshot was acknowledged", e)
            return False

    def restore(self, name: str, core: Any) -> bool:
        """Load the latest snapshot into the core (PS2). Returns True iff
        state was restored. PS3: failure -> fresh state, never a crash."""
        if not self.available:
            return False
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT snapshot, sha256 FROM agent_state WHERE agent=?",
                    (name,))
                row = cur.fetchone()
            if row is None:
                return False
            with self._module_context(name):    # PS8
                state = pickle.loads(row[0])
            for attr, value in state.items():
                setattr(core, attr, value)
            self._last_sha[name] = row[1]
            logger.info("state_store[%s]: restored %d attribute(s)",
                        name, len(state))
            return True
        except Exception as e:  # PS3: corrupt blob / renamed class -> fresh
            self._errors[name] = f"restore: {type(e).__name__}: {e}"
            logger.critical("state_store[%s]: RESTORE FAILED (%s) — starting "
                            "with fresh state; snapshot row preserved for "
                            "forensics", name, e)
            return False

    # ------------------------------------------------------------------ #
    # write-through wiring
    # ------------------------------------------------------------------ #
    def attach(self, name: str, core: Any) -> None:
        """Wrap core.process so state changes are durable before the result
        is returned to the caller (PS1). The wrapper matches the core's
        calling convention: async cores get an async wrapper, sync cores
        (e.g. smartscale, whose adapter calls process() without await) get
        a sync wrapper — changing the convention breaks the adapter."""
        original = core.process

        if inspect.iscoroutinefunction(original):
            @functools.wraps(original)
            async def process(input_data):
                result = await original(input_data)
                self.save(name, core)   # PS3: cannot raise
                return result
        else:
            @functools.wraps(original)
            def process(input_data):
                result = original(input_data)
                self.save(name, core)   # PS3: cannot raise
                return result

        core.process = process

    def save_all(self, cores: Dict[str, Any]) -> None:
        """Belt-and-braces snapshot (e.g. on graceful shutdown)."""
        for name, core in cores.items():
            self.save(name, core)

    # ------------------------------------------------------------------ #
    # observability
    # ------------------------------------------------------------------ #
    def status(self) -> Dict[str, Any]:
        """For /healthz: is persistence live, where, any errors."""
        return {
            "available": self.available,
            "db_path": self.db_path,
            "errors": dict(self._errors),
        }

    def close(self) -> None:
        if self.available:
            with self._lock:
                self._conn.close()
            self.available = False
