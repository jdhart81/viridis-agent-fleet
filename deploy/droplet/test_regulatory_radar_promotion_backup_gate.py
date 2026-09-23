import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from deploy.droplet import regulatory_radar_promotion_backup_gate as gate


NOW = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)


def make_backup(tmp_path: Path, *, created_at: datetime = NOW):
    backup = tmp_path / "viridis_state.db"
    with sqlite3.connect(backup) as connection:
        connection.execute(
            "CREATE TABLE agent_state("
            "agent TEXT PRIMARY KEY, seq INTEGER, snapshot BLOB, "
            "sha256 TEXT, updated_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO agent_state VALUES(?,?,?,?,?)",
            [
                (f"agent-{index}", 1, b"state", "abc", "2026-07-27")
                for index in range(34)
            ],
        )
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    manifest = tmp_path / "viridis_state.manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "1.0",
        "created_at": created_at.isoformat(),
        "backup": "/data/backups/viridis_state.db",
        "sha256": digest,
        "size_bytes": backup.stat().st_size,
        "integrity_check": "ok",
        "agent_state_rows": 34,
        "off_droplet_copy_required": True,
    }), encoding="utf-8")
    return backup, manifest, digest


def verify(backup, manifest, digest, *, now=NOW):
    return gate.verify_promotion_backup(
        backup,
        manifest,
        digest,
        minimum_rows=34,
        maximum_age_hours=25,
        now=now,
    )


def test_accepts_fresh_exact_integrity_checked_backup(tmp_path):
    backup, manifest, digest = make_backup(tmp_path)

    result = verify(backup, manifest, digest, now=NOW + timedelta(hours=1))

    assert result["status"] == "ok"
    assert result["agent_state_rows"] == 34
    assert result["integrity_check"] == "ok"


def test_rejects_backup_older_than_freshness_limit(tmp_path):
    backup, manifest, digest = make_backup(
        tmp_path,
        created_at=NOW - timedelta(hours=26),
    )

    with pytest.raises(gate.BackupGateFailure, match="older"):
        verify(backup, manifest, digest)


def test_rejects_tampered_backup_bytes(tmp_path):
    backup, manifest, digest = make_backup(tmp_path)
    with backup.open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(gate.BackupGateFailure, match="size"):
        verify(backup, manifest, digest)


def test_rejects_manifest_without_off_droplet_requirement(tmp_path):
    backup, manifest, digest = make_backup(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["off_droplet_copy_required"] = False
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(gate.BackupGateFailure, match="off-droplet"):
        verify(backup, manifest, digest)


def test_rejects_state_row_regression(tmp_path):
    backup, manifest, digest = make_backup(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["agent_state_rows"] = 33
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(gate.BackupGateFailure, match="row count"):
        verify(backup, manifest, digest)
