#!/usr/bin/env python3
"""Public test runner: every open agent with a tests/ dir, isolated per agent.

(The hosted service keeps its own stricter release gate privately.)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENTS = sorted(d.name for d in ROOT.iterdir()
                if d.is_dir() and (d / "tests").is_dir() and not d.name.startswith((".", "_")))


def run(name):
    d = ROOT / name
    t = time.time()
    r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "--no-header", "--tb=line",
                        "-p", "no:cacheprovider", "--override-ini=asyncio_mode=auto"],
                       cwd=d, capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (str(ROOT), str(d), os.environ.get("PYTHONPATH"))))})
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    ok = r.returncode == 0
    print(f"  {'✓' if ok else '✗'} {name:<42} {tail}  ({time.time() - t:.1f}s)")
    return ok


if __name__ == "__main__":
    results = [run(a) for a in AGENTS]
    print(f"\n{sum(results)}/{len(results)} agents clean")
    sys.exit(0 if all(results) else 1)
