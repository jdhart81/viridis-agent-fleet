#!/usr/bin/env python3
"""Candidate-only proof that gate-driven metering survives a restart."""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def health(base: str) -> dict:
    with urllib.request.urlopen(
            f"{base.rstrip('/')}/healthz", timeout=20) as response:
        return json.load(response)


def counters(payload: dict) -> dict:
    persistence = payload.get("metering_persistence", {})
    meter_checks = payload.get("agents", {}).get(
        "metering", {}).get("checks", {})
    return {
        "snapshot_seq": persistence.get("snapshot_seq"),
        "last_persisted_at": persistence.get("last_persisted_at"),
        "events": meter_checks.get("events"),
    }


async def mark(base: str) -> dict:
    before = counters(health(base))
    async with streamablehttp_client(
            f"{base.rstrip('/')}/smartscale/mcp") as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool(
                "scale_objects_from_credit_card",
                {
                    "image_id": "metering-persistence-release-probe",
                    "credit_card_pixel_width": 856.0,
                    "objects": [{
                        "label": "probe",
                        "pixel_width": 428.0,
                        "pixel_height": 214.0,
                    }],
                    "request_id": "metering-persistence-release-probe-20260725",
                },
            )
    if getattr(result, "isError", False):
        raise RuntimeError("candidate SmartScale probe returned an MCP error")
    after = counters(health(base))
    if not isinstance(before["snapshot_seq"], int):
        raise RuntimeError("candidate has no persisted metering snapshot")
    if after["snapshot_seq"] <= before["snapshot_seq"]:
        raise RuntimeError("metering snapshot sequence did not advance")
    if after["events"] <= before["events"]:
        raise RuntimeError("metering event count did not advance")
    if not after["last_persisted_at"]:
        raise RuntimeError("metering persistence timestamp is missing")
    return {"status": "ok", "before": before, "after": after}


async def mounts(base: str) -> dict:
    with urllib.request.urlopen(
            f"{base.rstrip('/')}/", timeout=20) as response:
        directory = json.load(response)
    paths = sorted(directory.get("agents", {}))
    if "subscriptions" in directory.get("infrastructure", {}):
        paths.append("subscriptions")
    results = {}
    for path in paths:
        async with streamablehttp_client(
                f"{base.rstrip('/')}/{path}/mcp") as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                results[path] = len(tools.tools)
    if len(results) != 27:
        raise RuntimeError(f"expected 27 MCP mounts, got {len(results)}")
    if any(count < 1 for count in results.values()):
        raise RuntimeError("one or more MCP mounts published no tools")
    return {
        "status": "ok",
        "mounts": len(results),
        "tools": sum(results.values()),
        "per_mount": results,
    }


def verify(base: str, min_seq: int, min_events: int) -> dict:
    current = counters(health(base))
    if current["snapshot_seq"] < min_seq:
        raise RuntimeError("metering snapshot sequence rolled back on restart")
    if current["events"] < min_events:
        raise RuntimeError("metering events rolled back on restart")
    if not current["last_persisted_at"]:
        raise RuntimeError("metering persistence timestamp is missing")
    return {"status": "ok", "current": current}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:18402")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("mark")
    subparsers.add_parser("mounts")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--min-seq", type=int, required=True)
    verify_parser.add_argument("--min-events", type=int, required=True)
    args = parser.parse_args()

    if args.command == "mark":
        result = asyncio.run(mark(args.base))
    elif args.command == "mounts":
        result = asyncio.run(mounts(args.base))
    else:
        result = verify(args.base, args.min_seq, args.min_events)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
