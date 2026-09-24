"""Regression pin — the default CanonResolver() must be self-contained.

viridisos ships a canon snapshot under _canon/. The default resolver has to find it
even when the RESEARCH_PIPELINE_v2 tree is absent (self-contained deploys / fresh VMs).
Without this, published-theorem modules silently drop to BLOCKED and the live-canon
suite goes red — the exact regression this pins against. Additive; A-1 unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.canon_resolver import CanonResolver, _DEFAULT_INDEX

# Forest Nucleation Theorem — a PUBLISHED theorem present in the shipped canon snapshot.
FNT_DOI = "10.5281/zenodo.20982979"
ABSENT_DOI = "10.5281/zenodo.NOT-IN-CANON"


def test_default_index_resolves_to_an_existing_file():
    # The default must point at a canon index that actually exists on disk,
    # so a plain CanonResolver() is never silently empty.
    assert _DEFAULT_INDEX.exists(), f"default canon index missing: {_DEFAULT_INDEX}"


def test_default_resolver_gate_passes_published_doi():
    # Self-contained certification: no fixture, no research pipeline tree.
    assert CanonResolver().is_gate_passed(FNT_DOI) is True


def test_default_resolver_still_enforces_A1_for_absent_doi():
    # A-1 is not weakened by the fallback: an unlisted DOI does not gate-pass.
    assert CanonResolver().is_gate_passed(ABSENT_DOI) is False
