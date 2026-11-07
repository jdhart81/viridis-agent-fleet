#!/usr/bin/env python3
"""Pre-deploy fleet-contract check for one agent directory.

The hosted gateway (proprietary) imposes four contracts that the public template's tests do not all cover, and a miss
fails the gateway's health gate at swap time (settlement-engine-agent, 2026-11-06: one auto-rollback). This script checks
them offline:

  C1  adapters/mcp_server.py exposes `mcp` (FastMCP) and `agent` (the core)                      [mount]
  C2  agent.health() is a dict with status == "ok"                                              [/healthz gate]
  C3  an unknown action returns a fleet error envelope: status == "error", never raises          [isError, PG]
  C4  every tool is wrapped by fleet_utils.mcp_errors.flag_error_results (__fleet_flags_errors__) [isError]
  C5  if the agent is gated: READ_ACTIONS and KNOWN_ACTIONS are frozensets, READ ⊆ KNOWN         [payment gate]
  C6  the core's state attributes pickle (the gateway StateStore persists them)                 [persistence]

Usage: python3 scripts/fleet_contract_check.py <agent-dir> [--gated]     (exit 1 on any failure)
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_ATTRS = {"config", "logger", "process", "_gate_inner"}


def load_adapter(agent_dir: Path):
    for m in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
    sys.path.insert(0, str(agent_dir))
    spec = importlib.util.spec_from_file_location("fleet_check_adapter", agent_dir / "adapters" / "mcp_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_dir")
    ap.add_argument("--gated", action="store_true", help="the agent will be in the gateway's gated_mounts")
    a = ap.parse_args()
    d = (ROOT / a.agent_dir).resolve() if not Path(a.agent_dir).is_absolute() else Path(a.agent_dir)
    results = []

    def check(code, ok, why=""):
        results.append((code, bool(ok), why))

    try:
        mod = load_adapter(d)
    except Exception as e:
        print(f"C1 FAIL adapter import: {type(e).__name__}: {e}")
        return 1
    check("C1", hasattr(mod, "mcp") and hasattr(mod, "agent"), "adapter must expose mcp and agent")
    agent = getattr(mod, "agent", None)
    try:
        h = agent.health()
        h = asyncio.run(h) if asyncio.iscoroutine(h) else h
        check("C2", isinstance(h, dict) and h.get("status") == "ok", f"health() -> {str(h)[:120]}")
    except Exception as e:
        check("C2", False, f"health() raised {type(e).__name__}: {e}")
    try:
        r = agent.process({"action": "__fleet_contract_check_unknown__"})
        r = asyncio.run(r) if asyncio.iscoroutine(r) else r
        check("C3", isinstance(r, dict) and r.get("status") == "error", f"unknown action -> {str(r)[:120]}")
    except Exception as e:
        check("C3", False, f"process() raised {type(e).__name__}: {e}")
    tools = getattr(getattr(mod.mcp, "_tool_manager", None), "_tools", None)
    if tools is None:
        tools = getattr(mod.mcp, "tools", {})
    bare = []
    for name, t in (tools or {}).items():
        fn = getattr(t, "fn", t)
        if not getattr(fn, "__fleet_flags_errors__", False):
            bare.append(name)
    check("C4", not bare, f"tools not wrapped by flag_error_results: {bare[:6]}")
    ra, ka = getattr(agent, "READ_ACTIONS", None), getattr(agent, "KNOWN_ACTIONS", None)
    if a.gated or ra is not None or ka is not None:
        check("C5", isinstance(ra, frozenset) and isinstance(ka, frozenset) and ra <= ka,
              f"READ_ACTIONS={type(ra).__name__} KNOWN_ACTIONS={type(ka).__name__}")
    else:
        check("C5", True, "not gated; READ/KNOWN_ACTIONS optional")
    bad = []
    for k, v in vars(agent).items():
        if k in EXCLUDED_ATTRS:
            continue
        try:
            pickle.dumps(v, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            bad.append(f"{k}: {type(e).__name__}")
    check("C6", not bad, f"unpicklable state attrs: {bad[:4]}")
    ok_all = all(ok for _, ok, _ in results)
    for code, ok, why in results:
        print(f"{code} {'ok  ' if ok else 'FAIL'} {why}")
    print(f"{d.name}: {'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
