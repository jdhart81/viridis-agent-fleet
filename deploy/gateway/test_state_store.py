#!/usr/bin/env python3
"""
Tests for state_store.py — one test per PS invariant, plus the invariant that
matters most for trust infrastructure: escrow exactly-once settlement (E6)
holds ACROSS a gateway restart.

Uses the real agent cores (escrow, identity) — stdlib-only, no mcp needed.
Run:  pytest deploy/gateway/test_state_store.py -q
"""
import asyncio
import hashlib
import importlib.util
import pickle
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from state_store import (  # noqa: E402
    StateStore,
    EXCLUDED_ATTRS,
    RUNTIME_BOUND_ATTRS,
)


def _load_core(agent_dir: str, tag: str):
    """Load an agent's core module in isolation (same idiom as the gateway)."""
    path = ROOT / agent_dir / "src" / "core.py"
    spec = importlib.util.spec_from_file_location(f"ss_test_{tag}_core", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ESCROW = _load_core("agent-escrow-agent", "escrow")
IDENTITY = _load_core("agent-identity-registry-agent", "identity")


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


# --------------------------------------------------------------------- #
# PS1 — durable-before-ack
# --------------------------------------------------------------------- #
def test_ps1_state_change_is_durable_before_result_returns(db):
    store = StateStore(db)
    core = ESCROW.build()
    store.attach("escrow", core)

    result = run(core.process({"action": "open", "payer": "a", "payee": "b",
                               "amount_minor": 500}))
    assert result["status"] == "ok"
    eid = result["data"]["escrow_id"]

    # Simulate a crash IMMEDIATELY after the response: a brand-new process
    # (new store handle, new core) must already see the escrow.
    store2 = StateStore(db)
    core2 = ESCROW.build()
    assert store2.restore("escrow", core2) is True
    status = run(core2.process({"action": "status", "escrow_id": eid}))
    assert status["status"] == "ok"
    assert status["data"]["state"] == "OPEN"


# --------------------------------------------------------------------- #
# PS2 — round-trip identity (including the tamper-evident audit chain)
# --------------------------------------------------------------------- #
def test_ps2_round_trip_preserves_state_and_audit_chain(db):
    store = StateStore(db)
    core = ESCROW.build()
    store.attach("escrow", core)
    eid = run(core.process({"action": "open", "payer": "a", "payee": "b",
                            "amount_minor": 1234}))["data"]["escrow_id"]
    run(core.process({"action": "fund", "escrow_id": eid, "payment_ref": "x402:t"}))

    core2 = ESCROW.build()
    StateStore(db).restore("escrow", core2)

    before = run(core.process({"action": "status", "escrow_id": eid}))["data"]
    after = run(core2.process({"action": "status", "escrow_id": eid}))["data"]
    assert before == after                     # identical record
    audit = run(core2.process({"action": "verify_audit", "escrow_id": eid}))
    assert audit["data"]["valid"] is True      # hash chain intact post-restore


# --------------------------------------------------------------------- #
# PS3 — persistence failure never breaks the fleet contract
# --------------------------------------------------------------------- #
def test_ps3_save_failure_never_raises_into_a_tool_call(db, monkeypatch):
    store = StateStore(db)
    core = ESCROW.build()
    store.attach("escrow", core)
    # kill the connection underneath the store
    store._conn.close()
    result = run(core.process({"action": "open", "payer": "a", "payee": "b",
                               "amount_minor": 100}))
    assert result["status"] == "ok"            # the call still succeeds
    assert store.status()["errors"]            # ...and the failure is surfaced


def test_ps3_corrupt_snapshot_restores_fresh_never_crashes(db):
    store = StateStore(db)
    core = ESCROW.build()
    store.attach("escrow", core)
    run(core.process({"action": "open", "payer": "a", "payee": "b",
                      "amount_minor": 100}))
    with store._lock:
        store._conn.execute("UPDATE agent_state SET snapshot=? WHERE agent=?",
                            (b"not a pickle", "escrow"))
        store._conn.commit()

    core2 = ESCROW.build()
    store2 = StateStore(db)
    assert store2.restore("escrow", core2) is False   # fresh state, no raise
    assert "escrow" in store2.status()["errors"]
    ok = run(core2.process({"action": "list"}))       # agent fully functional
    assert ok["status"] == "ok"


def test_ps3_unopenable_db_degrades_to_memory(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory")
    store = StateStore(str(blocker / "state.db"))   # parent is a file -> unopenable
    core = ESCROW.build()
    store.attach("escrow", core)
    result = run(core.process({"action": "open", "payer": "a", "payee": "b",
                               "amount_minor": 100}))
    assert result["status"] == "ok"
    assert store.available is False


# --------------------------------------------------------------------- #
# PS4 — namespace isolation
# --------------------------------------------------------------------- #
def test_ps4_agents_do_not_bleed_state(db):
    store = StateStore(db)
    esc, ident = ESCROW.build(), IDENTITY.build()
    store.attach("escrow", esc)
    store.attach("identity", ident)
    run(esc.process({"action": "open", "payer": "a", "payee": "b",
                     "amount_minor": 100}))
    run(ident.process({"action": "register", "agent_id": "agent-x",
                       "capabilities": ["measure"]}))

    esc2, ident2 = ESCROW.build(), IDENTITY.build()
    store2 = StateStore(db)
    store2.restore("escrow", esc2)
    store2.restore("identity", ident2)
    assert run(esc2.process({"action": "list"}))["data"]["count"] == 1
    assert run(ident2.process({"action": "resolve", "agent_id": "agent-x"})
               )["status"] == "ok"
    # identity's state never contains escrow structures and vice versa
    assert "_escrows" not in vars(ident2) or not vars(ident2).get("_escrows")


# --------------------------------------------------------------------- #
# PS5 — monotonic sequence
# --------------------------------------------------------------------- #
def test_ps5_seq_increments_per_change(db):
    store = StateStore(db)
    core = ESCROW.build()
    store.attach("escrow", core)
    for i in range(3):
        run(core.process({"action": "open", "payer": "a", "payee": "b",
                          "amount_minor": 100 + i}))
    cur = store._conn.execute("SELECT seq FROM agent_state WHERE agent='escrow'")
    assert cur.fetchone()[0] == 3


# --------------------------------------------------------------------- #
# PS6 — deterministic exclusion of ephemeral attributes
# --------------------------------------------------------------------- #
def test_ps6_config_and_logger_are_rebuilt_not_restored(db):
    store = StateStore(db)
    core = ESCROW.build()
    store.attach("escrow", core)
    run(core.process({"action": "open", "payer": "a", "payee": "b",
                      "amount_minor": 100}))
    snap = store._snapshot_state("escrow", core)
    for attr in EXCLUDED_ATTRS:
        assert attr not in snap
    # an unpicklable attribute is skipped, not fatal
    core._socket = lambda: None                # lambdas don't pickle
    assert store.save("escrow", core) in (True, False)  # no raise
    assert "_socket" not in store._snapshot_state("escrow", core)


def test_ps6_runtime_bound_receipt_path_is_never_restored_or_resaved(db):
    class SecurityCore:
        def __init__(self, receipt_db_path):
            self._receipt_db_path = receipt_db_path
            self._receipts = [{"receipt_id": "receipt-1"}]

    legacy_state = {
        "_receipt_db_path": "/data/security_preflight_receipts.sqlite3",
        "_receipts": [{"receipt_id": "receipt-1"}],
    }
    blob = pickle.dumps(legacy_state, protocol=pickle.HIGHEST_PROTOCOL)
    store = StateStore(db)
    store._conn.execute(
        "INSERT INTO agent_state(agent, seq, snapshot, sha256, updated_at) "
        "VALUES(?,?,?,?,?)",
        (
            "security-preflight",
            2,
            blob,
            hashlib.sha256(blob).hexdigest(),
            "2026-07-28T00:00:00+00:00",
        ),
    )
    store._conn.commit()

    core = SecurityCore(":memory:")
    assert store.restore("security-preflight", core) is True
    assert core._receipt_db_path == ":memory:"
    assert core._receipts == [{"receipt_id": "receipt-1"}]
    assert RUNTIME_BOUND_ATTRS["security-preflight"] == frozenset(
        {"_receipt_db_path"}
    )

    snap = store._snapshot_state("security-preflight", core)
    assert "_receipt_db_path" not in snap
    assert snap["_receipts"] == [{"receipt_id": "receipt-1"}]


# --------------------------------------------------------------------- #
# PS7 — read-only actions do not write
# --------------------------------------------------------------------- #
def test_ps7_reads_are_free(db):
    store = StateStore(db)
    core = ESCROW.build()
    store.attach("escrow", core)
    run(core.process({"action": "open", "payer": "a", "payee": "b",
                      "amount_minor": 100}))
    seq_before = store._conn.execute(
        "SELECT seq FROM agent_state WHERE agent='escrow'").fetchone()[0]
    for _ in range(5):
        run(core.process({"action": "list"}))
    seq_after = store._conn.execute(
        "SELECT seq FROM agent_state WHERE agent='escrow'").fetchone()[0]
    assert seq_after == seq_before


# --------------------------------------------------------------------- #
# PS8 — the gateway eviction pattern: every agent's classes live in
# `src.core`, evicted before the next agent loads. Reproduces the bug the
# selftest caught: without module context, pickling binds classes to the
# LAST loaded agent's module and every earlier agent fails to persist.
# --------------------------------------------------------------------- #
def _load_as_src_core(agent_dir: str):
    """Load an agent core exactly the way the gateway's adapters do: as the
    `src.core` submodule of a real `src` package (both end up in sys.modules,
    both are captured as the agent's module context)."""
    for m in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
    pkg_spec = importlib.util.spec_from_file_location(
        "src", ROOT / agent_dir / "src" / "__init__.py",
        submodule_search_locations=[str(ROOT / agent_dir / "src")])
    pkg = importlib.util.module_from_spec(pkg_spec)
    sys.modules["src"] = pkg
    pkg_spec.loader.exec_module(pkg)
    spec = importlib.util.spec_from_file_location(
        "src.core", ROOT / agent_dir / "src" / "core.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["src.core"] = mod
    spec.loader.exec_module(mod)
    return {"src": pkg, "src.core": mod}


def test_ps8_persists_under_gateway_module_eviction(db):
    store = StateStore(db)

    escrow_ctx = _load_as_src_core("agent-escrow-agent")
    esc = escrow_ctx["src.core"].build()
    store.register_modules("escrow", escrow_ctx)
    store.attach("escrow", esc)

    # the NEXT agent load evicts escrow's src.core — exactly like build_app()
    identity_ctx = _load_as_src_core("agent-identity-registry-agent")
    ident = identity_ctx["src.core"].build()
    store.register_modules("identity", identity_ctx)
    store.attach("identity", ident)

    r = run(esc.process({"action": "open", "payer": "a", "payee": "b",
                         "amount_minor": 500}))
    assert r["status"] == "ok"
    # the save must NOT have been silently skipped (this was the bug)
    assert "_escrows" not in store._skipped_attrs.get("escrow", set())
    cur = store._conn.execute(
        "SELECT seq FROM agent_state WHERE agent='escrow'").fetchone()
    assert cur is not None and cur[0] >= 1

    # restart: fresh store, fresh cores, same eviction order
    escrow_ctx2 = _load_as_src_core("agent-escrow-agent")
    esc2 = escrow_ctx2["src.core"].build()
    _load_as_src_core("agent-identity-registry-agent")  # evicts again
    store2 = StateStore(db)
    store2.register_modules("escrow", escrow_ctx2)
    assert store2.restore("escrow", esc2) is True
    got = run(esc2.process({"action": "status",
                            "escrow_id": r["data"]["escrow_id"]}))
    assert got["status"] == "ok" and got["data"]["state"] == "OPEN"


# --------------------------------------------------------------------- #
# PS9 — capital-path group snapshots commit all-or-nothing
# --------------------------------------------------------------------- #
class _Box:
    def __init__(self, value):
        self.value = value


def test_ps9_save_many_commits_both_snapshots(db):
    store = StateStore(db)
    a, b = _Box(1), _Box(2)
    assert store.save_many({"a": a, "b": b}) is True

    store2 = StateStore(db)
    a2, b2 = _Box(0), _Box(0)
    assert store2.restore("a", a2) is True
    assert store2.restore("b", b2) is True
    assert (a2.value, b2.value) == (1, 2)


def test_ps9_second_write_failure_rolls_back_the_group(db):
    store = StateStore(db)
    a, b = _Box(1), _Box(2)
    assert store.save_many({"a": a, "b": b}) is True
    a.value, b.value = 10, 20
    real = store._conn

    class FailingSecondInsert:
        def __init__(self, conn):
            self.conn = conn
            self.inserts = 0

        def execute(self, sql, params=()):
            if sql.lstrip().startswith("INSERT INTO agent_state"):
                self.inserts += 1
                if self.inserts == 2:
                    raise RuntimeError("simulated second snapshot failure")
            return self.conn.execute(sql, params)

        def commit(self):
            return self.conn.commit()

        def rollback(self):
            return self.conn.rollback()

    store._conn = FailingSecondInsert(real)
    assert store.save_many({"a": a, "b": b}) is False
    assert "__group__" in store.status()["errors"]

    # The first INSERT was part of the same transaction and was rolled back.
    fresh = StateStore(db)
    a2, b2 = _Box(0), _Box(0)
    assert fresh.restore("a", a2) and fresh.restore("b", b2)
    assert (a2.value, b2.value) == (1, 2)


# --------------------------------------------------------------------- #
# PS10/PS11 — bounded artifacts and pre-deploy snapshot compatibility
# --------------------------------------------------------------------- #
class _ReportsBox:
    def __init__(self, count):
        self.reports = {f"r-{index:04d}": {"index": index}
                        for index in range(count)}


def test_ps10_bounds_known_artifact_store_and_hashes_evictions(db):
    store = StateStore(db)
    box = _ReportsBox(505)
    assert store.save("smartscale", box) is True
    assert len(box.reports) == 500
    assert list(box.reports)[0] == "r-0005"
    evidence = box._state_store_evictions["reports"]
    assert evidence["evicted_count"] == 5
    assert len(evidence["sha256_chain"]) == 64

    restored = _ReportsBox(0)
    assert StateStore(db).restore("smartscale", restored) is True
    assert len(restored.reports) == 500
    assert restored._state_store_evictions["reports"]["evicted_count"] == 5


def test_ps11_compatibility_report_detects_checksum_drift(db):
    store = StateStore(db)
    box = _Box(7)
    assert store.save("box", box) is True
    clean = store.compatibility_report({"box": _Box(0)})
    assert clean["status"] == "ok"
    assert clean["rows"]["box"]["current_core_loaded"] is True

    store._conn.execute(
        "UPDATE agent_state SET sha256=? WHERE agent=?",
        ("0" * 64, "box"))
    store._conn.commit()
    broken = store.compatibility_report({"box": _Box(0)})
    assert broken["status"] == "error"
    assert broken["errors"]["box"] == "snapshot SHA-256 mismatch"


# --------------------------------------------------------------------- #
# The money invariant: E6 exactly-once settlement holds ACROSS restarts
# --------------------------------------------------------------------- #
def test_e6_exactly_once_settlement_survives_restart(db):
    store = StateStore(db)
    core = ESCROW.build()
    store.attach("escrow", core)
    eid = run(core.process({"action": "open", "payer": "buyer", "payee": "seller",
                            "amount_minor": 500}))["data"]["escrow_id"]
    run(core.process({"action": "fund", "escrow_id": eid}))
    first = run(core.process({"action": "release", "escrow_id": eid,
                              "delivery_proof": "sha256:job"}))
    assert first["data"]["state"] == "RELEASED"

    # ---- restart ----
    core2 = ESCROW.build()
    StateStore(db).restore("escrow", core2)

    second = run(core2.process({"action": "release", "escrow_id": eid}))
    assert second["data"]["state"] == "RELEASED"       # idempotent terminal
    assert second["data"]["audit_len"] == first["data"]["audit_len"]  # no new payout event
    refund = run(core2.process({"action": "refund", "escrow_id": eid}))
    # E6/E1: refund after release is refused or returns the terminal record —
    # under NO reading does a released escrow pay out twice.
    assert refund.get("data", {}).get("state", "RELEASED") == "RELEASED" \
        or refund["status"] == "error"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
