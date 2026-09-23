import copy
import hashlib
import json
from pathlib import Path
import subprocess

from deploy.droplet import gateway_runtime_parity_hardened_20260804 as parity


def _inspect() -> dict:
    return {
        "Name": "/viridis-fleet-gateway-1",
        "Image": "sha256:previous",
        "Path": "uvicorn",
        "Args": ["app:app"],
        "Config": {
            "User": "1000:1000",
            "WorkingDir": "/app",
            "Entrypoint": ["/entrypoint.sh"],
            "Cmd": ["uvicorn", "app:app"],
            "Env": ["X402_ENABLED=1", "SECRET=value"],
            "Labels": {
                "com.docker.compose.service": "gateway",
                "com.docker.compose.image": "sha256:previous",
            },
            "ExposedPorts": {"8402/tcp": {}},
            "Healthcheck": {"Test": ["CMD", "healthcheck"]},
            "StopSignal": "SIGTERM",
            "StopTimeout": 10,
            "Tty": False,
            "OpenStdin": False,
        },
        "HostConfig": {
            "NetworkMode": "viridis-fleet_default",
            "PortBindings": {"8402/tcp": [{"HostPort": "8402"}]},
            "RestartPolicy": {"Name": "unless-stopped"},
            "AutoRemove": False,
            "ReadonlyRootfs": False,
            "Privileged": False,
            "CapAdd": None,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "PidMode": "",
            "IpcMode": "private",
            "CgroupnsMode": "private",
            "Devices": [],
            "Memory": 0,
            "MemorySwap": 0,
            "NanoCpus": 0,
            "CpuShares": 0,
            "PidsLimit": None,
            "OomKillDisable": None,
            "LogConfig": {"Type": "json-file"},
            "Dns": [],
            "ExtraHosts": [],
        },
        "Mounts": [
            {
                "Type": "volume",
                "Source": "viridis_state",
                "Destination": "/data",
                "Mode": "rw",
                "RW": True,
                "Propagation": "",
            }
        ],
        "NetworkSettings": {
            "Networks": {
                "viridis-fleet_default": {
                    "Aliases": [
                        "gateway",
                        "a" * 64,
                        "viridis-fleet-gateway-1",
                    ],
                    "DriverOpts": None,
                    "Links": None,
                }
            }
        },
    }


