import hashlib
import pickle
import sqlite3
from datetime import datetime, timezone

import pytest

from scripts import retention_cohort_copied_state_probe as probe


def database(path, state, *, digest=None):
    raw = pickle.dumps(state)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE agent_state ("
        "agent TEXT PRIMARY KEY, seq INTEGER NOT NULL, snapshot BLOB NOT NULL, "
        "sha256 TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO agent_state VALUES (?, ?, ?, ?, ?)",
        (
            "agent",
            1,
            raw,
            digest or hashlib.sha256(raw).hexdigest(),
            "2026-07-31T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()


def test_copied_state_probe_returns_aggregates_without_payers(
        tmp_path, monkeypatch):
    state = {
        "_payment_gate_state": {
            "consumed_x402": {
                "first": {
                    "surface": "http-402-v2",
                    "classification_version": 1,
                    "payer_wallet": "0xNeverReturn",
                    "self_settle": False,
                    "timestamp": "2026-07-01T00:00:00Z",
                    "route": "radar/scan",
                },
                "repeat": {
                    "surface": "http-402-v2",
                    "classification_version": 1,
                    "payer_wallet": "0xNeverReturn",
                    "self_settle": False,
                    "timestamp": "2026-07-02T00:00:00Z",
                    "route": "radar/scan",
                },
            },
        },
    }
    path = tmp_path / "state.db"
    database(path, state)
    monkeypatch.setattr(probe, "PAID_AGENTS", frozenset({"agent"}))
    result = probe.probe(
        path, as_of=datetime(2026, 7, 31, tzinfo=timezone.utc)
    )
    assert result["retention_cohorts"]["payer_count"] == 1
    assert result["retention_cohorts"]["windows"]["7d"][
        "repeat_rate_bps"] == 10000
    assert "0xneverreturn" not in str(result).lower()
    assert result["payer_identifiers_returned"] is False
    assert result["production_mutated"] is False


def test_copied_state_probe_fails_on_snapshot_digest_drift(
        tmp_path, monkeypatch):
    path = tmp_path / "state.db"
    database(path, {}, digest="0" * 64)
    monkeypatch.setattr(probe, "PAID_AGENTS", frozenset({"agent"}))
    with pytest.raises(RuntimeError, match="digest mismatch"):
        probe.probe(
            path, as_of=datetime(2026, 7, 31, tzinfo=timezone.utc)
        )
