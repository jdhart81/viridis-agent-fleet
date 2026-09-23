#!/usr/bin/env python3
"""Fail-closed backup gate for Regulatory Radar growth promotion."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from deploy.droplet import growth_state_backup


class GrowthBackupGateFailure(RuntimeError):
    """The growth backup cannot authorize a production transaction."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GrowthBackupGateFailure(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_growth_promotion_backup(
    backup: Path,
    manifest_path: Path,
    expected_sha256: str,
    *,
    minimum_rows: int,
    minimum_max_seq: int,
    maximum_age_hours: float,
    expected_source: str = "/state/viridis_growth.sqlite3",
    now: datetime | None = None,
) -> dict[str, Any]:
    require(backup.is_file(), "retained growth backup is missing")
    require(manifest_path.is_file(), "growth backup manifest is missing")
    require(backup.stat().st_size > 0, "retained growth backup is empty")
    require(
        re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
        "expected growth backup SHA-256 is malformed",
    )
    require(minimum_rows >= 0, "minimum row count cannot be negative")
    require(minimum_max_seq >= 0, "minimum max sequence cannot be negative")
    require(maximum_age_hours > 0, "maximum age must be positive")
    require(expected_source.startswith("/"), "expected source must be absolute")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict), "growth backup manifest is not an object")
    require(
        manifest.get("schema_version") == "1.0",
        "growth backup manifest schema changed",
    )
    require(
        manifest.get("source") == expected_source,
        "growth backup source path changed",
    )
    require(
        manifest.get("sha256") == expected_sha256,
        "growth backup manifest digest does not match the promotion pin",
    )
    require(
        manifest.get("size_bytes") == backup.stat().st_size,
        "growth backup size does not match the manifest",
    )
    require(
        manifest.get("off_droplet_copy_required") is True,
        "growth backup manifest omits the off-droplet requirement",
    )

    created_raw = manifest.get("created_at")
    require(isinstance(created_raw, str), "growth backup creation time is missing")
    try:
        created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GrowthBackupGateFailure(
            "growth backup creation time is malformed"
        ) from exc
    require(
        created_at.tzinfo is not None,
        "growth backup creation time is not timezone-aware",
    )
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    created_at = created_at.astimezone(timezone.utc)
    age_seconds = (now - created_at).total_seconds()
    require(age_seconds >= 0, "growth backup creation time is in the future")
    require(
        age_seconds <= maximum_age_hours * 3600,
        "growth backup is older than the promotion freshness limit",
    )

    actual_sha256 = _sha256(backup)
    require(
        actual_sha256 == expected_sha256,
        "growth backup bytes do not match the promotion pin",
    )
    try:
        evidence = growth_state_backup.inspect_database(backup)
    except ValueError as exc:
        raise GrowthBackupGateFailure(str(exc)) from exc
    for key in (
        "integrity_check",
        "outbound_log_rows",
        "max_seq",
        "append_only_triggers",
        "duplicate_event_ids",
        "invalid_payload_rows",
    ):
        require(
            manifest.get(key) == evidence[key],
            f"growth backup evidence mismatch: {key}",
        )
    require(
        evidence["outbound_log_rows"] >= minimum_rows,
        "growth backup row count is below the promotion floor",
    )
    require(
        evidence["max_seq"] >= minimum_max_seq,
        "growth backup max sequence is below the promotion floor",
    )
    return {
        "status": "ok",
        "backup": str(backup),
        "manifest": str(manifest_path),
        "sha256": actual_sha256,
        "created_at": created_at.isoformat(),
        "age_seconds": round(age_seconds, 3),
        "maximum_age_hours": maximum_age_hours,
        **evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--minimum-rows", type=int, required=True)
    parser.add_argument("--minimum-max-seq", type=int, required=True)
    parser.add_argument("--maximum-age-hours", type=float, default=25.0)
    parser.add_argument(
        "--expected-source",
        default="/state/viridis_growth.sqlite3",
    )
    args = parser.parse_args()
    try:
        result = verify_growth_promotion_backup(
            args.backup,
            args.manifest,
            args.expected_sha256,
            minimum_rows=args.minimum_rows,
            minimum_max_seq=args.minimum_max_seq,
            maximum_age_hours=args.maximum_age_hours,
            expected_source=args.expected_source,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error": {
                "code": "GROWTH_BACKUP_GATE_FAILED",
                "message": str(exc),
            },
        }, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
