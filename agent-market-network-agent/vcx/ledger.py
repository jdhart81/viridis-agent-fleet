"""Simulation-only double-entry compute capital, inside caller transactions.

No method talks to a payment provider, imports a credential, commits, or converts
Fleet credits. Values are integer USD-style minor units of *simulation balances*.
The caller owns BEGIN IMMEDIATE/COMMIT/ROLLBACK for every mutation, allowing job
state and ledger postings to become durable in the same SQLite transaction.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

MAX_MINOR = 9_000_000_000_000_000
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/\-]{0,127}$")
_FUNDING = "__simulation_funding__"
_FEES = "__vcx_fees__"
_LABELS = {"balance_type": "simulation", "simulation_only": True,
           "redeemable": False, "currency": "USD",
           "actual_settled_funds_minor": 0, "service_credits": 0}


class LedgerError(ValueError):
    """A failed ledger requirement. The surrounding transaction must roll back."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _integer(value: Any, name: str, *, maximum: int = MAX_MINOR) -> int:
    if (not isinstance(value, int) or isinstance(value, bool)
            or not 0 <= value <= maximum):
        raise LedgerError("invalid_amount", f"{name} must be an integer in [0, {maximum}]")
    return value


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise LedgerError("invalid_identifier", f"invalid {name}")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class SimulationLedger:
    """Append-only financial journal with separately held and pending balances."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        # executescript() is intentionally avoided: it implicitly commits.
        for sql in (
            """CREATE TABLE IF NOT EXISTS vcx_capital_accounts (
                actor TEXT PRIMARY KEY, seed_minor INTEGER NOT NULL,
                policy_json TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS vcx_capital_operations (
                operation_key TEXT PRIMARY KEY, kind TEXT NOT NULL,
                terms_json TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS vcx_capital_entries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_key TEXT NOT NULL REFERENCES vcx_capital_operations(operation_key),
                actor TEXT NOT NULL, bucket TEXT NOT NULL, delta_minor INTEGER NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS vcx_capital_holds (
                job TEXT PRIMARY KEY, buyer TEXT NOT NULL, price_minor INTEGER NOT NULL,
                state TEXT NOT NULL, release_reason TEXT,
                seller TEXT, fee_minor INTEGER)""",
        ):
            self.conn.execute(sql)

    def _transaction(self) -> None:
        if not self.conn.in_transaction:
            raise LedgerError("transaction_required", "caller must begin a write transaction")

    def _account(self, actor: str) -> dict:
        _identifier(actor, "actor")
        row = self.conn.execute(
            "SELECT seed_minor,policy_json FROM vcx_capital_accounts WHERE actor=?",
            (actor,)).fetchone()
        if row is None:
            raise LedgerError("unknown_account", "actor has no owner-authorized simulation account")
        return {"actor": actor, "seed_minor": row[0], "policy": json.loads(row[1])}

    def _duplicate(self, key: str, kind: str, terms: dict) -> bool:
        row = self.conn.execute(
            "SELECT kind,terms_json FROM vcx_capital_operations WHERE operation_key=?",
            (key,)).fetchone()
        if row is None:
            return False
        if row[0] != kind or row[1] != _json(terms):
            raise LedgerError("idempotency_conflict", "operation key was already bound to different terms")
        return True

    def _post(self, key: str, kind: str, terms: dict, entries: list[tuple]) -> None:
        if sum(entry[2] for entry in entries) != 0:
            raise LedgerError("unbalanced_posting", "every operation must have zero net journal change")
        self.conn.execute("INSERT INTO vcx_capital_operations VALUES(?,?,?)",
                          (key, kind, _json(terms)))
        self.conn.executemany(
            "INSERT INTO vcx_capital_entries(operation_key,actor,bucket,delta_minor) VALUES(?,?,?,?)",
            [(key, actor, bucket, delta) for actor, bucket, delta in entries])

    def _balances(self, actor: str) -> dict:
        balances = {"available": 0, "held": 0, "pending_earnings": 0}
        for bucket, amount in self.conn.execute(
                "SELECT bucket,delta_minor FROM vcx_capital_entries WHERE actor=?", (actor,)):
            balances[bucket] = balances.get(bucket, 0) + amount
        return balances

    def _operations(self, kind: str) -> list[dict]:
        return [json.loads(row[0]) for row in self.conn.execute(
            "SELECT terms_json FROM vcx_capital_operations WHERE kind=?", (kind,))]

    @staticmethod
    def _policy(policy: Any, default_cap: int) -> dict:
        if policy is not None and not isinstance(policy, dict):
            raise LedgerError("invalid_policy", "policy must be an object")
        given = policy or {}
        if set(given) - {"max_spend_minor", "reserve_minor", "max_exposure_minor", "reinvest_bps"}:
            raise LedgerError("invalid_policy", "unknown policy field")
        cap = _integer(given.get("max_spend_minor", default_cap), "max_spend_minor")
        return {
            "max_spend_minor": cap,
            "reserve_minor": _integer(given.get("reserve_minor", 0), "reserve_minor"),
            "max_exposure_minor": _integer(given.get("max_exposure_minor", cap), "max_exposure_minor"),
            "reinvest_bps": _integer(given.get("reinvest_bps", 0), "reinvest_bps", maximum=10_000),
        }

    def update_policy(self, actor: str, policy: dict, change_id: str) -> dict:
        """Trusted owner control: replace the policy; audited, never a signed agent action.

        The spend cap cannot be set below what is already spent or held; use
        ``set_frozen`` to stop all new spending and reinvestment immediately.
        Held obligations are still honoured after either change.
        """
        self._transaction()
        account = self._account(actor)
        _identifier(change_id, "change_id")
        if not isinstance(policy, dict) or not policy:
            raise LedgerError("invalid_policy", "policy must be a non-empty object")
        normalized = self._policy(policy, account["policy"]["max_spend_minor"])
        if account["policy"].get("frozen"):
            normalized["frozen"] = True
        terms = {"actor": actor, "change_id": change_id, "policy": normalized}
        key = "policy:" + _json([actor, change_id])
        duplicate = self._duplicate(key, "policy", terms)
        if not duplicate:
            committed = self.earnings(actor)["spent_minor"] + self._balances(actor)["held"]
            if normalized["max_spend_minor"] < committed:
                raise LedgerError("invalid_policy", "spend cap cannot be below committed spending; freeze instead")
            self._post(key, "policy", terms, [])
            self.conn.execute("UPDATE vcx_capital_accounts SET policy_json=? WHERE actor=?",
                              (_json(normalized), actor))
        return {**self.budget(actor), "duplicate": duplicate}

    def set_frozen(self, actor: str, frozen: bool, change_id: str) -> dict:
        """Trusted owner kill switch: block or restore new holds and reinvestment."""
        self._transaction()
        account = self._account(actor)
        _identifier(change_id, "change_id")
        if type(frozen) is not bool:
            raise LedgerError("invalid_policy", "frozen must be a boolean")
        terms = {"actor": actor, "change_id": change_id, "frozen": frozen}
        key = "freeze:" + _json([actor, change_id])
        duplicate = self._duplicate(key, "freeze", terms)
        if not duplicate:
            policy = {k: v for k, v in account["policy"].items() if k != "frozen"}
            if frozen:
                policy["frozen"] = True
            self._post(key, "freeze", terms, [])
            self.conn.execute("UPDATE vcx_capital_accounts SET policy_json=? WHERE actor=?",
                              (_json(policy), actor))
        return {**self.budget(actor), "duplicate": duplicate}

    def seed_account(self, actor: str, amount_minor: int, policy: dict | None = None) -> dict:
        """Trusted local setup only; repeated setup cannot replenish balances.

        Absent policy, the owner cap equals initial funding and reinvestment is
        disabled. A seller initially funded at zero needs an explicit future
        spend cap and reinvestment policy before it can use its simulated earnings.
        """
        self._transaction()
        _identifier(actor, "actor")
        _integer(amount_minor, "amount_minor")
        normalized = self._policy(policy, amount_minor)
        terms = {"actor": actor, "amount_minor": amount_minor, "policy": normalized}
        key = "seed:" + actor
        duplicate = self._duplicate(key, "seed", terms)
        if not duplicate:
            self.conn.execute("INSERT INTO vcx_capital_accounts VALUES(?,?,?)",
                              (actor, amount_minor, _json(normalized)))
            self._post(key, "seed", terms, [(actor, "available", amount_minor),
                (_FUNDING, "external_simulated_funding", -amount_minor)])
        return {**self.budget(actor), "duplicate": duplicate}

    def reserve(self, job: str, buyer: str, price: int) -> dict:
        self._transaction()
        _identifier(job, "job")
        self._account(buyer)
        _integer(price, "price")
        if price == 0:
            raise LedgerError("invalid_amount", "price must be positive")
        terms = {"job": job, "buyer": buyer, "price_minor": price}
        key = "reserve:" + job
        duplicate = self._duplicate(key, "reserve", terms)
        if not duplicate:
            if price > self.budget(buyer)["available_budget_minor"]:
                raise LedgerError("insufficient_budget", "price exceeds available owner-authorized budget")
            self.conn.execute("INSERT INTO vcx_capital_holds(job,buyer,price_minor,state) VALUES(?,?,?,'HELD')",
                              (job, buyer, price))
            self._post(key, "reserve", terms,
                       [(buyer, "available", -price), (buyer, "held", price)])
        return {**_LABELS, **terms, "duplicate": duplicate, "reserved_minor": price}

    def _hold(self, job: str, buyer: str, price: int) -> tuple:
        _identifier(job, "job")
        self._account(buyer)
        _integer(price, "price")
        row = self.conn.execute(
            "SELECT buyer,price_minor,state FROM vcx_capital_holds WHERE job=?", (job,)).fetchone()
        if row is None:
            raise LedgerError("unknown_reservation", "job has no capital reservation")
        if row[0] != buyer or row[1] != price:
            raise LedgerError("reservation_conflict", "reservation terms do not match")
        if row[2] != "HELD":
            raise LedgerError("reservation_closed", "reservation already has a terminal financial outcome")
        return row

    def release(self, job: str, buyer: str, price: int, reason: str = "cancelled") -> dict:
        """Release a hold; this is simulation bookkeeping, not a Stripe refund."""
        self._transaction()
        _identifier(job, "job")
        self._account(buyer)
        _integer(price, "price")
        _identifier(reason, "reason")
        terms = {"job": job, "buyer": buyer, "price_minor": price, "reason": reason}
        key = "release:" + job
        duplicate = self._duplicate(key, "release", terms)
        if not duplicate:
            self._hold(job, buyer, price)
            self._post(key, "release", terms,
                       [(buyer, "held", -price), (buyer, "available", price)])
            self.conn.execute("UPDATE vcx_capital_holds SET state='RELEASED',release_reason=? WHERE job=?",
                              (reason, job))
        return {**_LABELS, **terms, "duplicate": duplicate, "released_minor": price,
                "external_refund_minor": 0}

    def settle(self, job: str, buyer: str, seller: str, price: int, fee_bps: int = 500) -> dict:
        self._transaction()
        _identifier(job, "job")
        self._account(buyer)
        self._account(seller)
        _integer(price, "price")
        _integer(fee_bps, "fee_bps", maximum=10_000)
        if buyer == seller:
            raise LedgerError("self_dealing", "buyer and seller must differ")
        fee = (price * fee_bps + 9_999) // 10_000
        terms = {"job": job, "buyer": buyer, "seller": seller, "price_minor": price,
                 "fee_bps": fee_bps, "fee_minor": fee, "seller_net_minor": price - fee}
        key = "settle:" + job
        duplicate = self._duplicate(key, "settle", terms)
        if not duplicate:
            self._hold(job, buyer, price)
            self._post(key, "settle", terms, [(buyer, "held", -price),
                (seller, "pending_earnings", price - fee), (_FEES, "marketplace_fees", fee)])
            self.conn.execute("UPDATE vcx_capital_holds SET state='SETTLED',seller=?,fee_minor=? WHERE job=?",
                              (seller, fee, job))
        return {**_LABELS, **terms, "duplicate": duplicate, "settlement_state": "SIMULATED_SETTLED"}

    def reinvest(self, actor: str, amount: int, request_id: str) -> dict:
        self._transaction()
        self._account(actor)
        _integer(amount, "amount")
        _identifier(request_id, "request_id")
        if amount == 0:
            raise LedgerError("invalid_amount", "amount must be positive")
        terms = {"actor": actor, "amount_minor": amount, "request_id": request_id}
        key = "reinvest:" + _json([actor, request_id])
        duplicate = self._duplicate(key, "reinvest", terms)
        if not duplicate:
            if amount > self.earnings(actor)["allowed_reinvestment_minor"]:
                raise LedgerError("reinvestment_limit", "amount exceeds pending earnings or owner policy")
            self._post(key, "reinvest", terms,
                       [(actor, "pending_earnings", -amount), (actor, "available", amount)])
        return {**_LABELS, **terms, "duplicate": duplicate, "budget": self.budget(actor)}

    def earnings(self, actor: str) -> dict:
        account = self._account(actor)
        settled = self._operations("settle")
        gross = sum(x["price_minor"] for x in settled if x["seller"] == actor)
        fees = sum(x["fee_minor"] for x in settled if x["seller"] == actor)
        spent = sum(x["price_minor"] for x in settled if x["buyer"] == actor)
        reinvested = sum(x["amount_minor"] for x in self._operations("reinvest") if x["actor"] == actor)
        pending = self._balances(actor)["pending_earnings"]
        policy_allowance = (gross - fees) * account["policy"]["reinvest_bps"] // 10_000
        allowed = max(0, min(pending, policy_allowance - reinvested))
        if account["policy"].get("frozen"):
            allowed = 0
        return {**_LABELS, "actor": actor, "gross_service_revenue_minor": gross,
                "marketplace_fees_paid_minor": fees, "net_service_revenue_minor": gross - fees,
                "spent_minor": spent, "realized_margin_minor": gross - fees - spent,
                "pending_earnings_minor": pending, "reinvested_minor": reinvested,
                "allowed_reinvestment_minor": allowed,
                "pending_earnings_kind": "simulation_proceeds", "actual_revenue_minor": 0}

    def budget(self, actor: str) -> dict:
        account = self._account(actor)
        balances = self._balances(actor)
        earned = self.earnings(actor)
        policy = account["policy"]
        available = max(0, min(balances["available"] - policy["reserve_minor"],
            policy["max_spend_minor"] - earned["spent_minor"] - balances["held"],
            policy["max_exposure_minor"] - balances["held"]))
        if policy.get("frozen"):
            available = 0
        return {**_LABELS, "actor": actor, "initial_simulation_funding_minor": account["seed_minor"],
                "available_minor": balances["available"], "available_budget_minor": available,
                "held_minor": balances["held"], "pending_earnings_minor": balances["pending_earnings"],
                "spent_minor": earned["spent_minor"],
                "allowed_reinvestment_minor": earned["allowed_reinvestment_minor"], "policy": policy}

    def reconcile(self) -> dict:
        """Read-only conservation and hold audit. Reports simulated flow only."""
        errors, totals, by_operation = [], {}, {}
        for key, bucket, delta in self.conn.execute(
                "SELECT operation_key,bucket,delta_minor FROM vcx_capital_entries"):
            totals[bucket] = totals.get(bucket, 0) + delta
            by_operation[key] = by_operation.get(key, 0) + delta
        for key, delta in by_operation.items():
            if delta != 0:
                errors.append("unbalanced_operation:" + key)
        for (actor,) in self.conn.execute("SELECT actor FROM vcx_capital_accounts"):
            balances = self._balances(actor)
            if any(balances[x] < 0 for x in ("available", "held", "pending_earnings")):
                errors.append("negative_balance:" + actor)
            expected = sum(row[0] for row in self.conn.execute(
                "SELECT price_minor FROM vcx_capital_holds WHERE buyer=? AND state='HELD'", (actor,)))
            if expected != balances["held"]:
                errors.append("reservation_mismatch:" + actor)
            if balances["held"] + self.earnings(actor)["spent_minor"] > self._account(actor)["policy"]["max_spend_minor"]:
                errors.append("spend_policy_exceeded:" + actor)
        net = sum(totals.values())
        if net != 0:
            errors.append("global_conservation_failed")
        return {**_LABELS, "status": "ok" if not errors else "error", "conserved": not errors,
                "errors": errors, "journal_net_minor": net,
                "available_minor": totals.get("available", 0), "held_minor": totals.get("held", 0),
                "pending_earnings_minor": totals.get("pending_earnings", 0),
                "marketplace_fees_minor": totals.get("marketplace_fees", 0),
                "external_simulated_funding_minor": -totals.get("external_simulated_funding", 0),
                "external_payment_settlement_minor": 0,
                "simulation_released_minor": sum(x["price_minor"] for x in self._operations("release")),
                "operations": len(by_operation)}
