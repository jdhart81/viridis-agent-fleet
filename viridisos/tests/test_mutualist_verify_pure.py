"""Purity + determinism pins for the mutualist certify->verify path.

test_mutualist.py proves one issue->verify round trip, but nothing pins that
`Certifier.verify` is a pure, repeatable read (A-2 is a verdict, not an
action), that verification never mutates the registry it consults, or that
the SRPT kernel itself is deterministic. Extends the fleet-wide verify-purity
sweep (N64-N67) into the viridisos modules per the standing Nightkeeper
queue. Additive; existing tests untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.canon_resolver import CanonResolver
from certification.certifier import Certifier
from modules.mutualist import MutualistModule
from modules.mutualist.module import SRPT_BACKING

RESOLVER = CanonResolver(entries={SRPT_BACKING.doi: {
    "verified": True, "lean_module": "SymbioticRiskPremium"}})

INPUTS = {"rho": 1.5, "sigma": 1e-20, "sigma_tot": 3e-20, "r_c": -0.4}


def test_kernel_compute_is_deterministic():
    m = MutualistModule(resolver=RESOLVER)
    a = m.compute(dict(INPUTS))
    b = m.compute(dict(INPUTS))
    assert a == b
    # non-triviality guard: different inputs must diverge
    c = m.compute({**INPUTS, "sigma": 2e-20})
    assert c != a


def test_verify_is_repeatable_and_does_not_mutate_registry():
    m = MutualistModule(resolver=RESOLVER)
    certifier = Certifier(resolver=RESOLVER)
    cert = certifier.issue(m, subject="portfolio-7", inputs=INPUTS)
    revoked_before = certifier.registry.is_revoked(cert.certificate_id)
    assert certifier.verify(cert, m, INPUTS) is True
    assert certifier.verify(cert, m, INPUTS) is True  # repeat: same verdict
    # verifying must not revoke, re-record, or otherwise change the registry
    assert certifier.registry.is_revoked(cert.certificate_id) == revoked_before
    assert certifier.verify(cert, m, INPUTS) is True  # still true after audit


def test_mismatched_inputs_verdict_is_deterministic_on_repeat():
    m = MutualistModule(resolver=RESOLVER)
    certifier = Certifier(resolver=RESOLVER)
    cert = certifier.issue(m, subject="portfolio-7", inputs=INPUTS)
    wrong = {**INPUTS, "rho": 9.9}
    assert certifier.verify(cert, m, wrong) is False
    assert certifier.verify(cert, m, wrong) is False  # repeat: same verdict
    # the failed audit must not poison the valid path
    assert certifier.verify(cert, m, INPUTS) is True


if __name__ == "__main__":
    import traceback
    fns = [g for n, g in sorted(globals().items())
           if n.startswith("test_") and callable(g)]
    p = f = 0
    for fn in fns:
        try:
            fn(); p += 1; print(f"PASS  {fn.__name__}")
        except Exception:
            f += 1; print(f"FAIL  {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed")
    raise SystemExit(1 if f else 0)
