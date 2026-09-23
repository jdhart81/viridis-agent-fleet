"""agent-offset-clearinghouse — Verra retirement-record generator (VR6)."""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _verra_credit(core, price=100, serial="VCS-1477-11111-22222",
                        vcs="VCS1477", vintage="2024", meth="VM0047"):
    return await core.process({"action": "list_credit", "issuer": "viridis-conservation",
                               "project_id": "andes-reforestation", "mass_g": 5_000_000,
                               "price_minor_per_kg": price,
                               "verification_ref": "dscore:zenodo.19317982/andes",
                               "registry": "verra", "vcs_project_id": vcs,
                               "vintage": vintage, "serial_number": serial,
                               "methodology": meth})


async def test_vr6_generates_submittable_record(core):
    await _verra_credit(core)
    # retire 2 tonnes worth (2,000,000 g)
    await core.process({"action": "buy_offset", "buyer": "acme-corp",
                        "purchase_id": "sale-1", "mass_g": 2_000_000})
    r = await core.process({"action": "verra_retirement_record",
                            "purchase_id": "sale-1"})
    assert r["status"] == "ok"
    d = r["data"]
    assert d["registry"] == "verra" and d["submission_status"] == "ready_to_submit"
    rec = d["records"][0]
    assert rec["vcs_project_id"] == "VCS1477"
    assert rec["serial_number"] == "VCS-1477-11111-22222"
    assert rec["methodology"] == "VM0047"
    assert rec["quantity_tco2e"] == 2.0            # 2,000,000 g = 2 tCO2e
    assert rec["retirement_beneficiary"] == "acme-corp"
    assert "registry.verra.org" in rec["public_cross_reference"]
    # VR6 conservation: record quantities sum to the retirement's Verra mass
    assert d["total_quantity_g"] == 2_000_000


async def test_vr6_excludes_non_verra_and_errors_when_none(core):
    # a generic (non-Verra) credit
    await core.process({"action": "list_credit", "issuer": "viridis",
                        "project_id": "generic", "mass_g": 5000,
                        "price_minor_per_kg": 100, "verification_ref": "dscore:x"})
    await core.process({"action": "buy_offset", "buyer": "b",
                        "purchase_id": "generic-sale", "mass_g": 1000})
    r = await core.process({"action": "verra_retirement_record",
                            "purchase_id": "generic-sale"})
    assert r["status"] == "error"    # no Verra fills -> nothing to submit
    # unknown purchase
    bad = await core.process({"action": "verra_retirement_record",
                              "purchase_id": "nope"})
    assert bad["status"] == "error" and bad["field"] == "purchase_id"


async def test_vr6_read_only(core):
    await _verra_credit(core)
    await core.process({"action": "buy_offset", "buyer": "acme",
                        "purchase_id": "s1", "mass_g": 1_000_000})
    before = await core.process({"action": "book"})
    for _ in range(3):
        await core.process({"action": "verra_retirement_record", "purchase_id": "s1"})
    after = await core.process({"action": "book"})
    assert before["data"] == after["data"]


async def test_vr6_custom_reason(core):
    await _verra_credit(core)
    await core.process({"action": "buy_offset", "buyer": "acme",
                        "purchase_id": "s1", "mass_g": 1_000_000})
    r = await core.process({"action": "verra_retirement_record", "purchase_id": "s1",
                            "retirement_reason": "CSRD FY2026 compliance"})
    assert r["data"]["records"][0]["retirement_reason"] == "CSRD FY2026 compliance"
