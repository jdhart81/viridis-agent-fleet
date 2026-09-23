#!/usr/bin/env python3
"""
Viridis Fleet Test Runner — runs each agent's tests in isolation.
Avoids namespace collisions by running pytest per-agent with rootdir set.
"""
import subprocess
import sys
import os
import time
from pathlib import Path

# Resolve once so infrastructure suites remain valid when this runner itself
# is invoked through a relative path.  A relative FLEET_ROOT combined with
# cwd=agent_dir turns the scripts suite into scripts/scripts and silently
# reports a collection error.
FLEET_ROOT = Path(__file__).resolve().parent

# Auto-discover: any directory with a tests/ subdirectory
AGENTS = sorted([
    d.name for d in FLEET_ROOT.iterdir()
    if d.is_dir() and (d / "tests").is_dir()
    and not d.name.startswith(('.', '_'))
    and d.name not in ('fleet_utils', '05_AGENTS copy', 'side project agents ')
])
# Revenue infrastructure and live commerce products are critical even before
# their test directories exist: any absent suite must fail the Nightkeeper gate
# instead of silently disappearing from auto-discovery.
REQUIRED_AGENT_SUITES = (
    "subscriptions-agent",
    "quantity-takeoff-agent",
    "disclosure-compiler-agent",
    "agent-hive-orchestrator-agent",
)
for required in REQUIRED_AGENT_SUITES:
    if required not in AGENTS:
        AGENTS.append(required)

# Infrastructure suites are part of the same release gate.  Payments covers
# the Stripe-hosted prepare-to-the-click rail; Glama covers the public aggregate
# bridge; gateway covers persistence/auth/entitlement integration.
AGENTS.extend(("deploy/payments", "deploy/glama", "deploy/gateway",
               "deploy/droplet", "scripts"))


def _pythonpath_for(agent_dir):
    """Keep both package-style root imports and isolated agent imports valid."""
    return os.pathsep.join(dict.fromkeys(
        p for p in (
            str(FLEET_ROOT),
            str(agent_dir),
            os.environ.get("PYTHONPATH", ""),
        ) if p
    ))


def run_agent_tests(agent_name):
    """Run tests for a single agent, return (name, passed, failed, errors, duration)."""
    agent_dir = FLEET_ROOT / agent_name
    test_dir = agent_dir / "tests"
    if not test_dir.is_dir():
        test_dir = agent_dir   # gateway-level suites keep tests alongside code

    start = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_dir),
         "--rootdir", str(agent_dir),
         "--tb=line", "--no-header", "-q",
         "--override-ini=asyncio_mode=auto",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, timeout=60,
        cwd=str(agent_dir),
        env={**os.environ, "PYTHONPATH": _pythonpath_for(agent_dir)}
    )
    duration = time.time() - start

    output = result.stdout + result.stderr
    # Parse pytest summary line like "49 passed" or "3 failed, 10 passed"
    passed = failed = errors = 0
    for line in output.split('\n'):
        if 'passed' in line or 'failed' in line or 'error' in line:
            import re
            p = re.search(r'(\d+) passed', line)
            f = re.search(r'(\d+) failed', line)
            e = re.search(r'(\d+) error', line)
            if p: passed = int(p.group(1))
            if f: failed = int(f.group(1))
            if e: errors = int(e.group(1))

    if result.returncode != 0 and failed == 0 and errors == 0:
        errors = 1

    return agent_name, passed, failed, errors, duration, result.returncode

if __name__ == "__main__":
    print(f"{'='*70}")
    print(f"  VIRIDIS FLEET TEST SUITE — {len(AGENTS)} agents")
    print(f"{'='*70}\n")

    results = []
    total_passed = total_failed = total_errors = 0
    fleet_start = time.time()

    for agent in AGENTS:
        try:
            name, p, f, e, dur, rc = run_agent_tests(agent)
            results.append((name, p, f, e, dur, rc))
            total_passed += p
            total_failed += f
            total_errors += e

            status = "✓" if rc == 0 and f == 0 and e == 0 else "✗"
            print(f"  {status} {name:<45} {p:>3} passed  {f:>2} failed  {e:>2} errors  ({dur:.2f}s)")
        except subprocess.TimeoutExpired:
            results.append((agent, 0, 0, 1, 60.0, 1))
            total_errors += 1
            print(f"  ⏱ {agent:<45}   TIMEOUT (60s)")
        except Exception as ex:
            results.append((agent, 0, 0, 1, 0, 1))
            total_errors += 1
            print(f"  ✗ {agent:<45}   ERROR: {ex}")

    fleet_duration = time.time() - fleet_start

    print(f"\n{'='*70}")
    print(f"  FLEET TOTALS: {total_passed} passed | {total_failed} failed | {total_errors} errors")
    print(f"  AGENTS: {sum(1 for _,_,f,e,_,_ in results if f==0 and e==0)}/{len(results)} clean")
    print(f"  TIME: {fleet_duration:.2f}s")
    print(f"{'='*70}")

    sys.exit(1 if total_failed > 0 or total_errors > 0 else 0)
