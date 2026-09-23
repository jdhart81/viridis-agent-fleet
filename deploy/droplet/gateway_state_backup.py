#!/usr/bin/env python3
"""Online backup and restore-drill utility for the Viridis gateway SQLite DB.

This utility is intentionally stdlib-only so it can run inside the existing
gateway image. It creates a consistent SQLite backup while the gateway is
running, verifies integrity, emits a SHA-256 manifest, and can restore into a
new scratch path without overwriting production state.

It does not claim the paid-service backup gate is closed by itself. A current
backup and manifest must also be copied off the droplet, and a restore drill
must be recorded.
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
from typing import Any, Dict

DEFAULT_SOURCE = Path(os.environ.get("STATE_DB", "/data/viridis_state.db"))
DEFAULT_BACKUP_DIR = Path("/data/backups")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_database(path: Path) -> Dict[str, Any]:
    """Return integrity and state-row evidence; raise on any failed check."""
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"database is missing or empty: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"SQLite integrity_check failed: {integrity}")
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "agent_state" not in tables:
            raise ValueError("required agent_state table is missing")
        state_rows = conn.execute(
            "SELECT COUNT(*) FROM agent_state"
        ).fetchone()[0]
        agents = [
            row[0] for row in conn.execute(
                "SELECT agent FROM agent_state ORDER BY agent LIMIT 100"
            )
        ]
    return {
        "integrity_check": "ok",
        "agent_state_rows": state_rows,
        "agents": agents,
    }


def backup_database(
    source: Path,
    destination_dir: Path,
    *,
    retain_days: int = 7,
    now: datetime | None = None,
) -> Dict[str, Any]:
    """Create and verify a consistent online backup plus evidence manifest."""
    source = source.resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    now = now or _utcnow()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    final = destination_dir / f"viridis_state-{stamp}.db"
    manifest_path = final.with_suffix(".manifest.json")

    with tempfile.NamedTemporaryFile(
        prefix=".viridis_state-", suffix=".db",
        dir=destination_dir, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with sqlite3.connect(str(source)) as src, sqlite3.connect(str(temporary)) as dst:
            src.backup(dst)
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
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    prune_backups(destination_dir, retain_days=retain_days, now=now)
    return manifest


def verify_backup(backup: Path, manifest: Path | None = None) -> Dict[str, Any]:
    """Verify database integrity and, when supplied, its manifest digest."""
    evidence = inspect_database(backup)
    actual_sha = _sha256(backup)
    if manifest is not None:
        recorded = json.loads(manifest.read_text())
        if recorded.get("sha256") != actual_sha:
            raise ValueError("backup SHA-256 does not match the manifest")
    return {"backup": str(backup), "sha256": actual_sha, **evidence}


def restore_drill(
    backup: Path,
    scratch: Path,
    *,
    manifest: Path | None = None,
) -> Dict[str, Any]:
    """Restore into a new scratch path and verify it; never overwrite a file."""
    if scratch.exists():
        raise FileExistsError(f"scratch restore target already exists: {scratch}")
    verify_backup(backup, manifest)
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
    """Remove only timestamped backup pairs older than the retention window."""
    if retain_days < 1:
        raise ValueError("retain_days must be at least 1")
    now = now or _utcnow()
    cutoff = now - timedelta(days=retain_days)
    for backup in directory.glob("viridis_state-????????T??????Z.db"):
        modified = datetime.fromtimestamp(
            backup.stat().st_mtime, timezone.utc
        )
        if modified >= cutoff:
            continue
        backup.unlink()
        backup.with_suffix(".manifest.json").unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    backup_cmd = sub.add_parser("backup")
    backup_cmd.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    backup_cmd.add_argument(
        "--destination-dir", type=Path, default=DEFAULT_BACKUP_DIR
    )
    backup_cmd.add_argument("--retain-days", type=int, default=7)

    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--backup", type=Path, required=True)
    verify_cmd.add_argument("--manifest", type=Path)

    restore_cmd = sub.add_parser("restore-drill")
    restore_cmd.add_argument("--backup", type=Path, required=True)
    restore_cmd.add_argument("--manifest", type=Path)
    restore_cmd.add_argument("--scratch", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "backup":
            result = backup_database(
                args.source, args.destination_dir,
                retain_days=args.retain_days,
            )
        elif args.command == "verify":
            result = verify_backup(args.backup, args.manifest)
        else:
            result = restore_drill(
                args.backup, args.scratch, manifest=args.manifest
            )
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }))
        return 1
    print(json.dumps({"status": "ok", **result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
