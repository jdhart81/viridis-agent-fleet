"""Fleet-gate wrapper: the x402-C carbon-neutral loop proof must pass.

Runs scripts/carbon_neutral_work_demo.py --quiet — proves compute-ledger's
carbon_receipt + offset-clearinghouse's verify_retirement together implement
the x402-C standard (C1-C4) end to end.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_carbon_neutral_loop_holds():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "carbon_neutral_work_demo.py"), "--quiet"],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (
        f"carbon-neutral demo failed (exit {r.returncode}):\n{r.stdout}\n{r.stderr}")
    assert "ALL x402-C LOOP INVARIANTS HELD" in r.stdout
