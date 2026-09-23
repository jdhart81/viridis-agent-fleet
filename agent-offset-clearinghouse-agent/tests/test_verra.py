"""agent-offset-clearinghouse — Verra registry / trading (VR1-VR5)."""
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _verra_credit(core, mass_g=100000, price=1000, serial="VCS-1477-11111-22222",
                        vcs="VCS1477", vintage="2024"):
    return await core.process({"action": "list_credit", "issuer": "verra-broker",
                               "project_id": "andes-cloud-forest", "mass_g": mass_g,
                               "price_minor_per_kg": price,
                               "verification_ref": "dscore:zenodo.19317982/andes",
                               "registry": "verra", "vcs_project_id": vcs,
                               "vintage": vintage, "serial_number": serial,
                               "methodology": "VM0007"})


async def test_vr1_verra_requires_provenance(core):
    # Missing serial -> rejected
    bad = await core.process({"action": "list_credit", "issuer": "b", "project_id": "p",
                              "mass_g": 1000, "price_minor_per_kg": 100,
                              "verification_ref": "dscore:x", "registry": "verra",
                              "vcs_project_id": "VCS1", "vintage": "2024"})
    assert bad["status"] == "error" and bad["field"] == "serial_number"
    # unsupported registry -> rejected
    bad2 = await core.process({"action": "list_credit", "issuer": "b", "project_id": "p",
                               "mass_g": 1000, "price_minor_per_kg": 100,
                               "verification_ref": "dscore:x",
                               "registry": "goldstandard"})
    assert bad2["status"] == "error" and bad2["field"] == "registry"
    # complete Verra provenance -> accepted
    ok = await _verra_credit(core)
    assert ok["status"] == "ok"
    assert ok["data"]["registry"] == "verra"
    assert ok["data"]["serial_number"] == "VCS-1477-11111-22222"


async def test_vr2_provenance_in_retirement_certificate(core):
    await _verra_credit(core)
    buy = await core.process({"action": "buy_offset", "buyer": "corp",
                              "purchase_id": "sale-1", "mass_g": 5000})
    fill = buy["data"]["fills"][0]
    assert fill["registry"] == "verra"
    assert fill["vcs_project_id"] == "VCS1477"
    assert fill["serial_number"] == "VCS-1477-11111-22222"
    # the certificate is content-addressed over the fills -> tamper-evident
    cert = await core.process({"action": "verify_certificate",
                               "certificate": buy["data"]})
    assert cert["data"]["valid"] is True


async def test_vr3_viridis_take_on_verra_trade(core, monkeypatch):
    await core.process({"action": "register_project",
                        "project_id": "andes-cloud-forest",
                        "verification_ref": "verra:VCS1477",
                        "beneficiary": "Andes Trust"})
    await _verra_credit(core, price=1000)   # 1 minor/g
    await core.process({"action": "buy_offset", "buyer": "corp",
                        "purchase_id": "sale-1", "mass_g": 10000})  # gross 10000
    sched = await core.process({"action": "disbursement_schedule",
                                "project_id": "andes-cloud-forest"})
    line = sched["data"]["lines"][0]
    assert line["viridis_withhold_minor"] == 1500   # 15% take
    assert line["project_payout_minor"] == 8500     # project keeps 85%


async def test_vr4_backward_compatible_generic_supply(core):
    # No registry fields -> behaves exactly as before
    r = await core.process({"action": "list_credit", "issuer": "viridis",
                            "project_id": "wild", "mass_g": 1000,
                            "price_minor_per_kg": 500, "verification_ref": "dscore:x"})
    assert r["status"] == "ok" and r["data"]["registry"] == ""
    buy = await core.process({"action": "buy_offset", "buyer": "b",
                              "purchase_id": "p", "mass_g": 500})
    assert buy["status"] == "ok"
    assert buy["data"]["fills"][0]["registry"] == ""


async def test_vr5_verra_supply_surface(core):
    await _verra_credit(core, mass_g=100000)
    await core.process({"action": "list_credit", "issuer": "viridis",
                        "project_id": "generic", "mass_g": 5000,
                        "price_minor_per_kg": 100, "verification_ref": "dscore:y"})
    supply = await core.process({"action": "verra_supply"})
    d = supply["data"]
    assert d["registry"] == "verra" and d["count"] == 1   # only Verra credits
    assert d["available_g"] == 100000
    assert d["viridis_take_bps"] == 1500
    assert d["credits"][0]["vcs_project_id"] == "VCS1477"
