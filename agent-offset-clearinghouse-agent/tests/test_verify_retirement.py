"""agent-offset-clearinghouse — verify_retirement (O13 / x402-C C4)."""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _credit(core, mass_g=1000, price=500, vref="dscore:zenodo.19317982/s7"):
    return await core.process({"action": "list_credit", "issuer": "viridis",
                               "project_id": "forest-1", "mass_g": mass_g,
                               "price_minor_per_kg": price,
                               "verification_ref": vref})


async def _buy(core, pid, mass_g, buyer="agent-x"):
    return await core.process({"action": "buy_offset", "buyer": buyer,
                               "purchase_id": pid, "mass_g": mass_g})


async def test_o13_covered_when_retirement_meets_requirement(core):
    await _credit(core, mass_g=1000)
    await _buy(core, "ret-1", 200)
    r = await core.process({"action": "verify_retirement",
                            "purchase_id": "ret-1", "required_g": 150})
    assert r["status"] == "ok"
    d = r["data"]
    assert d["covered"] is True and d["retired_g"] == 200
    assert d["shortfall_g"] == 0
    assert d["credits"] and d["credits"][0]["mass_g"] == 200
    assert d["certificate_hash"]


async def test_o13_shortfall_when_under_covered(core):
    await _credit(core, mass_g=1000)
    await _buy(core, "ret-2", 100)
    r = await core.process({"action": "verify_retirement",
                            "purchase_id": "ret-2", "required_g": 250})
    d = r["data"]
    assert d["covered"] is False and d["shortfall_g"] == 150


async def test_o13_read_only_and_errors(core):
    await _credit(core, mass_g=1000)
    await _buy(core, "ret-3", 300)
    book_before = await core.process({"action": "book"})
    for _ in range(3):
        await core.process({"action": "verify_retirement",
                            "purchase_id": "ret-3", "required_g": 100})
    book_after = await core.process({"action": "book"})
    assert book_before["data"] == book_after["data"]        # read-only
    # unknown purchase -> error, never crash (O8)
    bad = await core.process({"action": "verify_retirement",
                              "purchase_id": "nope", "required_g": 1})
    assert bad["status"] == "error" and bad["field"] == "purchase_id"
    # required_g must be a non-negative int
    neg = await core.process({"action": "verify_retirement",
                              "purchase_id": "ret-3", "required_g": -5})
    assert neg["status"] == "error" and neg["field"] == "required_g"
    # required_g defaults to 0 -> trivially covered
    zero = await core.process({"action": "verify_retirement",
                               "purchase_id": "ret-3"})
    assert zero["data"]["covered"] is True
