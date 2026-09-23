import importlib.util
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "gateway_state_backup", HERE / "gateway_state_backup.py"
)
BACKUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKUP)


def _state_db(path: Path) -> Path:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE agent_state("
            "agent TEXT PRIMARY KEY, seq INTEGER, snapshot BLOB, "
            "sha256 TEXT, updated_at TEXT)"
        )
        conn.execute(
            "INSERT INTO agent_state VALUES(?,?,?,?,?)",
            ("smartscale", 1, b"marker", "abc", "2026-07-23T00:00:00Z"),
        )
        conn.commit()
    return path


def test_online_backup_and_restore_drill(tmp_path):
    source = _state_db(tmp_path / "state.db")
    manifest = BACKUP.backup_database(source, tmp_path / "backups")
    backup = Path(manifest["backup"])
    manifest_path = backup.with_suffix(".manifest.json")

    assert manifest["integrity_check"] == "ok"
    assert manifest["agent_state_rows"] == 1
    assert manifest["agents"] == ["smartscale"]
    assert manifest["off_droplet_copy_required"] is True

    scratch = tmp_path / "restore" / "state.db"
    drill = BACKUP.restore_drill(
        backup, scratch, manifest=manifest_path
    )
    assert drill["status"] == "pass"
    assert drill["integrity_check"] == "ok"
    assert drill["agents"] == ["smartscale"]


def test_restore_never_overwrites_existing_target(tmp_path):
    source = _state_db(tmp_path / "state.db")
    manifest = BACKUP.backup_database(source, tmp_path / "backups")
    scratch = tmp_path / "already-there.db"
    scratch.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        BACKUP.restore_drill(Path(manifest["backup"]), scratch)
    assert scratch.read_bytes() == b"keep me"


def test_manifest_digest_detects_tampering(tmp_path):
    source = _state_db(tmp_path / "state.db")
    manifest = BACKUP.backup_database(source, tmp_path / "backups")
    backup = Path(manifest["backup"])
    manifest_path = backup.with_suffix(".manifest.json")
    with backup.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="SHA-256"):
        BACKUP.verify_backup(backup, manifest_path)


def test_retention_removes_only_old_timestamped_backups(tmp_path):
    source = _state_db(tmp_path / "state.db")
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    manifest = BACKUP.backup_database(source, tmp_path, now=now)
    current = Path(manifest["backup"])
    old = tmp_path / "viridis_state-20260701T000000Z.db"
    old.write_bytes(current.read_bytes())
    old_manifest = old.with_suffix(".manifest.json")
    old_manifest.write_text("{}")
    old_time = (now - timedelta(days=20)).timestamp()
    os.utime(old, (old_time, old_time))

    BACKUP.prune_backups(tmp_path, retain_days=7, now=now)
    assert not old.exists()
    assert not old_manifest.exists()
    assert current.exists()
