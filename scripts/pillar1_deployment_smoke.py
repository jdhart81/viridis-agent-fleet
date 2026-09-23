#!/usr/bin/env python3
"""Smoke check deployability for Pillar 1 revenue agents.

This intentionally excludes Energy AI and Bounty Hunter because they are already
deployed. It verifies the remaining money agents have their claimed deployment
surfaces and can boot their core, describe themselves, and report health.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

AGENTS = [
    {
        "dir": "smartscale-agent",
        "class_name": "SmartScaleCore",
        "expected": ["adapters/fastapi_server.py", "adapters/mcp_server.py", "agent.yaml"],
    },
    {
        "dir": "protogen-agent",
        "class_name": "ProtoGenCore",
        "expected": ["adapters/fastapi_server.py", "adapters/mcp_server.py", "agent.yaml"],
    },
    {
        "dir": "compute-exchange-agent",
        "class_name": "ComputeExchangeCore",
        "expected": ["adapters/fastapi_server.py", "adapters/mcp_server.py", "agent.yaml"],
    },
    {
        "dir": "ecoinvest-agent",
        "class_name": "EcoInvestCore",
        "config_name": "ecoinvest-agent",
        "expected": ["adapters/fastapi_server.py", "agent.yaml"],
    },
    {
        "dir": "viridis-trading-agent",
        "class_name": "TradingCore",
        "config_name": "viridis-trading-agent",
        "expected": ["adapters/fastapi_server.py", "agent.yaml"],
    },
    {
        "dir": "thermo-arbitrage-agent",
        "class_name": "ThermoArbitrageCore",
        "config_name": "thermo-arbitrage-agent",
        "expected": ["adapters/fastapi_server.py", "agent.yaml"],
    },
    {
        "dir": "ecotopia-agent",
        "class_name": "EcotopiaCore",
        "expected": ["adapters/fastapi_server.py", "adapters/mcp_server.py", "agent.yaml"],
    },
    {
        "dir": "qi-flow-architect-agent",
        "class_name": "QiFlowArchitectCore",
        "expected": ["adapters/fastapi_server.py", "adapters/mcp_server.py", "agent.yaml"],
    },
    {
        "dir": "living-game-coach-agent",
        "class_name": "LivingGameCoachCore",
        "expected": ["adapters/fastapi_server.py", "adapters/mcp_server.py", "agent.yaml"],
    },
]


BOOT_TEMPLATE = r"""
import asyncio
import inspect
from src import core

Core = getattr(core, "{class_name}")
config_name = {config_name!r}
if config_name:
    AgentConfig = getattr(core, "AgentConfig")
    try:
        agent = Core(AgentConfig(name=config_name))
    except TypeError:
        agent = Core(AgentConfig())
else:
    agent = Core()

description = agent.describe()
health_result = agent.health()
if inspect.isawaitable(health_result):
    health_result = asyncio.run(health_result)

assert isinstance(description, dict), "describe() did not return a dict"
assert isinstance(health_result, dict), "health() did not return a dict"
assert health_result.get("status") == "ok", health_result
print(description.get("name", "{class_name}"))
"""


def check_files(agent: dict) -> list[str]:
    missing = []
    agent_dir = ROOT / agent["dir"]
    for rel_path in agent["expected"]:
        if not (agent_dir / rel_path).exists():
            missing.append(rel_path)
    return missing


def boot_agent(agent: dict) -> tuple[bool, str]:
    agent_dir = ROOT / agent["dir"]
    code = BOOT_TEMPLATE.format(
        class_name=agent["class_name"],
        config_name=agent.get("config_name"),
    )
    env = {**os.environ, "PYTHONPATH": str(agent_dir)}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(agent_dir),
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def main() -> int:
    failures = []
    print("Pillar 1 deployment smoke: remaining revenue agents")
    print("Excluded as already deployed: energyai-agent, bounty-hunter-agent")
    print()

    for agent in AGENTS:
        missing = check_files(agent)
        boot_ok, boot_output = boot_agent(agent)
        file_status = "files ok" if not missing else f"missing {', '.join(missing)}"
        boot_status = "boots" if boot_ok else "boot failed"
        print(f"- {agent['dir']}: {file_status}; {boot_status}")
        if boot_output:
            print(f"  {boot_output.splitlines()[-1]}")
        if missing or not boot_ok:
            failures.append(agent["dir"])

    if failures:
        print()
        print("FAILED:", ", ".join(failures))
        return 1

    print()
    print("All remaining Pillar 1 revenue agents have deployment surfaces and boot cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
