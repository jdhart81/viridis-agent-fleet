import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPT = Path(__file__).with_name("fleet_nightkeeper_watchdog.py")


def run_watchdog(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_never_succeeded_alerts(tmp_path: Path) -> None:
    result = run_watchdog(
        "--status-file",
        str(tmp_path / "status.json"),
        "check",
        "--at",
        "2026-07-30T12:00:00Z",
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "never_succeeded"


def test_fresh_success_is_ok(tmp_path: Path) -> None:
    status_file = tmp_path / "status.json"
    recorded = run_watchdog(
        "--status-file",
        str(status_file),
        "record-success",
        "--finished-at",
        "2026-07-30T10:00:00Z",
        "--suite-count",
        "35",
        "--tests-passed",
        "1943",
        "--duration-seconds",
        "42.5",
    )
    assert recorded.returncode == 0

    checked = run_watchdog(
        "--status-file",
        str(status_file),
        "check",
        "--at",
        "2026-07-31T11:59:59Z",
    )
    payload = json.loads(checked.stdout)
    assert checked.returncode == 0
    assert payload["status"] == "ok"
    assert payload["suite_count"] == 35
    assert payload["tests_passed"] == 1943


def test_deliberately_simulated_miss_alerts(tmp_path: Path) -> None:
    status_file = tmp_path / "status.json"
    recorded = run_watchdog(
        "--status-file",
        str(status_file),
        "record-success",
        "--finished-at",
        "2026-07-30T10:00:00Z",
        "--suite-count",
        "35",
        "--tests-passed",
        "1943",
        "--duration-seconds",
        "42.5",
    )
    assert recorded.returncode == 0

    checked = run_watchdog(
        "--status-file",
        str(status_file),
        "check",
        "--at",
        "2026-07-31T12:00:01Z",
    )
    payload = json.loads(checked.stdout)
    assert checked.returncode == 2
    assert payload["status"] == "missed"
    assert payload["alert"] is True
    assert payload["age_hours"] > 26


def test_exact_26_hour_boundary_is_not_missed(tmp_path: Path) -> None:
    status_file = tmp_path / "status.json"
    run_watchdog(
        "--status-file",
        str(status_file),
        "record-success",
        "--finished-at",
        "2026-07-30T10:00:00Z",
        "--suite-count",
        "0",
        "--tests-passed",
        "0",
        "--duration-seconds",
        "0",
    )
    checked = run_watchdog(
        "--status-file",
        str(status_file),
        "check",
        "--at",
        "2026-07-31T12:00:00Z",
    )
    assert checked.returncode == 0
    assert json.loads(checked.stdout)["status"] == "ok"


@pytest.mark.parametrize("value", ["0", "-1"])
def test_non_positive_age_limit_fails_closed(tmp_path: Path, value: str) -> None:
    checked = run_watchdog(
        "--status-file",
        str(tmp_path / "status.json"),
        "check",
        "--max-age-hours",
        value,
    )
    assert checked.returncode == 2
    assert json.loads(checked.stdout)["status"] == "invalid"


def test_future_success_fails_closed(tmp_path: Path) -> None:
    status_file = tmp_path / "status.json"
    future = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    run_watchdog(
        "--status-file",
        str(status_file),
        "record-success",
        "--finished-at",
        future,
        "--suite-count",
        "1",
        "--tests-passed",
        "1",
        "--duration-seconds",
        "1",
    )
    checked = run_watchdog("--status-file", str(status_file), "check")
    assert checked.returncode == 2
    assert json.loads(checked.stdout)["status"] == "invalid"
