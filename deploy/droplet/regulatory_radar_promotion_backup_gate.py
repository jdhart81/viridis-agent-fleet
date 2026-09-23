#!/usr/bin/env python3
"""Fail-closed backup prerequisite for the Radar gateway promotion.

The gate is read-only. It independently checks the retained database, its
manifest, freshness, digest, SQLite integrity, and state-row floor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BackupGateFailure(RuntimeError):
    """The pinned backup cannot authorize a production transaction."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BackupGateFailure(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_promotion_backup(
    backup: Path,
    manifest_path: Path,
    expected_sha256: str,
    *,
    minimum_rows: int,
    maximum_age_hours: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    require(backup.is_file(), "retained backup is missing")
    require(manifest_path.is_file(), "backup manifest is missing")
    require(backup.stat().st_size > 0, "retained backup is empty")
    require(
        re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
        "expected backup SHA-256 is malformed",
    )
    require(minimum_rows >= 1, "minimum row count must be positive")
    require(maximum_age_hours > 0, "maximum age must be positive")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict), "backup manifest is not an object")
    require(
        manifest.get("schema_version") == "1.0",
        "backup manifest schema changed",
    )
    require(
        manifest.get("sha256") == expected_sha256,
        "backup manifest digest does not match the promotion pin",
    )
    require(
        manifest.get("size_bytes") == backup.stat().st_size,
        "backup size does not match the manifest",
    )
    require(
        manifest.get("integrity_check") == "ok",
        "backup manifest does not record integrity ok",
    )
    require(
        manifest.get("off_droplet_copy_required") is True,
        "backup manifest omits the off-droplet requirement",
    )
    require(
        int(manifest.get("agent_state_rows", -1)) >= minimum_rows,
        "backup manifest state-row count is below the promotion floor",
    )

    created_raw = manifest.get("created_at")
    require(isinstance(created_raw, str), "backup creation time is missing")
    try:
        created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BackupGateFailure("backup creation time is malformed") from exc
    require(
        created_at.tzinfo is not None,
        "backup creation time is not timezone-aware",
    )
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    created_at = created_at.astimezone(timezone.utc)
    age_seconds = (now - created_at).total_seconds()
    require(age_seconds >= 0, "backup creation time is in the future")
    require(
        age_seconds <= maximum_age_hours * 3600,
        "backup is older than the promotion freshness limit",
    )

    actual_sha256 = _sha256(backup)
    require(
        actual_sha256 == expected_sha256,
        "retained backup bytes do not match the promotion pin",
    )
    uri = f"{backup.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        require(integrity == "ok", "retained backup SQLite integrity failed")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        require("agent_state" in tables, "retained backup lacks agent_state")
        rows = connection.execute(
            "SELECT COUNT(*) FROM agent_state"
        ).fetchone()[0]
    require(rows >= minimum_rows, "retained backup state rows regressed")
    require(
        rows == manifest.get("agent_state_rows"),
        "retained backup state rows do not match the manifest",
    )
    return {
        "status": "ok",
        "backup": str(backup),
        "manifest": str(manifest_path),
        "sha256": actual_sha256,
        "integrity_check": "ok",
        "agent_state_rows": rows,
        "created_at": created_at.isoformat(),
        "age_seconds": round(age_seconds, 3),
        "maximum_age_hours": maximum_age_hours,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--minimum-rows", type=int, default=34)
    parser.add_argument("--maximum-age-hours", type=float, default=25.0)
    args = parser.parse_args()
    try:
        result = verify_promotion_backup(
            args.backup,
            args.manifest,
            args.expected_sha256,
            minimum_rows=args.minimum_rows,
            maximum_age_hours=args.maximum_age_hours,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
