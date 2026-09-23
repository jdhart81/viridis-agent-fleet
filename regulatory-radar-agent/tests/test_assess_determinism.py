"""Determinism pin for the paid `assess` path (strengthens G4).

regulatory-radar is the fleet's only confirmed 402->escrow converter, so its paid
compliance assessment is a product buyers pay for. That output must be reproducible:
two identical assess calls must yield byte-identical results, modulo the embedded
`assessed_at` timestamp. This pins idempotency/determinism (the N63 fitness signal)
without adding a new numbered invariant. Additive; nothing in core changes.
"""

import re
import pytest
from src.core import RegulatoryRadarCore


@pytest.fixture
def core():
    return RegulatoryRadarCore()


_TS = re.compile(r"datetime\.datetime\([^)]*\)")


def _normalize(result: str) -> str:
    # The only intended run-to-run variation is the assessment timestamp.
    return _TS.sub("datetime.datetime(<ts>)", result)


ASSESS = {
    "action": "assess", "company_name": "ACME",
    "sector": "manufacturing", "jurisdiction": "EU",
}


async def test_assess_is_deterministic_modulo_timestamp(core):
    r1 = await core.process(dict(ASSESS))
    r2 = await core.process(dict(ASSESS))
    assert r1["status"] == "success" and r2["status"] == "success"
    assert _normalize(r1["result"]) == _normalize(r2["result"]), \
        "identical assess inputs must produce identical results (modulo timestamp)"


async def test_assess_determinism_is_not_trivial(core):
    # Guard the pin: genuinely different inputs must produce different assessments,
    # so the determinism check above cannot pass by collapsing everything to a constant.
    r1 = await core.process(dict(ASSESS))
    r_other = await core.process({
        "action": "assess", "company_name": "ACME",
        "sector": "forestry", "jurisdiction": "US",
    })
    assert r1["status"] == "success" and r_other["status"] == "success"
    assert _normalize(r1["result"]) != _normalize(r_other["result"])
