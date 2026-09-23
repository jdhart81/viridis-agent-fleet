#!/usr/bin/env python3
"""Hash a runtime filesystem tree for exact candidate/base parity checks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

RELEASE_EXCLUDES = {
    "Agent harvest /secrets/",
    "production-backups/2026-08-06/**/production-after-stage.json",
}


def _release_excluded(relative: str) -> bool:
    return (relative.startswith("Agent harvest /secrets/") or
            relative.startswith("production-backups/2026-08-06/") and
            relative.endswith("/production-after-stage.json"))


def build_manifest(root: Path, excluded: set[str]) -> dict:
    records: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in excluded or _release_excluded(relative):
            continue
        raw = path.read_bytes()
        records.append(
            {
                "path": relative,
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    encoded = json.dumps(
        records, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "status": "ok",
        "root": str(root),
        "excluded": sorted(excluded | RELEASE_EXCLUDES),
        "file_count": len(records),
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/fleet"))
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    print(
        json.dumps(
            build_manifest(args.root, set(args.exclude)), sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
