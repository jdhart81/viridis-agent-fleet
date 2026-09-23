#!/usr/bin/env python3
"""Online backup and restore verifier for the growth append-only audit.

The utility is stdlib-only and never overwrites production state. It proves
SQLite integrity, the outbound-log schema, both append-only triggers, row
continuity, and a byte digest before a backup can authorize a candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


EXPECTED_COLUMNS = (
    "seq",
    "event_id",
    "event_type",
    "attempt_id",
    "target_id",
    "channel",
    "content",
    "occurred_at",
    "payload_json",
)
EXPECTED_TRIGGERS = (
    "outbound_log_no_delete",
    "outbound_log_no_update",
)
DEFAULT_SOURCE = Path("/state/viridis_growth.sqlite3")
DEFAULT_BACKUP_DIR = Path("/state/backups")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_database(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"growth database is missing or empty: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"SQLite integrity_check failed: {integrity}")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "outbound_log" not in tables:
            raise ValueError("required outbound_log table is missing")
        columns = tuple(
            row[1] for row in connection.execute(
                "PRAGMA table_info(outbound_log)"
            )
        )
        if columns != EXPECTED_COLUMNS:
            raise ValueError("outbound_log schema changed")
        trigger_rows = {
            row[0]: str(row[1] or "")
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' AND tbl_name='outbound_log'"
            )
        }
        if set(trigger_rows) != set(EXPECTED_TRIGGERS):
            raise ValueError("append-only trigger set changed")
        for name, sql in trigger_rows.items():
            normalized = " ".join(sql.lower().split())
            if "raise(abort" not in normalized:
                raise ValueError(f"{name} is not fail-closed")
        rows, max_seq = connection.execute(
            "SELECT COUNT(*), COALESCE(MAX(seq), 0) FROM outbound_log"
        ).fetchone()
        duplicate_events = connection.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT event_id FROM outbound_log "
            "GROUP BY event_id HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        invalid_payloads = 0
        for (payload,) in connection.execute(
            "SELECT payload_json FROM outbound_log"
        ):
            try:
                value = json.loads(payload)
            except (TypeError, ValueError):
                invalid_payloads += 1
                continue
            if not isinstance(value, dict):
                invalid_payloads += 1
    if duplicate_events:
        raise ValueError("outbound_log contains duplicate event ids")
    if invalid_payloads:
        raise ValueError("outbound_log contains invalid payload JSON")
    return {
        "integrity_check": "ok",
        "outbound_log_rows": rows,
        "max_seq": max_seq,
        "append_only_triggers": list(EXPECTED_TRIGGERS),
        "duplicate_event_ids": 0,
        "invalid_payload_rows": 0,
    }


def backup_database(
    source: Path,
    destination_dir: Path,
    *,
    retain_days: int = 7,
    now: datetime | None = None,
) -> dict[str, Any]:
    source = source.resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    now = now or _utcnow()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    final = destination_dir / f"viridis_growth-{stamp}.db"
    manifest_path = final.with_suffix(".manifest.json")

    with tempfile.NamedTemporaryFile(
        prefix=".viridis_growth-",
        suffix=".db",
        dir=destination_dir,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with (
            sqlite3.connect(str(source)) as source_connection,
            sqlite3.connect(str(temporary)) as backup_connection,
        ):
            source_connection.backup(backup_connection)
        evidence = inspect_database(temporary)
        os.replace(temporary, final)
    finally:
        temporary.unlink(missing_ok=True)

    manifest = {
        "schema_version": "1.0",
        "created_at": now.isoformat(),
        "source": str(source),
        "backup": str(final),
        "sha256": _sha256(final),
        "size_bytes": final.stat().st_size,
        **evidence,
        "off_droplet_copy_required": True,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prune_backups(destination_dir, retain_days=retain_days, now=now)
    return manifest


def verify_backup(
    backup: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    evidence = inspect_database(backup)
    actual_sha256 = _sha256(backup)
    if manifest_path is not None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("sha256") != actual_sha256:
            raise ValueError("backup SHA-256 does not match the manifest")
        if manifest.get("size_bytes") != backup.stat().st_size:
            raise ValueError("backup size does not match the manifest")
        for key in (
            "integrity_check",
            "outbound_log_rows",
            "max_seq",
            "append_only_triggers",
            "duplicate_event_ids",
            "invalid_payload_rows",
        ):
            if manifest.get(key) != evidence[key]:
                raise ValueError(f"backup evidence mismatch: {key}")
        if manifest.get("off_droplet_copy_required") is not True:
            raise ValueError("manifest omits the off-droplet requirement")
    return {
        "backup": str(backup),
        "sha256": actual_sha256,
        **evidence,
    }


def restore_drill(
    backup: Path,
    scratch: Path,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    if scratch.exists():
        raise FileExistsError(
            f"scratch restore target already exists: {scratch}"
        )
    verify_backup(backup, manifest_path)
    scratch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, scratch)
    evidence = inspect_database(scratch)
    return {
        "status": "pass",
        "restored_at": _utcnow().isoformat(),
        "source_backup": str(backup),
        "scratch_database": str(scratch),
        **evidence,
    }


def prune_backups(
    directory: Path,
    *,
    retain_days: int,
    now: datetime | None = None,
) -> None:
    if retain_days < 1:
        raise ValueError("retain_days must be at least 1")
    now = now or _utcnow()
    cutoff = now - timedelta(days=retain_days)
    for backup in directory.glob("viridis_growth-????????T??????Z.db"):
        modified = datetime.fromtimestamp(
            backup.stat().st_mtime,
            timezone.utc,
        )
        if modified >= cutoff:
            continue
        backup.unlink()
        backup.with_suffix(".manifest.json").unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    backup_command = commands.add_parser("backup")
    backup_command.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
    )
    backup_command.add_argument(
        "--destination-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
    )
    backup_command.add_argument("--retain-days", type=int, default=7)

    verify_command = commands.add_parser("verify")
    verify_command.add_argument("--backup", type=Path, required=True)
    verify_command.add_argument("--manifest", type=Path)

    restore_command = commands.add_parser("restore-drill")
    restore_command.add_argument("--backup", type=Path, required=True)
    restore_command.add_argument("--manifest", type=Path)
    restore_command.add_argument("--scratch", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "backup":
            result = backup_database(
                args.source,
                args.destination_dir,
                retain_days=args.retain_days,
            )
        elif args.command == "verify":
            result = verify_backup(args.backup, args.manifest)
        else:
            result = restore_drill(
                args.backup,
                args.scratch,
                manifest_path=args.manifest,
            )
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, sort_keys=True))
        return 1
    print(json.dumps({"status": "ok", **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
