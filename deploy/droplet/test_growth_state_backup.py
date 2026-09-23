import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from deploy.droplet import growth_state_backup as backup


def state_database(path: Path, *, rows: int = 2) -> Path:
    with sqlite3.connect(path) as connection:
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
                    "public copy",
                    "2026-07-27T00:00:00+00:00",
                    json.dumps({"success": True}),
                )
                for index in range(rows)
            ],
        )
    return path


def test_online_backup_and_restore_preserve_audit_contract(tmp_path):
    source = state_database(tmp_path / "growth.db")
    manifest = backup.backup_database(source, tmp_path / "backups")
    backup_path = Path(manifest["backup"])
    manifest_path = backup_path.with_suffix(".manifest.json")

    assert manifest["integrity_check"] == "ok"
    assert manifest["outbound_log_rows"] == 2
    assert manifest["max_seq"] == 2
    assert manifest["append_only_triggers"] == list(
        backup.EXPECTED_TRIGGERS
    )
    verified = backup.verify_backup(backup_path, manifest_path)
    assert verified["sha256"] == manifest["sha256"]

    restored = backup.restore_drill(
        backup_path,
        tmp_path / "restore" / "growth.db",
        manifest_path=manifest_path,
    )
    assert restored["status"] == "pass"
    assert restored["outbound_log_rows"] == 2


def test_manifest_digest_detects_tampered_backup(tmp_path):
    source = state_database(tmp_path / "growth.db")
    manifest = backup.backup_database(source, tmp_path / "backups")
    backup_path = Path(manifest["backup"])
    manifest_path = backup_path.with_suffix(".manifest.json")
    with backup_path.open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(ValueError, match="SHA-256"):
        backup.verify_backup(backup_path, manifest_path)


def test_missing_append_only_trigger_is_rejected(tmp_path):
    source = state_database(tmp_path / "growth.db")
    with sqlite3.connect(source) as connection:
        connection.execute("DROP TRIGGER outbound_log_no_delete")

    with pytest.raises(ValueError, match="trigger set"):
        backup.inspect_database(source)


def test_manifest_cannot_lie_about_row_continuity(tmp_path):
    source = state_database(tmp_path / "growth.db", rows=3)
    manifest = backup.backup_database(source, tmp_path / "backups")
    backup_path = Path(manifest["backup"])
    manifest_path = backup_path.with_suffix(".manifest.json")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["outbound_log_rows"] = 2
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="outbound_log_rows"):
        backup.verify_backup(backup_path, manifest_path)


def test_restore_drill_never_overwrites_existing_state(tmp_path):
    source = state_database(tmp_path / "growth.db")
    manifest = backup.backup_database(source, tmp_path / "backups")
    destination = tmp_path / "keep.db"
    destination.write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        backup.restore_drill(Path(manifest["backup"]), destination)
    assert destination.read_bytes() == b"keep"


def test_retention_removes_only_old_named_backup_pairs(tmp_path):
    source = state_database(tmp_path / "growth.db")
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    manifest = backup.backup_database(source, tmp_path, now=now)
    current = Path(manifest["backup"])
    old = tmp_path / "viridis_growth-20260701T000000Z.db"
    old.write_bytes(current.read_bytes())
    old_manifest = old.with_suffix(".manifest.json")
    old_manifest.write_text("{}", encoding="utf-8")
    old_time = (now - timedelta(days=20)).timestamp()
    os.utime(old, (old_time, old_time))

    backup.prune_backups(tmp_path, retain_days=7, now=now)

    assert not old.exists()
    assert not old_manifest.exists()
    assert current.exists()
