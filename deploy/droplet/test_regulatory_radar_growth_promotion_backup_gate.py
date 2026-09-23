from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from deploy.droplet import growth_state_backup
from deploy.droplet import regulatory_radar_growth_promotion_backup_gate as gate


NOW = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)


def _backup(tmp_path: Path, *, created_at: datetime = NOW, rows: int = 3):
    source = tmp_path / "viridis_growth.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.executescript("""
        CREATE TABLE outbound_log (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            event_type TEXT NOT NULL,
            attempt_id TEXT,
            target_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            content TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TRIGGER outbound_log_no_update
        BEFORE UPDATE ON outbound_log BEGIN
            SELECT RAISE(ABORT, 'outbound_log is append-only');
        END;
        CREATE TRIGGER outbound_log_no_delete
        BEFORE DELETE ON outbound_log BEGIN
            SELECT RAISE(ABORT, 'outbound_log is append-only');
        END;
        """)
        connection.executemany(
            "INSERT INTO outbound_log("
            "event_id,event_type,attempt_id,target_id,channel,content,"
            "occurred_at,payload_json) VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    f"event-{index}",
                    "send_result",
                    f"attempt-{index}",
                    "owned-target",
                    "owned-channel",
                    "content",
                    NOW.isoformat(),
                    json.dumps({"success": True}),
                )
                for index in range(rows)
            ],
        )
    manifest = growth_state_backup.backup_database(
        source,
        tmp_path / "backups",
        now=created_at,
    )
    backup = Path(manifest["backup"])
    manifest_path = backup.with_suffix(".manifest.json")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["source"] = "/state/viridis_growth.sqlite3"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return backup, manifest_path, manifest["sha256"]


def _verify(backup, manifest, digest, *, now=NOW):
    return gate.verify_growth_promotion_backup(
        backup,
        manifest,
        digest,
        minimum_rows=3,
        minimum_max_seq=3,
        maximum_age_hours=25,
        now=now,
    )


def test_accepts_fresh_exact_growth_backup(tmp_path):
    backup, manifest, digest = _backup(tmp_path)
    result = _verify(
        backup,
        manifest,
        digest,
        now=NOW + timedelta(hours=1),
    )
    assert result["status"] == "ok"
    assert result["outbound_log_rows"] == 3
    assert result["max_seq"] == 3


@pytest.mark.parametrize(
    ("created_at", "message"),
    [
        (NOW - timedelta(hours=26), "older"),
        (NOW + timedelta(minutes=1), "future"),
    ],
)
def test_rejects_stale_or_future_backup(tmp_path, created_at, message):
    backup, manifest, digest = _backup(tmp_path, created_at=created_at)
    with pytest.raises(gate.GrowthBackupGateFailure, match=message):
        _verify(backup, manifest, digest)


def test_rejects_tampered_backup_bytes(tmp_path):
    backup, manifest, digest = _backup(tmp_path)
    with backup.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(gate.GrowthBackupGateFailure, match="size"):
        _verify(backup, manifest, digest)


def test_rejects_source_or_offsite_contract_drift(tmp_path):
    backup, manifest, digest = _backup(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["source"] = "/tmp/not-production.db"
    payload["off_droplet_copy_required"] = False
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(gate.GrowthBackupGateFailure, match="source"):
        _verify(backup, manifest, digest)


def test_rejects_row_or_sequence_regression(tmp_path):
    backup, manifest, digest = _backup(tmp_path, rows=2)
    with pytest.raises(gate.GrowthBackupGateFailure, match="row count"):
        _verify(backup, manifest, digest)


def test_rejects_missing_append_only_trigger(tmp_path):
    backup, manifest, digest = _backup(tmp_path)
    with sqlite3.connect(backup) as connection:
        connection.execute("DROP TRIGGER outbound_log_no_delete")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["sha256"] = gate._sha256(backup)
    payload["size_bytes"] = backup.stat().st_size
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(gate.GrowthBackupGateFailure, match="trigger set"):
        gate.verify_growth_promotion_backup(
            backup,
            manifest,
            payload["sha256"],
            minimum_rows=3,
            minimum_max_seq=3,
            maximum_age_hours=25,
            now=NOW,
        )
