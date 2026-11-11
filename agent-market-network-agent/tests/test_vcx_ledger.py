"""Financial invariants for the disconnected VCX simulation ledger."""
import concurrent.futures
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vcx.ledger import LedgerError, SimulationLedger


POLICY = {"max_spend_minor": 2000, "reserve_minor": 100,
          "max_exposure_minor": 800, "reinvest_bps": 5000}


@pytest.fixture
def ledger(tmp_path):
    conn = sqlite3.connect(tmp_path / "capital.db")
    item = SimulationLedger(conn)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        item.seed_account("buyer", 1000, POLICY)
        item.seed_account("seller", 0, {**POLICY, "reserve_minor": 0})
    yield item
    conn.close()


def write(item, fn):
    with item.conn:
        item.conn.execute("BEGIN IMMEDIATE")
        return fn()


def error(code, fn):
    with pytest.raises(LedgerError) as caught:
        fn()
    assert caught.value.code == code


def test_balanced_settlement_fee_and_bounded_reinvestment(ledger):
    write(ledger, lambda: ledger.reserve("job", "buyer", 200))
    assert ledger.budget("buyer")["held_minor"] == 200
    settled = write(ledger, lambda: ledger.settle("job", "buyer", "seller", 200))
    assert settled["fee_minor"] == 10
    assert settled["seller_net_minor"] == 190
    assert ledger.earnings("seller")["allowed_reinvestment_minor"] == 95
    assert ledger.earnings("seller")["pending_earnings_minor"] == 190
    assert ledger.budget("seller")["available_budget_minor"] == 0
    write(ledger, lambda: ledger.reinvest("seller", 95, "owner-policy-1"))
    assert ledger.budget("seller")["available_budget_minor"] == 95
    assert ledger.earnings("seller")["allowed_reinvestment_minor"] == 0
    assert ledger.reconcile() == {
        "balance_type": "simulation", "simulation_only": True, "redeemable": False,
        "currency": "USD", "actual_settled_funds_minor": 0, "service_credits": 0,
        "status": "ok", "conserved": True, "errors": [], "journal_net_minor": 0,
        "available_minor": 895, "held_minor": 0, "pending_earnings_minor": 95,
        "marketplace_fees_minor": 10, "external_simulated_funding_minor": 1000,
        "external_payment_settlement_minor": 0, "simulation_released_minor": 0, "operations": 5,
    }


def test_earned_budget_funds_another_job_without_new_external_funding(ledger):
    write(ledger, lambda: ledger.reserve("first", "buyer", 400))
    write(ledger, lambda: ledger.settle("first", "buyer", "seller", 400))
    write(ledger, lambda: ledger.reinvest("seller", 190, "reinvest"))
    write(ledger, lambda: ledger.reserve("second", "seller", 150))
    write(ledger, lambda: ledger.settle("second", "seller", "buyer", 150))
    assert ledger.earnings("seller")["spent_minor"] == 150
    assert ledger.earnings("seller")["realized_margin_minor"] == 230
    assert ledger.reconcile()["external_simulated_funding_minor"] == 1000
    assert ledger.reconcile()["conserved"]


def test_every_mutation_requires_the_callers_transaction(ledger):
    for call in [lambda: ledger.seed_account("new", 5),
                 lambda: ledger.reserve("job", "buyer", 1),
                 lambda: ledger.release("job", "buyer", 1),
                 lambda: ledger.settle("job", "buyer", "seller", 1),
                 lambda: ledger.reinvest("seller", 1, "r")]:
        error("transaction_required", call)


def test_no_implicit_commit_and_rollback_includes_account_and_job_state(ledger):
    ledger.conn.execute("CREATE TABLE application_job(id TEXT)")
    ledger.conn.execute("BEGIN IMMEDIATE")
    ledger.conn.execute("INSERT INTO application_job VALUES('same-transaction')")
    ledger.reserve("atomic", "buyer", 500)
    SimulationLedger(ledger.conn)  # Schema initialization must not commit.
    ledger.conn.rollback()
    assert ledger.conn.execute("SELECT COUNT(*) FROM application_job").fetchone()[0] == 0
    assert ledger.budget("buyer")["available_minor"] == 1000
    assert ledger.budget("buyer")["held_minor"] == 0


@pytest.mark.parametrize("value", [True, False, 1.0, "100", -1, None, 10**20])
def test_non_integer_or_out_of_range_money_never_changes_journal(ledger, value):
    error("invalid_amount", lambda: write(ledger, lambda: ledger.reserve("job", "buyer", value)))
    assert ledger.reconcile()["operations"] == 2


def test_reserve_replay_and_financial_outcome_are_unique(ledger):
    write(ledger, lambda: ledger.reserve("job", "buyer", 200))
    assert write(ledger, lambda: ledger.reserve("job", "buyer", 200))["duplicate"]
    error("idempotency_conflict", lambda: write(ledger, lambda: ledger.reserve("job", "buyer", 201)))
    write(ledger, lambda: ledger.settle("job", "buyer", "seller", 200))
    assert write(ledger, lambda: ledger.settle("job", "buyer", "seller", 200))["duplicate"]
    error("idempotency_conflict", lambda: write(ledger, lambda: ledger.settle("job", "buyer", "seller", 200, 600)))
    error("reservation_closed", lambda: write(ledger, lambda: ledger.release("job", "buyer", 200)))
    assert ledger.earnings("buyer")["spent_minor"] == 200
    assert ledger.reconcile()["marketplace_fees_minor"] == 10


