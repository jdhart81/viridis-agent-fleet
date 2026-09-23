#!/usr/bin/env python3
"""Offline runtime-contract probe for the Regulatory Radar growth image.

The probe consumes captured Docker inspect JSON and one structured dry-run
cycle. It never connects to Docker, a network, a model, or a posting API.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_IMAGE = (
    "sha256:"
    "f1bd8e3d69b9606bf3d686a16bb9374d1090bc4031ed5e56795f41844f9b5985"
)
LIVE_STATE_VOLUME = "growth-agent_growth_state"
TRUTHY = frozenset({"1", "true", "yes", "on"})


class RuntimeProbeFailure(RuntimeError):
    """The captured growth runtime violates the release contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeProbeFailure(message)


def _env_map(inspect: dict[str, Any]) -> dict[str, str]:
    raw = inspect.get("Config", {}).get("Env", [])
    require(isinstance(raw, list), "container environment is not a list")
    result: dict[str, str] = {}
    for item in raw:
        require(isinstance(item, str), "container environment entry is invalid")
        name, separator, value = item.partition("=")
        require(separator == "=" and name, "container environment entry is malformed")
        result[name] = value
    return result


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in TRUTHY


def verify_runtime(
    inspect: dict[str, Any],
    cycle: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    require(mode in {"candidate", "promotion"}, "unsupported runtime mode")
    require(inspect.get("Image") == EXPECTED_IMAGE, "growth image is not exact")
    state = inspect.get("State", {})
    require(isinstance(state, dict), "container state is missing")
    if mode == "candidate":
        require(state.get("Status") == "exited", "candidate did not exit")
        require(state.get("ExitCode") == 0, "candidate exit code is not zero")
    else:
        require(state.get("Status") == "running", "promoted worker is not running")
        restart = inspect.get("HostConfig", {}).get("RestartPolicy", {})
        require(
            restart.get("Name") == "unless-stopped",
            "promoted worker restart policy changed",
        )

    env = _env_map(inspect)
    require(_enabled(env.get("GROWTH_AGENT_ENABLED")), "worker is not enabled")
    require(_enabled(env.get("GROWTH_AGENT_DRY_RUN")), "dry-run is not enabled")
    require(
        not _enabled(env.get("GROWTH_OPENAI_ENABLED")),
        "OpenAI must remain disabled",
    )
    require(
        not str(env.get("GROWTH_CAMPAIGN") or "").strip(),
        "campaign must remain empty",
    )
    require(
        not str(env.get("GROWTH_CAMPAIGN_AUTHORIZATION") or "").strip(),
        "campaign authorization must remain empty",
    )
    if mode == "candidate":
        require(
            _enabled(env.get("GROWTH_AGENT_RUN_ONCE")),
            "candidate must run exactly one cycle",
        )
    else:
        require(
            not _enabled(env.get("GROWTH_AGENT_RUN_ONCE")),
            "promoted worker must not inherit run-once mode",
        )

    mounts = inspect.get("Mounts")
    require(isinstance(mounts, list), "container mounts are not a list")
    state_mounts = [
        item for item in mounts
        if isinstance(item, dict) and item.get("Destination") == "/state"
    ]
    require(len(state_mounts) == 1, "expected exactly one state mount")
    state_mount = state_mounts[0]
    require(state_mount.get("RW") is True, "state mount is not writable")
    if mode == "candidate":
        require(
            state_mount.get("Type") == "bind",
            "candidate state must be a copied-state bind mount",
        )
        require(
            state_mount.get("Name") != LIVE_STATE_VOLUME
            and LIVE_STATE_VOLUME not in str(state_mount.get("Source") or ""),
            "candidate is attached to the live growth state",
        )
    else:
        require(
            state_mount.get("Type") == "volume"
            and state_mount.get("Name") == LIVE_STATE_VOLUME,
            "promoted worker is not attached to the exact live state volume",
        )
    for mount in mounts:
        if mount is state_mount:
            continue
        require(
            isinstance(mount, dict) and mount.get("RW") is False,
            "non-state mount is writable",
        )

    require(cycle.get("status") == "dry_run", "first cycle is not dry-run")
    require(cycle.get("enabled") is True, "first cycle was not enabled")
    require(
        cycle.get("send_attempted") is False,
        "first cycle attempted an outbound send",
    )
    require(
        cycle.get("model")
        == {"mode": "deterministic", "reason": "dry_run_no_api"},
        "first cycle did not prove no-model dry-run mode",
    )
    require(
        cycle.get("campaign") in (None, ""),
        "first cycle unexpectedly selected a campaign",
    )
    return {
        "status": "ok",
        "mode": mode,
        "image": EXPECTED_IMAGE,
        "container_status": state.get("Status"),
        "dry_run": True,
        "openai_enabled": False,
        "campaign": None,
        "campaign_authorization": None,
        "send_attempted": False,
        "model_called": False,
        "state_mount": (
            "copied_bind" if mode == "candidate" else LIVE_STATE_VOLUME
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inspect-json",
        required=True,
        help="Docker inspect JSON path, or - to read it from stdin",
    )
    parser.add_argument("--cycle-json", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("candidate", "promotion"),
        required=True,
    )
    args = parser.parse_args()
    try:
        if args.inspect_json == "-":
            inspect_payload = json.load(sys.stdin)
        else:
            inspect_payload = json.loads(
                Path(args.inspect_json).read_text(encoding="utf-8")
            )
        if isinstance(inspect_payload, list):
            require(
                len(inspect_payload) == 1,
                "inspect capture must contain exactly one container",
            )
            inspect_payload = inspect_payload[0]
        require(isinstance(inspect_payload, dict), "inspect capture is invalid")
        cycle = json.loads(args.cycle_json.read_text(encoding="utf-8"))
        require(isinstance(cycle, dict), "cycle capture is invalid")
        result = verify_runtime(inspect_payload, cycle, mode=args.mode)
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "mode": args.mode,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
