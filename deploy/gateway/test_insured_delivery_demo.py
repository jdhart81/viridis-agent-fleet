"""Fleet-gate wrapper: the insured-delivery composition proof must pass.

Runs scripts/insured_delivery_demo.py --quiet as a subprocess (the demo is a
self-contained cross-rail integration test that exits non-zero on any invariant
failure). Keeps the 6-rail composition — verified→surety→escrow→notary→
arbitration→trust — green as part of the fleet suite.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_insured_delivery_composition_holds():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "insured_delivery_demo.py"), "--quiet"],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (
        f"insured-delivery demo failed (exit {r.returncode}):\n"
        f"{r.stdout}\n{r.stderr}")
    assert "ALL INSURED-DELIVERY INVARIANTS HELD" in r.stdout
