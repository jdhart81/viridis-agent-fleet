#!/usr/bin/env python3
"""Verify the old-image rollback drill for the seat-bridge promotion.

All inputs are immutable evidence from an isolated, no-network copied-state
run.  This gate never opens or writes the live production database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


EXPECTED_ROWS = 35
EXPECTED_NORMALIZED_SOURCE_SHA256 = (
    "9638302328395f329314be04722907e1d0652a999dca5ff26d59c558b3b26b86"
)
EXPECTED_OLD_IMAGE_FINAL_SHA256 = (
    "939d5c25b9a992048e3169e96852d9f751035e3115736d45d10aebb17de72578"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RollbackGateFailure(RuntimeError):
    """The rollback drill cannot authorize the promotion transaction."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RollbackGateFailure(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_hash(path: Path, expected: str, label: str) -> None:
    require(path.is_file(), f"{label} is missing")
    require(_SHA256.fullmatch(expected) is not None, f"{label} pin is malformed")
    require(_sha256(path) == expected, f"{label} bytes do not match the pin")


def _read_object(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), f"{label} is not an object")
    return payload


def _source_digest(path: Path, label: str) -> str:
    parts = path.read_text(encoding="utf-8").strip().split()
    require(len(parts) == 2, f"{label} line is malformed")
    digest = parts[0]
    require(_SHA256.fullmatch(digest) is not None, f"{label} digest is malformed")
    return digest


def verify_rollback_drill(
    snapshot_compatibility: Path,
    loopback_health: Path,
    final_state: Path,
    source_before: Path,
    source_after: Path,
    *,
    snapshot_sha256: str,
    health_sha256: str,
    final_state_sha256: str,
    source_before_sha256: str,
    source_after_sha256: str,
) -> dict[str, Any]:
    for path, expected, label in (
        (snapshot_compatibility, snapshot_sha256, "snapshot evidence"),
        (loopback_health, health_sha256, "loopback evidence"),
        (final_state, final_state_sha256, "final-state evidence"),
        (source_before, source_before_sha256, "source-before evidence"),
        (source_after, source_after_sha256, "source-after evidence"),
    ):
        _require_hash(path, expected, label)

    snapshot = _read_object(snapshot_compatibility, "snapshot evidence")
    require(snapshot.get("status") == "ok", "old-image snapshot gate did not pass")
    require(snapshot.get("errors") == {}, "old-image snapshot errors are present")
    require(
        snapshot.get("adapter_load_errors") == {},
        "old-image adapter load errors are present",
    )
    rows = snapshot.get("rows")
    require(isinstance(rows, dict), "old-image snapshot rows are missing")
    require(
        len(rows) == EXPECTED_ROWS,
        f"expected {EXPECTED_ROWS} snapshot rows, found {len(rows)}",
    )
    security = rows.get("security-preflight", {})
    require(
        security.get("current_core_loaded") is True
        and security.get("attributes") == 2,
        "old image did not load normalized Security Preflight state",
    )

    health = _read_object(loopback_health, "loopback evidence")
    expected_health = {
        "status": "ok",
        "http_status": 503,
        "gateway_status": "degraded",
        "agent_count": 28,
        "degraded_agents": ["hive"],
        "security_preflight_version": "1.1.0",
        "payment_enabled": False,
    }
    require(health == expected_health, "old-image loopback health evidence changed")

    final = _read_object(final_state, "final-state evidence")
    require(final.get("integrity") == "ok", "old-image final SQLite integrity failed")
    require(
        final.get("rows") == EXPECTED_ROWS,
        "old-image final state-row count changed",
    )
    require(
        final.get("sha256") == EXPECTED_OLD_IMAGE_FINAL_SHA256,
        "old-image final database digest changed",
    )

    before_digest = _source_digest(source_before, "source-before evidence")
    after_digest = _source_digest(source_after, "source-after evidence")
    require(
        before_digest == EXPECTED_NORMALIZED_SOURCE_SHA256,
        "normalized source digest is unexpected",
    )
    require(
        after_digest == before_digest,
        "rollback drill mutated its immutable normalized source",
    )
    return {
        "status": "ok",
        "old_image_snapshot_compatible": True,
        "agent_state_rows": EXPECTED_ROWS,
        "security_preflight_attributes_loaded": 2,
        "loopback_agent_count": 28,
        "loopback_expected_degraded_agent": "hive",
        "payment_enabled": False,
        "normalized_source_unchanged": True,
        "old_image_clean_stop_integrity": "ok",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--health", type=Path, required=True)
    parser.add_argument("--final-state", type=Path, required=True)
    parser.add_argument("--source-before", type=Path, required=True)
    parser.add_argument("--source-after", type=Path, required=True)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--health-sha256", required=True)
    parser.add_argument("--final-state-sha256", required=True)
    parser.add_argument("--source-before-sha256", required=True)
    parser.add_argument("--source-after-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_rollback_drill(
            args.snapshot,
            args.health,
            args.final_state,
            args.source_before,
            args.source_after,
            snapshot_sha256=args.snapshot_sha256,
            health_sha256=args.health_sha256,
            final_state_sha256=args.final_state_sha256,
            source_before_sha256=args.source_before_sha256,
            source_after_sha256=args.source_after_sha256,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
