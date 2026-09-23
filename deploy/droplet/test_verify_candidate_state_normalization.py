import hashlib
import pickle
import sqlite3

import pytest

from deploy.droplet.verify_candidate_state_normalization import (
    EXPECTED_ROWS,
    NormalizationFailure,
    verify_normalization,
)


def write_db(path, rows):
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE agent_state ("
        "agent TEXT PRIMARY KEY, seq INTEGER NOT NULL, "
        "snapshot BLOB NOT NULL, sha256 TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )
    for agent, seq, state, updated_at in rows:
        raw = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
        connection.execute(
            "INSERT INTO agent_state VALUES(?,?,?,?,?)",
            (
                agent,
                seq,
                raw,
                hashlib.sha256(raw).hexdigest(),
                updated_at,
            ),
        )
    connection.commit()
    connection.close()


def fixture_rows(*, normalized):
    rows = []
    for index in range(EXPECTED_ROWS - 2):
        rows.append(
            (
                f"agent-{index:02d}",
                1,
                {"value": index},
                "2026-07-27T00:00:00+00:00",
            )
        )
    rows.extend(
        [
            (
                "metering",
                647 if normalized else 646,
                {"_meters": {"m": 1}, "_seq": 7},
                (
                    "2026-07-28T00:00:00+00:00"
                    if normalized
                    else "2026-07-27T00:00:00+00:00"
                ),
            ),
            (
                "security-preflight",
                3 if normalized else 2,
                (
                    {
                        "_payment_gate_state": {},
                        "_receipts": [],
                    }
                    if normalized
                    else {
                        "_payment_gate_state": {},
                        "_receipt_db_path": (
                            "/data/security_preflight_receipts.sqlite3"
                        ),
                        "_receipts": [],
                    }
                ),
                (
                    "2026-07-28T00:00:00+00:00"
                    if normalized
                    else "2026-07-27T00:00:00+00:00"
                ),
            ),
        ]
    )
    return rows


def test_accepts_exact_two_row_semantic_normalization(tmp_path):
    before = tmp_path / "before.db"
    after = tmp_path / "after.db"
    write_db(before, fixture_rows(normalized=False))
    write_db(after, fixture_rows(normalized=True))
    result = verify_normalization(
        before,
        after,
        module_contexts={"metering": {}, "security-preflight": {}},
    )
    assert result["status"] == "ok"
    assert result["changed_rows"] == ["metering", "security-preflight"]
    assert result["receipt_database_created"] is False


def test_refuses_any_third_changed_row(tmp_path):
    before = tmp_path / "before.db"
    after = tmp_path / "after.db"
    old = fixture_rows(normalized=False)
    new = fixture_rows(normalized=True)
    agent, seq, _, _ = new[0]
    new[0] = (agent, seq + 1, {"value": "changed"}, "2026-07-28T00:00:00Z")
    write_db(before, old)
    write_db(after, new)
    with pytest.raises(NormalizationFailure, match="unexpected changed rows"):
        verify_normalization(
            before,
            after,
            module_contexts={"metering": {}, "security-preflight": {}},
        )


def test_refuses_persistent_security_receipt_database(tmp_path):
    before = tmp_path / "before.db"
    after = tmp_path / "after.db"
    write_db(before, fixture_rows(normalized=False))
    write_db(after, fixture_rows(normalized=True))
    (tmp_path / "security_preflight_receipts.sqlite3").write_bytes(b"")
    with pytest.raises(NormalizationFailure, match="persistent"):
        verify_normalization(
            before,
            after,
            module_contexts={"metering": {}, "security-preflight": {}},
        )
