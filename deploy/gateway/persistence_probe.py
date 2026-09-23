#!/usr/bin/env python3
"""
persistence_probe — proves the gateway's restart-persistence invariant against
a RUNNING gateway (local or production) over real MCP streamable-http.

The invariant (PS1/PS2, see state_store.py): an escrow opened before a gateway
restart still exists, in the same state, with a valid audit chain, after it.

Usage:
    # 1. before restart: opens a marker escrow, prints its id
    python3 persistence_probe.py mark   [--base URL]
    # 2. restart the gateway (docker compose restart gateway)
    # 3. after restart: verifies the marker survived + audit chain valid
    python3 persistence_probe.py verify --escrow-id <id> [--base URL]

    # or one-shot against a local gateway it manages itself:
    python3 persistence_probe.py selftest    # boots gateway, kills it, reboots

Exit code 0 = invariant holds; non-zero = it does not.
BASE defaults to $BASE or http://127.0.0.1:8402.
"""
import argparse
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = os.environ.get("BASE", "http://127.0.0.1:8402").rstrip("/")
HERE = Path(__file__).resolve().parent


async def _call(base: str, path: str, tool: str, args: dict) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(f"{base}/{path}/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            return json.loads(res.content[0].text)


async def mark(base: str) -> str:
    out = await _call(base, "escrow", "open_escrow",
                      {"payer": "persistence-probe", "payee": "persistence-probe-peer",
                       "amount_minor": 1,
                       "terms": "restart-persistence marker (PS1/PS2)"})
    eid = out["data"]["escrow_id"]
    print(f"marker escrow: {eid}  (state={out['data']['state']})")
    return eid


async def verify(base: str, eid: str) -> bool:
    status = await _call(base, "escrow", "escrow_status", {"escrow_id": eid})
    ok_exists = status.get("status") == "ok" and status["data"]["state"] == "OPEN"
    audit = await _call(base, "escrow", "verify_audit", {"escrow_id": eid})
    ok_audit = audit.get("status") == "ok" and audit["data"]["valid"] is True
    print(f"  {'✓' if ok_exists else '✗ FAIL'} marker escrow survived restart")
    print(f"  {'✓' if ok_audit else '✗ FAIL'} audit hash chain valid after restart")
    return ok_exists and ok_audit


def _wait_port(port: int, timeout: float = 30.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                time.sleep(0.5)  # let lifespan finish
                return
        except OSError:
            time.sleep(0.3)
    raise TimeoutError(f"gateway did not open port {port}")


def selftest() -> int:
    """Boot the gateway locally, mark, HARD-KILL it (SIGKILL — no graceful
    shutdown, so this proves write-through, not save-on-exit), reboot, verify."""
    import tempfile
    port = 8412
    env = dict(os.environ,
               STATE_DB=str(Path(tempfile.mkdtemp()) / "probe_state.db"))
    gw = [sys.executable, str(HERE / "viridis_mcp_gateway.py"), "--port", str(port)]

    def boot():
        return subprocess.Popen(gw, env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.STDOUT)

    p = boot()
    try:
        _wait_port(port)
        eid = asyncio.run(mark(f"http://127.0.0.1:{port}"))
    finally:
        p.send_signal(signal.SIGKILL)   # crash, not shutdown
        p.wait()

    p = boot()
    try:
        _wait_port(port)
        ok = asyncio.run(verify(f"http://127.0.0.1:{port}", eid))
    finally:
        p.send_signal(signal.SIGTERM)
        p.wait()
    print("SELFTEST:", "PASS — state survives a hard kill" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["mark", "verify", "selftest"])
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--escrow-id", default="")
    a = ap.parse_args()
    if a.cmd == "mark":
        asyncio.run(mark(a.base))
        sys.exit(0)
    if a.cmd == "verify":
        if not a.escrow_id:
            sys.exit("--escrow-id required for verify")
        sys.exit(0 if asyncio.run(verify(a.base, a.escrow_id)) else 1)
    sys.exit(selftest())