def test_release_restores_budget_once_and_never_calls_a_refund_rail(ledger):
    write(ledger, lambda: ledger.reserve("job", "buyer", 200))
    released = write(ledger, lambda: ledger.release("job", "buyer", 200, "verification_failed"))
    assert released["external_refund_minor"] == 0
    assert write(ledger, lambda: ledger.release("job", "buyer", 200, "verification_failed"))["duplicate"]
    error("reservation_closed", lambda: write(ledger, lambda: ledger.settle("job", "buyer", "seller", 200)))
    error("idempotency_conflict", lambda: write(ledger, lambda: ledger.release("job", "buyer", 200, "timeout")))
    assert ledger.budget("buyer")["available_minor"] == 1000
    assert ledger.reconcile()["conserved"]


def test_owner_policy_caps_initial_setup_and_reinvestment(ledger):
    assert write(ledger, lambda: ledger.seed_account("buyer", 1000, POLICY))["duplicate"]
    error("idempotency_conflict", lambda: write(ledger, lambda: ledger.seed_account("buyer", 1001, POLICY)))
    error("insufficient_budget", lambda: write(ledger, lambda: ledger.reserve("large", "buyer", 801)))
    write(ledger, lambda: ledger.reserve("job", "buyer", 700))
    error("insufficient_budget", lambda: write(ledger, lambda: ledger.reserve("second", "buyer", 101)))
    write(ledger, lambda: ledger.settle("job", "buyer", "seller", 700))
    error("reinvestment_limit", lambda: write(ledger, lambda: ledger.reinvest("seller", 333, "over-cap")))
    write(ledger, lambda: ledger.reinvest("seller", 332, "bounded"))
    assert write(ledger, lambda: ledger.reinvest("seller", 332, "bounded"))["duplicate"]
    error("idempotency_conflict", lambda: write(ledger, lambda: ledger.reinvest("seller", 1, "bounded")))
    assert ledger.reconcile()["conserved"]


def test_max_spend_is_cumulative_and_reserve_is_preserved(ledger):
    write(ledger, lambda: ledger.seed_account("bounded", 1000, {
        "max_spend_minor": 300, "max_exposure_minor": 1000, "reserve_minor": 100}))
    write(ledger, lambda: ledger.reserve("spent", "bounded", 300))
    write(ledger, lambda: ledger.settle("spent", "bounded", "seller", 300))
    assert ledger.budget("bounded")["available_minor"] == 700
    assert ledger.budget("bounded")["available_budget_minor"] == 0
    error("insufficient_budget", lambda: write(ledger, lambda: ledger.reserve("over", "bounded", 1)))
    write(ledger, lambda: ledger.seed_account("reserve", 1000, {
        "max_spend_minor": 2000, "max_exposure_minor": 2000, "reserve_minor": 900}))
    assert ledger.budget("reserve")["available_budget_minor"] == 100


def test_restart_replays_do_not_create_money(ledger):
    write(ledger, lambda: ledger.reserve("job", "buyer", 200))
    write(ledger, lambda: ledger.settle("job", "buyer", "seller", 200))
    path = ledger.conn.execute("PRAGMA database_list").fetchone()[2]
    other = sqlite3.connect(path)
    recovered = SimulationLedger(other)
    assert write(recovered, lambda: recovered.settle("job", "buyer", "seller", 200))["duplicate"]
    assert recovered.earnings("seller")["net_service_revenue_minor"] == 190
    assert recovered.reconcile()["conserved"]
    other.close()


def test_competing_process_connections_cannot_overreserve(ledger):
    path = ledger.conn.execute("PRAGMA database_list").fetchone()[2]

    def worker(job):
        conn = sqlite3.connect(path, timeout=10)
        item = SimulationLedger(conn)
        try:
            write(item, lambda: item.reserve(job, "buyer", 600))
            return "reserved"
        except LedgerError as exc:
            return exc.code
        finally:
            conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, ["concurrent-a", "concurrent-b"]))
    assert sorted(results) == ["insufficient_budget", "reserved"]
    assert ledger.budget("buyer")["held_minor"] == 600
    assert ledger.reconcile()["conserved"]


def test_reconciliation_detects_corrupted_journal(ledger):
    ledger.conn.execute("UPDATE vcx_capital_entries SET delta_minor=delta_minor+1 WHERE entry_id=1")
    ledger.conn.commit()
    report = ledger.reconcile()
    assert report["status"] == "error"
    assert not report["conserved"]
    assert "global_conservation_failed" in report["errors"]


def test_unknown_actors_and_self_dealing_fail_closed(ledger):
    error("unknown_account", lambda: ledger.budget("missing"))
    write(ledger, lambda: ledger.reserve("job", "buyer", 10))
    error("self_dealing", lambda: write(ledger, lambda: ledger.settle("job", "buyer", "buyer", 10)))
    assert ledger.budget("buyer")["held_minor"] == 10
