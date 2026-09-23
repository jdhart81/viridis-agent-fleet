"""Purity + determinism pins for restoration certify->verify (N70).

Completes the ViridisOS verify-purity sweep by extending the mutualist,
afforestation, and harmonization idiom to the restoration (FNT) module:
kernel determinism with a divergence guard, Certifier.verify as a pure
repeatable read, registry no-mutation under audit, and the theorem's headline
threshold/cubic-nucleus contract pinned mechanically.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from certification.certifier import Certifier
from modules.restoration import RestorationModule
from modules.restoration import engine
from modules.restoration.module import FNT_BACKING
from runtime.canon_resolver import CanonResolver

RESOLVER = CanonResolver(entries={FNT_BACKING.doi: {
    "verified": True, "lean_module": "ForestNucleation"}})

INPUTS = {"sigma": 1.5, "delta_mu": 1.0}


def test_kernel_compute_is_deterministic():
    module = RestorationModule(resolver=RESOLVER)
    first = module.compute(dict(INPUTS))
    second = module.compute(dict(INPUTS))
    assert first == second
    assert module.compute({**INPUTS, "sigma": 2.0}) != first


def test_fnt_thresholds_and_cubic_nucleus_are_exact():
    """FNT headline: n* = theta cubed and broadcast fails only above 1."""
    assert engine.critical_nucleus(sigma=2.0, delta_mu=1.0) == pytest.approx(8.0)
    assert engine.design(sigma=0.5, delta_mu=1.0) == {
        "nucleation_number": 0.5,
        "critical_nucleus_n_star": 0.125,
        "recommendation": "GREEN",
        "broadcast_fails": False,
    }
    assert engine.design(sigma=0.500001, delta_mu=1.0)[
        "recommendation"] == "AMBER"
    at_one = engine.design(sigma=1.0, delta_mu=1.0)
    assert at_one["recommendation"] == "AMBER"
    assert at_one["broadcast_fails"] is False
    over_one = engine.design(sigma=1.000001, delta_mu=1.0)
    assert over_one["recommendation"] == "RED"
    assert over_one["broadcast_fails"] is True


@pytest.mark.parametrize("bad", [
    {"sigma": -0.000001},
    {"delta_mu": 0.0},
    {"delta_mu": -1.0},
])
def test_out_of_domain_inputs_are_refused(bad):
    module = RestorationModule(resolver=RESOLVER)
    with pytest.raises(ValueError):
        module.compute({**INPUTS, **bad})


def test_verify_is_repeatable_and_does_not_mutate_registry():
    module = RestorationModule(resolver=RESOLVER)
    certifier = Certifier(resolver=RESOLVER)
    certificate = certifier.issue(
        module, subject="restoration-site-9", inputs=INPUTS)
    revoked_before = certifier.registry.is_revoked(
        certificate.certificate_id)

    assert certifier.verify(certificate, module, INPUTS) is True
    assert certifier.verify(certificate, module, INPUTS) is True
    assert certifier.registry.is_revoked(
        certificate.certificate_id) == revoked_before

    wrong = {**INPUTS, "sigma": 1.75}
    assert certifier.verify(certificate, module, wrong) is False
    assert certifier.verify(certificate, module, wrong) is False
    assert certifier.verify(certificate, module, INPUTS) is True
