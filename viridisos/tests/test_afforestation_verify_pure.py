"""Purity + determinism pins for afforestation certify->verify (N68).

Extends the N67 mutualist idiom to the afforestation (AST) module per the
standing Nightkeeper queue: kernel determinism (+ divergence guard),
Certifier.verify as a pure repeatable read (A-2: a verdict, not an action),
registry no-mutation under audit — plus the AST theorem's own headline
invariant pinned mechanically: the site-prep lever is CUBIC, so prep=2.0
yields exactly x8 optimal density vs prep=1.0, and out-of-domain inputs
are refused (sigma/delta_mu <= 0, prep outside [1,2]).

The sweep is completed by the harmonization and restoration parity files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.canon_resolver import CanonResolver
from certification.certifier import Certifier
from modules.afforestation import AfforestationModule
from modules.afforestation.module import AST_BACKING
from modules.afforestation import engine

RESOLVER = CanonResolver(entries={AST_BACKING.doi: {
    "verified": True, "lean_module": "AfforestationStewardship"}})

INPUTS = {"sigma": 2.0, "delta_mu": 3.0, "prep": 1.5, "rate": 0.4,
          "rate_max": 1.0}


def test_kernel_compute_is_deterministic():
    m = AfforestationModule(resolver=RESOLVER)
    a = m.compute(dict(INPUTS))
    b = m.compute(dict(INPUTS))
    assert a == b
    # non-triviality guard: different site prep must diverge
    c = m.compute({**INPUTS, "prep": 1.1})
    assert c != a


def test_cubic_site_prep_lever_is_exactly_x8():
    """AST headline: prep enters cubically -> prep=2 doubles-cubed the
    optimum. Pin the exact factor so a silent exponent change reads red."""
    base = engine.optimal_density(sigma=2.0, delta_mu=3.0, prep=1.0)
    boosted = engine.optimal_density(sigma=2.0, delta_mu=3.0, prep=2.0)
    assert boosted == pytest.approx(8.0 * base)
    assert engine.site_prep_multiplier(2.0) == pytest.approx(8.0)


@pytest.mark.parametrize("bad", [
    {"sigma": 0.0}, {"sigma": -1.0}, {"delta_mu": 0.0},
    {"prep": 0.99}, {"prep": 2.01},
])
def test_out_of_domain_inputs_are_refused(bad):
    m = AfforestationModule(resolver=RESOLVER)
    with pytest.raises(ValueError):
        m.compute({**INPUTS, **bad})


def test_verify_is_repeatable_and_does_not_mutate_registry():
    m = AfforestationModule(resolver=RESOLVER)
    certifier = Certifier(resolver=RESOLVER)
    cert = certifier.issue(m, subject="stand-12", inputs=INPUTS)
    revoked_before = certifier.registry.is_revoked(cert.certificate_id)
    assert certifier.verify(cert, m, INPUTS) is True
    assert certifier.verify(cert, m, INPUTS) is True  # repeat: same verdict
    assert certifier.registry.is_revoked(cert.certificate_id) == revoked_before
    # mismatched inputs must fail the audit WITHOUT poisoning the valid path
    assert certifier.verify(cert, m, {**INPUTS, "prep": 1.2}) is False
    assert certifier.verify(cert, m, INPUTS) is True
