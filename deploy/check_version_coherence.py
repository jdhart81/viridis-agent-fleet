#!/usr/bin/env python3
"""Fleet release-coherence gate.

Local checks cover every hosted gateway mount plus subscriptions:

* agent.yaml version
* core describe() and health() versions
* both publish-package server.json and tools.json files
* canonical public domain and exact mount path
* generated tool names/counts versus the current FastMCP adapter
* per-agent READ_ACTIONS/KNOWN_ACTIONS integrity

Unless --local-only is supplied, the official MCP registry and live healthz
versions are checked as well. Any absent truth surface is a release failure.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_BASE = "https://mcp.viridisconservation.com"
REGISTRY = (
    "https://registry.modelcontextprotocol.io/v0/servers"
    "?search=io.github.jdhart81"
)

# The mapping is deliberately explicit. It is also imported by publish-contract
# tests, so registry names and live mounts cannot silently diverge.
NAME_TO_MOUNT = {
    "agent-identity-registry": "identity",
    "agent-trust-oracle": "trust",
    "agent-escrow": "escrow",
    "agent-metering": "metering",
    "agent-arbitration": "arbitration",
    "agent-compute-ledger": "compute-ledger",
    "agent-covenant": "covenant",
    "agent-provenance": "provenance",
    "agent-offset-clearinghouse": "offsets",
    "agent-erc8004-bridge": "erc8004",
    "agent-surety": "surety",
    "agent-notary": "notary",
    "wavefunction-search": "wavefunction",
    "smartscale": "smartscale",
    "protogen": "protogen",
    "regulatory-radar": "regulatory-radar",
    "narrative-engine": "narrative-engine",
    "taxcredit-engine": "taxcredit-engine",
    "ghg-ledger": "ghg-ledger",
    "quantity-takeoff": "quantity-takeoff",
    "disclosure-compiler": "disclosure-compiler",
    "agent-verified-relay": "verified",
    "verdigraph": "verdigraph",
    "neurogenesis": "neurogenesis",
    "green-router": "green-router",
    "viridisos": "viridisos",
}

MOUNT_TO_DIR = {
    "identity": "agent-identity-registry-agent",
    "trust": "agent-trust-oracle-agent",
    "escrow": "agent-escrow-agent",
    "metering": "agent-metering-agent",
    "arbitration": "agent-arbitration-agent",
    "compute-ledger": "agent-compute-ledger-agent",
    "covenant": "agent-covenant-agent",
    "provenance": "agent-provenance-agent",
    "offsets": "agent-offset-clearinghouse-agent",
    "erc8004": "agent-erc8004-bridge-agent",
    "surety": "agent-surety-agent",
    "notary": "agent-notary-agent",
    "wavefunction": "wavefunction-search-agent",
    "smartscale": "smartscale-agent",
    "protogen": "protogen-agent",
    "regulatory-radar": "regulatory-radar-agent",
    "narrative-engine": "narrative-engine-agent",
    "taxcredit-engine": "taxcredit-engine-agent",
    "ghg-ledger": "ghg-ledger-agent",
    "quantity-takeoff": "quantity-takeoff-agent",
    "disclosure-compiler": "disclosure-compiler-agent",
    "verified": "agent-verified-relay-agent",
    "verdigraph": "verdigraph-brain-agent",
    "neurogenesis": "neurogenesis-agent",
    "green-router": "green-router-agent",
    "viridisos": "viridisos",
    "subscriptions": "subscriptions-agent",
}

INFRA_TO_HEALTH = {"subscriptions": "subscriptions"}
PUBLISH_TREES = ("deploy/mcp-publish", "deploy/mcp-publish-github")


def fetch(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read())


def fetch_registry() -> dict[str, Any]:
    """Fetch every search page; the registry defaults to 30 version rows."""
    servers: list[dict[str, Any]] = []
    cursor = ""
    seen: set[str] = set()
    while True:
        url = REGISTRY
        if cursor:
            url += "&cursor=" + urllib.parse.quote(cursor, safe="")
        page = fetch(url)
        servers.extend(page.get("servers", []))
        next_cursor = str(page.get("metadata", {}).get("nextCursor", "") or "")
        if not next_cursor:
            break
        if next_cursor in seen:
            raise ValueError("registry pagination cursor repeated")
        seen.add(next_cursor)
        cursor = next_cursor
    return {"servers": servers}


def _yaml_version(path: Path) -> str:
    match = re.search(
        r"(?m)^version:\s*[\"']?([^\"'\s#]+)", path.read_text()
    )
    return match.group(1) if match else ""


def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _load_adapter(mount: str, agent_dir: str):
    gateway_dir = ROOT / "deploy" / "gateway"
    if str(gateway_dir) not in sys.path:
        sys.path.insert(0, str(gateway_dir))
    import viridis_mcp_gateway as gateway

    return gateway._load_adapter(mount, agent_dir)


def _tool_names(adapter: Any) -> set[str]:
    manager = getattr(getattr(adapter, "mcp", None), "_tool_manager", None)
    tools = getattr(manager, "_tools", None)
    if not isinstance(tools, dict):
        raise TypeError("FastMCP tool registry is unavailable")
    return set(tools)


def _surface_version(core: Any, method: str) -> str:
    result = _maybe_await(getattr(core, method)())
    if not isinstance(result, dict):
        return ""
    return str(result.get("version", "") or "")


def check_local() -> tuple[list[str], dict[str, dict[str, Any]]]:
    failures: list[str] = []
    rows: dict[str, dict[str, Any]] = {}

    for mount, agent_dir in MOUNT_TO_DIR.items():
        row: dict[str, Any] = {"agent_dir": agent_dir}
        rows[mount] = row
        yaml_path = ROOT / agent_dir / "agent.yaml"
        if not yaml_path.is_file():
            failures.append(f"LC1 {mount}: missing {agent_dir}/agent.yaml")
            yaml_version = ""
        else:
            yaml_version = _yaml_version(yaml_path)
            if not yaml_version:
                failures.append(f"LC2 {mount}: agent.yaml has no version")
        row["agent_yaml"] = yaml_version

        try:
            adapter = _load_adapter(mount, agent_dir)
            core = adapter.agent
            tool_names = _tool_names(adapter)
            describe_version = _surface_version(core, "describe")
            health_version = _surface_version(core, "health")
        except Exception as exc:
            failures.append(
                f"LC3 {mount}: adapter/core load failed: "
                f"{type(exc).__name__}: {exc}"
            )
            tool_names = set()
            describe_version = ""
            health_version = ""
            core = None

        row["describe"] = describe_version
        row["health"] = health_version
        row["tool_count"] = len(tool_names)
        for label, version in (
            ("core describe()", describe_version),
            ("core health()", health_version),
        ):
            if not version:
                failures.append(f"LC4 {mount}: {label} has no version")
            elif yaml_version and version != yaml_version:
                failures.append(
                    f"LC5 {mount}: agent.yaml={yaml_version} "
                    f"{label}={version}"
                )

        if core is not None and hasattr(core, "READ_ACTIONS"):
            reads = getattr(core, "READ_ACTIONS")
            known = getattr(core, "KNOWN_ACTIONS", None)
            if not isinstance(reads, (set, frozenset)):
                failures.append(f"LC6 {mount}: READ_ACTIONS is not a set")
            if not isinstance(known, (set, frozenset)):
                failures.append(f"LC6 {mount}: KNOWN_ACTIONS is not a set")
            elif isinstance(reads, (set, frozenset)) and not reads <= known:
                failures.append(
                    f"LC7 {mount}: unknown reads "
                    f"{sorted(reads - known)}"
                )

        expected_remote = f"{CANONICAL_BASE}/{mount}/mcp"
        for tree in PUBLISH_TREES:
            package = ROOT / tree / agent_dir
            server_path = package / "server.json"
            tools_path = package / "tools.json"
            relative = package.relative_to(ROOT)
            if not server_path.is_file():
                failures.append(f"LC8 {mount}: missing {relative}/server.json")
            else:
                try:
                    server = json.loads(server_path.read_text())
                except Exception as exc:
                    failures.append(
                        f"LC9 {mount}: invalid {relative}/server.json: {exc}"
                    )
                    server = {}
                manifest_version = str(server.get("version", "") or "")
                remotes = server.get("remotes", [])
                remote = (
                    remotes[0].get("url", "")
                    if isinstance(remotes, list) and remotes
                    and isinstance(remotes[0], dict)
                    else ""
                )
                if manifest_version != yaml_version:
                    failures.append(
                        f"LC10 {mount}: {relative}/server.json="
                        f"{manifest_version or 'missing'} agent.yaml="
                        f"{yaml_version or 'missing'}"
                    )
                if remote != expected_remote:
                    failures.append(
                        f"LC11 {mount}: {relative}/server.json remote="
                        f"{remote or 'missing'} expected={expected_remote}"
                    )
            if not tools_path.is_file():
                failures.append(f"LC12 {mount}: missing {relative}/tools.json")
            else:
                try:
                    manifest = json.loads(tools_path.read_text())
                    packaged = manifest.get("tools", [])
                    packaged_names = {
                        tool.get("name") for tool in packaged
                        if isinstance(tool, dict) and tool.get("name")
                    }
                    declared_count = manifest.get("tool_count")
                    if declared_count != len(packaged):
                        failures.append(
                            f"LC13 {mount}: {relative}/tools.json count="
                            f"{declared_count} actual={len(packaged)}"
                        )
                    if packaged_names != tool_names:
                        failures.append(
                            f"LC14 {mount}: {relative}/tools.json drift "
                            f"missing={sorted(tool_names - packaged_names)} "
                            f"stale={sorted(packaged_names - tool_names)}"
                        )
                except Exception as exc:
                    failures.append(
                        f"LC15 {mount}: invalid {relative}/tools.json: {exc}"
                    )
    return failures, rows


def check_remote(base: str) -> tuple[list[str], dict[str, dict[str, str]]]:
    failures: list[str] = []
    rows: dict[str, dict[str, str]] = {}
    try:
        registry = fetch_registry()
        health = fetch(f"{base.rstrip('/')}/healthz")
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        return [f"RC0 remote evidence unavailable: {type(exc).__name__}: {exc}"], rows

    latest: dict[str, str] = {}
    for entry in registry.get("servers", []):
        meta = entry.get("_meta", {}).get(
            "io.modelcontextprotocol.registry/official", {}
        )
        if not meta.get("isLatest"):
            continue
        server = entry.get("server", {})
        name = str(server.get("name", "")).split("/", 1)[-1]
        latest[name] = str(server.get("version", "") or "")

    agents = health.get("agents", {})
    for short, mount in {**NAME_TO_MOUNT, **INFRA_TO_HEALTH}.items():
        advertised = latest.get(short, "")
        live_surface = (
            health.get(mount, {})
            if short in INFRA_TO_HEALTH
            else agents.get(mount, {})
        )
        running = str(live_surface.get("version", "") or "")
        rows[mount] = {"registry": advertised, "running": running}
        if not advertised:
            failures.append(f"RC1 {short}: no latest official registry version")
        if not running:
            failures.append(f"RC2 {mount}: live healthz has no version")
        if advertised and running and advertised != running:
            failures.append(
                f"RC3 {short}: registry={advertised} running={running}"
            )
    return failures, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=CANONICAL_BASE)
    parser.add_argument(
        "--local-only", action="store_true",
        help="skip registry/live checks; still require every local truth surface",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    failures, local_rows = check_local()
    remote_rows: dict[str, dict[str, str]] = {}
    if not args.local_only:
        remote_failures, remote_rows = check_remote(args.base)
        failures.extend(remote_failures)

    report = {
        "status": "pass" if not failures else "blocked",
        "canonical_base": CANONICAL_BASE,
        "checked_agents": len(MOUNT_TO_DIR),
        "local": local_rows,
        "remote": remote_rows,
        "violations": failures,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif failures:
        print(f"FLEET RELEASE BLOCKED — {len(failures)} coherence violation(s)")
        for failure in failures:
            print(f"  - {failure}")
    else:
        scope = "local + registry + live" if not args.local_only else "local"
        print(
            f"FLEET COHERENCE PASS — {len(MOUNT_TO_DIR)} agents, {scope}"
        )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
