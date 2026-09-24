"""Purity + determinism pins for harmonization certify->verify (N69).

Extends the N67 mutualist / N68 afforestation idiom to the harmonization
(GHT) module per the standing Nightkeeper queue: kernel determinism
(+ divergence guard), Certifier.verify as a pure repeatable read, registry
no-mutation under audit — plus the GHT theorem's own headline invariants
pinned mechanically: the clearing shadow price is the max binding marginal
cost, the wu-wei dividend is exactly overhead*(n-1) (strictly positive for
n>=2 stewards — decentralization is cheaper BY THE THEOREM), and
out-of-domain inputs (no stewards, negative costs) are refused.

The restoration parity file completes the module-wide sweep.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.canon_resolver import CanonResolver
from certification.certifier import Certifier
from modules.harmonization import HarmonizationModule
from modules.harmonization.module import GHT_BACKING
from modules.harmonization import engine

RESOLVER = CanonResolver(entries={GHT_BACKING.doi: {
    "verified": True, "lean_module": "GaianHarmonization"}})

INPUTS = {"marginal_costs": [0.5, 1.25, 0.75], "command_overhead": 2.0,
          "bandwidth": 0.4, "ib_bound": 1.0}


def test_kernel_compute_is_deterministic():
    m = HarmonizationModule(resolver=RESOLVER)
    a = m.compute(dict(INPUTS))
    b = m.compute(dict(INPUTS))
    assert a == b
    # non-triviality guard: a different binding cost must diverge
    c = m.compute({**INPUTS, "marginal_costs": [0.5, 2.5, 0.75]})
    assert c != a


def test_ght_headline_shadow_price_and_wu_wei_dividend():
    """GHT headline: lambda* is the max binding marginal cost, and the
    wu-wei dividend is exactly overhead*(n-1) — strictly positive for
    n>=2 stewards. Pin the exact arithmetic so a silent kernel change
    reads red."""
    out = engine.harmonize(marginal_costs=[0.5, 1.25, 0.75],
                           command_overhead=2.0, bandwidth=0.4, ib_bound=1.0)
    assert out["shadow_price"] == pytest.approx(1.25)
    assert out["wu_wei_dividend"] == pytest.approx(2.0 * (3 - 1))
    assert out["decentralization_cheaper"] is True
    assert out["coordination_within_ib"] is True
    # single steward: nothing to decentralize over — dividend collapses to 0
    solo = engine.harmonize(marginal_costs=[0.9], command_overhead=2.0,
                            bandwidth=0.4, ib_bound=1.0)
    assert solo["wu_wei_dividend"] == pytest.approx(0.0)
    assert solo["decentralization_cheaper"] is False
    # bandwidth over the IB bound flips the coordination flag, nothing else
    over = engine.harmonize(marginal_costs=[0.5, 1.25, 0.75],
                            command_overhead=2.0, bandwidth=1.5, ib_bound=1.0)
    assert over["coordination_within_ib"] is False
    assert over["shadow_price"] == out["shadow_price"]


@pytest.mark.parametrize("bad", [
    {"marginal_costs": []},
    {"marginal_costs": [0.5, -0.1]},
])
def test_out_of_domain_inputs_are_refused(bad):
    m = HarmonizationModule(resolver=RESOLVER)
    with pytest.raises(ValueError):
        m.compute({**INPUTS, **bad})


def test_verify_is_repeatable_and_does_not_mutate_registry():
    m = HarmonizationModule(resolver=RESOLVER)
    certifier = Certifier(resolver=RESOLVER)
    cert = certifier.issue(m, subject="basin-7", inputs=INPUTS)
    revoked_before = certifier.registry.is_revoked(cert.certificate_id)
    assert certifier.verify(cert, m, INPUTS) is True
    assert certifier.verify(cert, m, INPUTS) is True  # repeat: same verdict
    assert certifier.registry.is_revoked(cert.certificate_id) == revoked_before
    # mismatched inputs must fail the audit WITHOUT poisoning the valid path
    assert certifier.verify(cert, m, {**INPUTS, "command_overhead": 3.0}) is False
    assert certifier.verify(cert, m, INPUTS) is True
