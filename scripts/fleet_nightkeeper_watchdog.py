#!/usr/bin/env python3
"""Record and verify the Fleet Nightkeeper's last successful run.

The status file contains operational evidence only. It intentionally excludes
tokens, customer data, request payloads, and production identifiers.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATUS = Path("runtime/fleet-nightkeeper-status.json")
SCHEMA = "viridis-fleet-nightkeeper-status-v1"


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_status(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError(f"unsupported Nightkeeper status schema in {path}")
    parse_time(str(data["last_success_at"]))
    return data


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def evaluate(
    status: dict[str, Any] | None, *, now: datetime, max_age_hours: float
) -> tuple[dict[str, Any], int]:
    if max_age_hours <= 0:
        raise ValueError("max age must be positive")

    deadline = timedelta(hours=max_age_hours)
    if status is None:
        return (
            {
                "status": "never_succeeded",
                "alert": True,
                "max_age_hours": max_age_hours,
                "checked_at": iso_z(now),
            },
            2,
        )

    last_success = parse_time(str(status["last_success_at"]))
    age = now - last_success
    if age.total_seconds() < 0:
        raise ValueError("last success is in the future")

    missed = age > deadline
    result = {
        "status": "missed" if missed else "ok",
        "alert": missed,
        "max_age_hours": max_age_hours,
        "checked_at": iso_z(now),
        "last_success_at": iso_z(last_success),
        "age_hours": round(age.total_seconds() / 3600, 6),
        "suite_count": status.get("suite_count"),
        "tests_passed": status.get("tests_passed"),
        "duration_seconds": status.get("duration_seconds"),
        "brief_path": status.get("brief_path"),
    }
    return result, 2 if missed else 0


def command_record(args: argparse.Namespace) -> int:
    finished_at = parse_time(args.finished_at) if args.finished_at else utc_now()
    if args.suite_count < 0 or args.tests_passed < 0 or args.duration_seconds < 0:
        raise ValueError("run metrics must be non-negative")
    status = {
        "schema": SCHEMA,
        "last_success_at": iso_z(finished_at),
        "suite_count": args.suite_count,
        "tests_passed": args.tests_passed,
        "duration_seconds": args.duration_seconds,
        "brief_path": args.brief_path,
    }
    atomic_write(args.status_file, status)
    print(json.dumps(status, sort_keys=True))
    return 0


def command_check(args: argparse.Namespace) -> int:
    now = parse_time(args.at) if args.at else utc_now()
    result, exit_code = evaluate(
        load_status(args.status_file), now=now, max_age_hours=args.max_age_hours
    )
    print(json.dumps(result, sort_keys=True))
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record-success")
    record.add_argument("--finished-at")
    record.add_argument("--suite-count", type=int, required=True)
    record.add_argument("--tests-passed", type=int, required=True)
    record.add_argument("--duration-seconds", type=float, required=True)
    record.add_argument("--brief-path", default="MORNING_BRIEF.md")
    record.set_defaults(handler=command_record)

    check = subparsers.add_parser("check")
    check.add_argument("--at")
    check.add_argument("--max-age-hours", type=float, default=26.0)
    check.set_defaults(handler=command_check)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.handler(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "invalid", "alert": True, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
