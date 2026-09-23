import copy
import json
from pathlib import Path
import subprocess

import pytest

from deploy.droplet import regulatory_radar_growth_runtime_probe as probe


def inspect_payload(*, mode: str):
    candidate = mode == "candidate"
    env = [
        "GROWTH_AGENT_ENABLED=1",
        "GROWTH_AGENT_DRY_RUN=1",
        "GROWTH_OPENAI_ENABLED=0",
        "GROWTH_CAMPAIGN=",
        "GROWTH_CAMPAIGN_AUTHORIZATION=",
        f"GROWTH_AGENT_RUN_ONCE={'1' if candidate else '0'}",
    ]
    state_mount = {
        "Type": "bind" if candidate else "volume",
        "Name": "" if candidate else probe.LIVE_STATE_VOLUME,
        "Source": (
            "/root/viridis-candidates/radar-growth/state"
            if candidate
            else "/var/lib/docker/volumes/"
            f"{probe.LIVE_STATE_VOLUME}/_data"
        ),
        "Destination": "/state",
        "RW": True,
    }
    return {
        "Image": probe.EXPECTED_IMAGE,
        "State": {
            "Status": "exited" if candidate else "running",
            "ExitCode": 0 if candidate else None,
        },
        "Config": {"Env": env},
        "HostConfig": {
            "RestartPolicy": {
                "Name": "no" if candidate else "unless-stopped",
            },
        },
        "Mounts": [
            state_mount,
            {
                "Type": "bind",
                "Source": "/root/growth/secrets/key.pem",
                "Destination": "/run/secrets/key.pem",
                "RW": False,
            },
        ],
    }


def cycle():
    return {
        "status": "dry_run",
        "enabled": True,
        "campaign": None,
        "send_attempted": False,
        "model": {"mode": "deterministic", "reason": "dry_run_no_api"},
    }


@pytest.mark.parametrize("mode", ["candidate", "promotion"])
def test_accepts_exact_safe_runtime_contract(mode):
    result = probe.verify_runtime(
        inspect_payload(mode=mode),
        cycle(),
        mode=mode,
    )

    assert result["status"] == "ok"
    assert result["send_attempted"] is False
    assert result["model_called"] is False


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("GROWTH_AGENT_DRY_RUN", "0", "dry-run"),
        ("GROWTH_OPENAI_ENABLED", "1", "OpenAI"),
        ("GROWTH_CAMPAIGN", "regulatory_radar_repeat", "campaign"),
        (
            "GROWTH_CAMPAIGN_AUTHORIZATION",
            "authorize outbound: Regulatory Radar repeat purchase",
            "campaign authorization",
        ),
    ],
)
def test_rejects_unsafe_runtime_flags(name, value, message):
    captured = inspect_payload(mode="promotion")
    captured["Config"]["Env"] = [
        f"{name}={value}" if item.startswith(f"{name}=") else item
        for item in captured["Config"]["Env"]
    ]

    with pytest.raises(probe.RuntimeProbeFailure, match=message):
        probe.verify_runtime(captured, cycle(), mode="promotion")


def test_rejects_candidate_live_state_mount():
    captured = inspect_payload(mode="candidate")
    captured["Mounts"][0] = copy.deepcopy(
        inspect_payload(mode="promotion")["Mounts"][0]
    )

    with pytest.raises(probe.RuntimeProbeFailure, match="copied-state"):
        probe.verify_runtime(captured, cycle(), mode="candidate")


def test_rejects_send_or_model_cycle():
    bad_send = cycle()
    bad_send["send_attempted"] = True
    with pytest.raises(probe.RuntimeProbeFailure, match="outbound send"):
        probe.verify_runtime(
            inspect_payload(mode="promotion"),
            bad_send,
            mode="promotion",
        )

    bad_model = cycle()
    bad_model["model"] = {"mode": "openai", "reason": "generated"}
    with pytest.raises(probe.RuntimeProbeFailure, match="no-model"):
        probe.verify_runtime(
            inspect_payload(mode="promotion"),
            bad_model,
            mode="promotion",
        )


def test_rejects_writable_non_state_secret_mount():
    captured = inspect_payload(mode="promotion")
    captured["Mounts"][1]["RW"] = True

    with pytest.raises(probe.RuntimeProbeFailure, match="non-state"):
        probe.verify_runtime(captured, cycle(), mode="promotion")


def test_cli_accepts_streamed_inspect_without_writing_raw_runtime(tmp_path):
    cycle_path = tmp_path / "cycle.json"
    cycle_path.write_text(json.dumps(cycle()), encoding="utf-8")
    result = subprocess.run(
        [
            "python3",
            str(Path(probe.__file__)),
            "--inspect-json",
            "-",
            "--cycle-json",
            str(cycle_path),
            "--mode",
            "promotion",
        ],
        input=json.dumps([inspect_payload(mode="promotion")]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["status"] == "ok"
    assert list(tmp_path.iterdir()) == [cycle_path]


def test_cli_rejects_malformed_stream(tmp_path):
    cycle_path = tmp_path / "cycle.json"
    cycle_path.write_text(json.dumps(cycle()), encoding="utf-8")
    result = subprocess.run(
        [
            "python3",
            str(Path(probe.__file__)),
            "--inspect-json",
            "-",
            "--cycle-json",
            str(cycle_path),
            "--mode",
            "promotion",
        ],
        input="{not-json",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "error"
