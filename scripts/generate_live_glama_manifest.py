#!/usr/bin/env python3
"""Regenerate Glama's aggregate tool manifest from the live MCP fleet.

The release gate is intentionally strict: the live gateway must be healthy,
the hosted-agent count must match, and every advertised MCP endpoint must
complete initialize + tools/list before the local manifest is replaced.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "deploy" / "glama" / "fleet_manifest.json"
AUXILIARY_MOUNTS = {"subscriptions": "0.1.1"}


def fetch_health(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/healthz", timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"healthz returned HTTP {response.status}")
        return json.load(response)


async def fetch_tools(base: str, mount: str) -> list[dict]:
    async with streamablehttp_client(f"{base}/{mount}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "inputSchema": tool.inputSchema,
        }
        for tool in listed.tools
    ]


async def build_manifest(base: str, mounts: list[str]) -> dict[str, list[dict]]:
    results = await asyncio.gather(
        *(fetch_tools(base, mount) for mount in mounts),
        return_exceptions=True,
    )
    failures = [
        f"{mount}: {type(result).__name__}: {result}"
        for mount, result in zip(mounts, results)
        if isinstance(result, BaseException)
    ]
    if failures:
        raise RuntimeError("live tools/list failed: " + "; ".join(failures))
    return {mount: tools for mount, tools in zip(mounts, results)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", default="https://mcp.viridisconservation.com",
        help="live gateway base URL",
    )
    parser.add_argument("--expected-count", type=int, default=28)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    base = args.base.rstrip("/")
    health = fetch_health(base)
    agents = health.get("agents") or {}
    if health.get("status") != "ok":
        raise SystemExit(f"refusing manifest write: live status={health.get('status')!r}")
    if len(agents) != args.expected_count:
        raise SystemExit(
            f"refusing manifest write: live agents={len(agents)}, "
            f"expected={args.expected_count}"
        )
    if agents.get("ghg-ledger", {}).get("version") != "0.1.0":
        raise SystemExit("refusing manifest write: ghg-ledger v0.1.0 is not live")
    if agents.get("quantity-takeoff", {}).get("version") != "0.1.0":
        raise SystemExit("refusing manifest write: quantity-takeoff v0.1.0 is not live")
    if agents.get("disclosure-compiler", {}).get("version") != "0.1.0":
        raise SystemExit(
            "refusing manifest write: disclosure-compiler v0.1.0 is not live"
        )

    for mount, version in AUXILIARY_MOUNTS.items():
        info = health.get(mount) or {}
        if info.get("status") != "ok" or str(info.get("version") or "") != version:
            raise SystemExit(
                f"refusing manifest write: auxiliary /{mount} is not live "
                f"and coherent at v{version}"
            )

    mounts = sorted([*agents, *AUXILIARY_MOUNTS])
    manifest = asyncio.run(build_manifest(base, mounts))
    total = sum(len(tools) for tools in manifest.values())
    if not manifest.get("ghg-ledger"):
        raise SystemExit("refusing manifest write: ghg-ledger has no live tools")
    if not manifest.get("quantity-takeoff"):
        raise SystemExit("refusing manifest write: quantity-takeoff has no live tools")
    if not manifest.get("disclosure-compiler"):
        raise SystemExit(
            "refusing manifest write: disclosure-compiler has no live tools"
        )
    if not manifest.get("subscriptions"):
        raise SystemExit("refusing manifest write: subscriptions has no live tools")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(manifest, indent=2) + "\n")
    temp.replace(output)
    print(f"live manifest: {len(agents)} agents + {len(AUXILIARY_MOUNTS)} "
          f"infrastructure surface / {total} tools -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
