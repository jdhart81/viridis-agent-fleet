#!/usr/bin/env python3
"""Capture and compare redacted Docker gateway runtime configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


SCHEMA = "viridis-gateway-runtime-parity-v1"
_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _redacted_env(entries: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in entries or []:
        name, separator, value = entry.partition("=")
        if not name or name in result:
            raise ValueError("environment names must be nonempty and unique")
        result[name] = _digest(value if separator else None)
    return dict(sorted(result.items()))


def _redacted_labels(labels: dict[str, str] | None) -> dict[str, str]:
    result = {}
    for name, value in (labels or {}).items():
        if (
            name == "com.docker.compose.image"
            or name.startswith("org.opencontainers.image.")
        ):
            continue
        result[name] = _digest(value)
    return dict(sorted(result.items()))


def _mounts(entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    selected = []
    for mount in entries or []:
        selected.append(
            {
                "type": mount.get("Type"),
                "source": mount.get("Source"),
                "destination": mount.get("Destination"),
                "mode": mount.get("Mode"),
                "rw": mount.get("RW"),
                "propagation": mount.get("Propagation"),
            }
        )
    return sorted(
        selected,
        key=lambda item: (
            str(item["destination"]),
            str(item["source"]),
            str(item["type"]),
        ),
    )


def _networks(entries: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    result = {}
    for name, network in sorted((entries or {}).items()):
        aliases = [
            alias
            for alias in (network.get("Aliases") or [])
            if not _CONTAINER_ID.fullmatch(alias or "")
        ]
        result[name] = {
            "aliases": sorted(aliases),
            "driver_opts": network.get("DriverOpts"),
            "links": sorted(network.get("Links") or []),
        }
    return result


def canonical_runtime(inspect: dict[str, Any]) -> dict[str, Any]:
    config = inspect.get("Config") or {}
    host = inspect.get("HostConfig") or {}
    network_settings = inspect.get("NetworkSettings") or {}
    healthcheck = config.get("Healthcheck")
    return {
        "name": inspect.get("Name"),
        "path": inspect.get("Path"),
        "args": inspect.get("Args"),
        "config": {
            "user": config.get("User"),
            "working_dir": config.get("WorkingDir"),
            "entrypoint": config.get("Entrypoint"),
            "cmd": config.get("Cmd"),
            "env": _redacted_env(config.get("Env")),
            "labels": _redacted_labels(config.get("Labels")),
            "exposed_ports": config.get("ExposedPorts"),
            "healthcheck": healthcheck,
            "stop_signal": config.get("StopSignal"),
            "stop_timeout": config.get("StopTimeout"),
            "tty": config.get("Tty"),
            "open_stdin": config.get("OpenStdin"),
        },
        "host_config": {
            "network_mode": host.get("NetworkMode"),
            "port_bindings": host.get("PortBindings"),
            "restart_policy": host.get("RestartPolicy"),
            "auto_remove": host.get("AutoRemove"),
            "readonly_rootfs": host.get("ReadonlyRootfs"),
            "privileged": host.get("Privileged"),
            "cap_add": sorted(host.get("CapAdd") or []),
            "cap_drop": sorted(host.get("CapDrop") or []),
            "security_opt": sorted(host.get("SecurityOpt") or []),
            "pid_mode": host.get("PidMode"),
            "ipc_mode": host.get("IpcMode"),
            "cgroupns_mode": host.get("CgroupnsMode"),
            "devices": host.get("Devices"),
            "memory": host.get("Memory"),
            "memory_swap": host.get("MemorySwap"),
            "nano_cpus": host.get("NanoCpus"),
            "cpu_shares": host.get("CpuShares"),
            "pids_limit": host.get("PidsLimit"),
            "oom_kill_disable": host.get("OomKillDisable"),
            "log_config": host.get("LogConfig"),
            # Docker may serialize an unset DNS list as either null or []
            # across an otherwise identical Compose recreation.
            "dns": sorted(host.get("Dns") or []),
            "extra_hosts": host.get("ExtraHosts"),
        },
        "mounts": _mounts(inspect.get("Mounts")),
        "networks": _networks(network_settings.get("Networks")),
    }


def _inspect(container: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "inspect", container],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("docker inspect failed")
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, list) or len(parsed) != 1:
        raise ValueError("docker inspect must return exactly one container")
    if not isinstance(parsed[0], dict):
        raise ValueError("docker inspect container must be an object")
    return parsed[0]


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def capture_inspect(
    inspect: dict[str, Any],
    container: str,
    expected_image: str,
    output: Path,
) -> dict[str, Any]:
    if inspect.get("Image") != expected_image:
        raise ValueError("container image does not match expected image")
    runtime = canonical_runtime(inspect)
    payload = {
        "schema": SCHEMA,
        "container": container,
        "image": expected_image,
        "runtime": runtime,
        "runtime_sha256": _digest(runtime),
    }
    _write_atomic(output, payload)
    return {
        "status": "ok",
        "action": "capture",
        "runtime_sha256": payload["runtime_sha256"],
    }


def capture(container: str, expected_image: str, output: Path) -> dict[str, Any]:
    return capture_inspect(
        _inspect(container),
        container,
        expected_image,
        output,
    )


def capture_json(
    source: str,
    container: str,
    expected_image: str,
    output: Path,
) -> dict[str, Any]:
    if source == "-":
        parsed = json.load(sys.stdin)
    else:
        parsed = json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(parsed, list) or len(parsed) != 1:
        raise ValueError("inspect JSON must contain exactly one container")
    if not isinstance(parsed[0], dict):
        raise ValueError("inspect JSON container must be an object")
    return capture_inspect(parsed[0], container, expected_image, output)


def _read_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError("runtime snapshot schema mismatch")
    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("runtime snapshot is missing runtime")
    if payload.get("runtime_sha256") != _digest(runtime):
        raise ValueError("runtime snapshot digest mismatch")
    return payload


def compare(before: Path, after: Path) -> dict[str, Any]:
    baseline = _read_snapshot(before)
    candidate = _read_snapshot(after)
    if baseline["runtime"] != candidate["runtime"]:
        changed = sorted(
            key
            for key in baseline["runtime"].keys() | candidate["runtime"].keys()
            if baseline["runtime"].get(key) != candidate["runtime"].get(key)
        )
        raise ValueError(
            "gateway runtime parity failed in: " + ", ".join(changed)
        )
    return {
        "status": "ok",
        "action": "compare",
        "runtime_sha256": baseline["runtime_sha256"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--container", required=True)
    capture_parser.add_argument("--expected-image", required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    stream_parser = subparsers.add_parser("capture-json")
    stream_parser.add_argument("--input", default="-")
    stream_parser.add_argument("--container", required=True)
    stream_parser.add_argument("--expected-image", required=True)
    stream_parser.add_argument("--output", type=Path, required=True)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--before", type=Path, required=True)
    compare_parser.add_argument("--after", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "capture":
            result = capture(args.container, args.expected_image, args.output)
        elif args.action == "capture-json":
            result = capture_json(
                args.input,
                args.container,
                args.expected_image,
                args.output,
            )
        else:
            result = compare(args.before, args.after)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": {
                        "code": "RUNTIME_PARITY_FAILED",
                        "message": str(exc),
                    },
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
