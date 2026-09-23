"""agent-offset-clearinghouse — restoration-project funding (P1-P6)."""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _project(core, pid="restoration-site-7", vref="dscore:zenodo.19317982/s7", **kw):
    return await core.process({"action": "register_project", "project_id": pid,
                               "verification_ref": vref, **kw})


async def _credit(core, project, mass_g=1000, price=500, vref="dscore:abc"):
    return await core.process({"action": "list_credit", "issuer": "viridis",
                               "project_id": project, "mass_g": mass_g,
                               "price_minor_per_kg": price, "verification_ref": vref})


async def _buy(core, pid, mass_g, buyer="agent-x"):
    return await core.process({"action": "buy_offset", "buyer": buyer,
                               "purchase_id": pid, "mass_g": mass_g})


async def test_p1_register_requires_verification_and_is_immutable(core):
    bad = await core.process({"action": "register_project", "project_id": "p1"})
    assert bad["status"] == "error" and bad["field"] == "verification_ref"
    r = await _project(core, "p1", name="Kelp Forest", beneficiary="Coastal Trust")
    assert r["status"] == "ok" and r["data"]["duplicate"] is False
    # identical re-registration is idempotent
    again = await _project(core, "p1", name="Kelp Forest", beneficiary="Coastal Trust")
    assert again["data"]["duplicate"] is True
    # conflicting re-registration is rejected
    conflict = await _project(core, "p1", name="Different Name")
    assert conflict["status"] == "error" and conflict["field"] == "project_id"


async def test_p2_funding_attribution_is_exact(core):
    await _project(core, "forest-1", beneficiary="Andes Trust")
    await _credit(core, "forest-1", mass_g=10_000, price=500)   # 0.5 minor/g
    await _buy(core, "buy-1", 2000)     # cost = ceil(2 kg * 500) = 1000
    await _buy(core, "buy-2", 3000)     # cost = ceil(3 kg * 500) = 1500
    f = await core.process({"action": "project_funding", "project_id": "forest-1"})
    d = f["data"]
    assert d["retired_g"] == 5000
    assert d["gross_proceeds_minor"] == 2500      # 1000 + 1500, exact
    assert d["retirements"] == 2
    assert d["beneficiary"] == "Andes Trust"


async def test_p3_read_only(core):
    await _project(core, "forest-1")
    await _credit(core, "forest-1", mass_g=5000)
    await _buy(core, "b1", 1000)
    book_before = await core.process({"action": "book"})
    for _ in range(3):
        await core.process({"action": "project_funding"})
        await core.process({"action": "list_projects"})
    book_after = await core.process({"action": "book"})
    assert book_before["data"] == book_after["data"]


async def test_p4_backward_compatible_unregistered_project_still_attributed(core):
    # No register_project — retire against a bare project_id string.
    await _credit(core, "wild-mangrove", mass_g=4000, price=300)
    await _buy(core, "b1", 1000)        # cost = ceil(1 kg * 300) = 300
    f = await core.process({"action": "project_funding", "project_id": "wild-mangrove"})
    assert f["data"]["registered"] is False
    assert f["data"]["retired_g"] == 1000 and f["data"]["gross_proceeds_minor"] == 300


async def test_p5_registered_but_unfunded_and_unknown_report_zero(core):
    await _project(core, "future-reef", beneficiary="Reef Foundation")
    f = await core.process({"action": "project_funding", "project_id": "future-reef"})
    assert f["status"] == "ok" and f["data"]["retired_g"] == 0
    assert f["data"]["gross_proceeds_minor"] == 0 and f["data"]["registered"] is True
    unknown = await core.process({"action": "project_funding", "project_id": "nope"})
    assert unknown["status"] == "ok" and unknown["data"]["retired_g"] == 0
    # registered-but-unfunded still appears in the full ledger
    all_f = await core.process({"action": "project_funding"})
    assert any(p["project_id"] == "future-reef" for p in all_f["data"]["projects"])


async def test_p6_conservation_of_proceeds(core):
    await _credit(core, "forest-1", mass_g=10_000, price=500)
    await _credit(core, "wetland-2", mass_g=10_000, price=700)
    await _buy(core, "b1", 3000)
    await _buy(core, "b2", 4000, buyer="agent-y")
    # dry_run must NOT be attributed (P2/O10)
    await core.process({"action": "buy_offset", "buyer": "agent-z",
                        "purchase_id": "dry", "mass_g": 1000, "dry_run": True})
    funding = await core.process({"action": "project_funding"})["data"] \
        if False else (await core.process({"action": "project_funding"}))["data"]
    total_owed = funding["total_owed_to_projects_minor"]
    # equals the exact sum of real purchases' total_cost_minor
    settled = 0
    for pid in ("b1", "b2"):
        p = await core.process({"action": "get_purchase", "purchase_id": pid})
        settled += p["data"]["total_cost_minor"]
    assert total_owed == settled