def _snapshot(inspect: dict, image: str) -> dict:
    runtime = parity.canonical_runtime(inspect)
    encoded = json.dumps(
        runtime,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "schema": parity.SCHEMA,
        "container": "viridis-fleet-gateway-1",
        "image": image,
        "runtime": runtime,
        "runtime_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def test_runtime_redacts_environment_and_compose_image_label():
    runtime = parity.canonical_runtime(_inspect())
    serialized = json.dumps(runtime, sort_keys=True)
    assert "SECRET" in serialized
    assert "value" not in serialized
    assert "com.docker.compose.image" not in serialized
    assert runtime["config"]["env"]["SECRET"] == parity._digest("value")


def test_immutable_oci_image_labels_do_not_create_runtime_drift():
    before = _inspect()
    after = copy.deepcopy(before)
    after["Config"]["Labels"].update(
        {
            "org.opencontainers.image.title": "Viridis fleet",
            "org.opencontainers.image.version": "20260804",
            "org.opencontainers.image.description": "Eight paid routes",
        }
    )
    assert parity.canonical_runtime(before) == parity.canonical_runtime(after)


def test_dynamic_container_network_alias_is_ignored():
    runtime = parity.canonical_runtime(_inspect())
    aliases = runtime["networks"]["viridis-fleet_default"]["aliases"]
    assert "a" * 64 not in aliases
    assert aliases == ["gateway", "viridis-fleet-gateway-1"]


def test_mount_order_is_canonical():
    inspect = _inspect()
    second = copy.deepcopy(inspect["Mounts"][0])
    second["Destination"] = "/config"
    inspect["Mounts"].insert(0, second)
    assert [
        mount["destination"]
        for mount in parity.canonical_runtime(inspect)["mounts"]
    ] == ["/config", "/data"]


def test_unset_dns_null_and_empty_list_are_equivalent():
    empty = _inspect()
    unset = copy.deepcopy(empty)
    unset["HostConfig"]["Dns"] = None
    assert (
        parity.canonical_runtime(empty)["host_config"]
        == parity.canonical_runtime(unset)["host_config"]
    )


def test_compare_accepts_image_only_change(tmp_path):
    before_inspect = _inspect()
    after_inspect = copy.deepcopy(before_inspect)
    after_inspect["Image"] = "sha256:candidate"
    after_inspect["Config"]["Labels"]["com.docker.compose.image"] = (
        "sha256:candidate"
    )
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(
        json.dumps(_snapshot(before_inspect, "sha256:previous")),
        encoding="utf-8",
    )
    after.write_text(
        json.dumps(_snapshot(after_inspect, "sha256:candidate")),
        encoding="utf-8",
    )
    assert parity.compare(before, after)["status"] == "ok"


def test_compare_rejects_environment_drift_without_exposing_value(tmp_path):
    before_inspect = _inspect()
    after_inspect = copy.deepcopy(before_inspect)
    after_inspect["Config"]["Env"][-1] = "SECRET=new-secret"
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(
        json.dumps(_snapshot(before_inspect, "sha256:previous")),
        encoding="utf-8",
    )
    after.write_text(
        json.dumps(_snapshot(after_inspect, "sha256:candidate")),
        encoding="utf-8",
    )
    try:
        parity.compare(before, after)
    except ValueError as exc:
        assert "config" in str(exc)
        assert "new-secret" not in str(exc)
    else:
        raise AssertionError("environment drift was accepted")


def test_compare_rejects_mount_drift(tmp_path):
    before_inspect = _inspect()
    after_inspect = copy.deepcopy(before_inspect)
    after_inspect["Mounts"][0]["RW"] = False
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(
        json.dumps(_snapshot(before_inspect, "sha256:previous")),
        encoding="utf-8",
    )
    after.write_text(
        json.dumps(_snapshot(after_inspect, "sha256:candidate")),
        encoding="utf-8",
    )
    try:
        parity.compare(before, after)
    except ValueError as exc:
        assert "mounts" in str(exc)
    else:
        raise AssertionError("mount drift was accepted")


def test_compare_rejects_tampered_snapshot_digest(tmp_path):
    snapshot = _snapshot(_inspect(), "sha256:previous")
    snapshot["runtime"]["host_config"]["privileged"] = True
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    try:
        parity.compare(path, path)
    except ValueError as exc:
        assert "digest mismatch" in str(exc)
    else:
        raise AssertionError("tampered digest was accepted")


def test_streamed_capture_writes_only_redacted_snapshot(tmp_path, monkeypatch):
    inspect = _inspect()
    output = tmp_path / "snapshot.json"
    monkeypatch.setattr(
        "sys.stdin",
        __import__("io").StringIO(json.dumps([inspect])),
    )
    result = parity.capture_json(
        "-",
        "viridis-fleet-gateway-1",
        "sha256:previous",
        output,
    )
    serialized = output.read_text(encoding="utf-8")
    assert result["status"] == "ok"
    assert "SECRET" in serialized
    assert "value" not in serialized


def test_streamed_capture_rejects_wrong_image(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sys.stdin",
        __import__("io").StringIO(json.dumps([_inspect()])),
    )
    try:
        parity.capture_json(
            "-",
            "viridis-fleet-gateway-1",
            "sha256:not-current",
            tmp_path / "snapshot.json",
        )
    except ValueError as exc:
        assert "image does not match" in str(exc)
    else:
        raise AssertionError("wrong image was accepted")


def test_cli_returns_fleet_error_schema_for_parity_failure(tmp_path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(
        json.dumps(_snapshot(_inspect(), "sha256:previous")),
        encoding="utf-8",
    )
    changed = _inspect()
    changed["HostConfig"]["Privileged"] = True
    after.write_text(
        json.dumps(_snapshot(changed, "sha256:candidate")),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "python3",
            str(Path(parity.__file__)),
            "compare",
            "--before",
            str(before),
            "--after",
            str(after),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "RUNTIME_PARITY_FAILED"
