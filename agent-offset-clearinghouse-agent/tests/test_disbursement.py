"""agent-offset-clearinghouse — automated certified disbursement (D1-D7)."""
import pytest
from src.core import DEFAULT_VIRIDIS_WITHHOLD_BPS, build


@pytest.fixture
def core():
    return build()


async def _project(core, pid, vref="dscore:v", **kw):
    return await core.process({"action": "register_project", "project_id": pid,
                               "verification_ref": vref, **kw})


async def _credit(core, project, mass_g=100000, price=1000, vref="dscore:c"):
    # price 1000 minor/kg = 1 minor/g -> gross == grams (easy arithmetic)
    return await core.process({"action": "list_credit", "issuer": "viridis",
                               "project_id": project, "mass_g": mass_g,
                               "price_minor_per_kg": price, "verification_ref": vref})


async def _buy(core, pid, mass_g, buyer="corp"):
    return await core.process({"action": "buy_offset", "buyer": buyer,
                               "purchase_id": pid, "mass_g": mass_g})


async def _sched(core, **kw):
    return (await core.process({"action": "disbursement_schedule", **kw}))["data"]


async def test_d1_d2_split_is_conservative_and_deterministic(core):
    await _project(core, "forest", beneficiary="Andes Trust")
    await _credit(core, "forest")
    await _buy(core, "b1", 10_000)   # gross = 10_000 minor
    s = await _sched(core)
    assert s["viridis_withhold_bps"] == DEFAULT_VIRIDIS_WITHHOLD_BPS  # 1500
    line = s["lines"][0]
    assert line["viridis_withhold_minor"] == 1500     # 15% of 10000
    assert line["project_payout_minor"] == 8500       # 85%
    assert line["viridis_withhold_minor"] + line["project_payout_minor"] == 10_000  # D1
    # deterministic
    assert (await _sched(core))["lines"][0] == line


async def test_d3_withhold_configurable_and_bounded(core, monkeypatch):
    await _project(core, "forest")
    await _credit(core, "forest")
    await _buy(core, "b1", 10_000)
    monkeypatch.setenv("VIRIDIS_CONSERVATION_WITHHOLD_BPS", "2000")   # 20%
    s = await _sched(core)
    assert s["viridis_withhold_bps"] == 2000
    assert s["lines"][0]["viridis_withhold_minor"] == 2000
    # invalid / out-of-range -> falls back to default (never crashes)
    monkeypatch.setenv("VIRIDIS_CONSERVATION_WITHHOLD_BPS", "99999")
    assert (await _sched(core))["viridis_withhold_bps"] == DEFAULT_VIRIDIS_WITHHOLD_BPS
    monkeypatch.setenv("VIRIDIS_CONSERVATION_WITHHOLD_BPS", "notanumber")
    assert (await _sched(core))["viridis_withhold_bps"] == DEFAULT_VIRIDIS_WITHHOLD_BPS


async def test_d4_certify_exactly_once_and_delta_accrual(core):
    await _project(core, "forest", beneficiary="Andes Trust")
    await _credit(core, "forest")
    await _buy(core, "b1", 10_000)
    c1 = await core.process({"action": "certify_disbursement", "batch_id": "batch-1"})
    assert c1["data"]["duplicate"] is False
    assert c1["data"]["total_project_payout_minor"] == 8500
    # replay same batch_id -> original, no double disburse
    again = await core.process({"action": "certify_disbursement", "batch_id": "batch-1"})
    assert again["data"]["duplicate"] is True
    # after certification, nothing new is owed
    assert (await _sched(core))["total_owed_now_minor"] == 0
    empty = await core.process({"action": "certify_disbursement", "batch_id": "batch-2"})
    assert empty["status"] == "error"    # nothing to disburse
    # more sales accrue -> only the DELTA is certifiable next
    await _buy(core, "b2", 4000)
    s = await _sched(core)
    assert s["total_owed_now_minor"] == 4000
    c2 = await core.process({"action": "certify_disbursement", "batch_id": "batch-3"})
    assert c2["data"]["lines"][0]["owed_minor"] == 4000


async def test_d5_certificates_hash_chained_and_verifiable(core):
    await _project(core, "forest")
    await _credit(core, "forest")
    await _buy(core, "b1", 5000)
    await core.process({"action": "certify_disbursement", "batch_id": "b-1"})
    await _buy(core, "b2", 3000)
    await core.process({"action": "certify_disbursement", "batch_id": "b-2"})
    v = await core.process({"action": "verify_disbursement"})
    assert v["data"]["valid"] and v["data"]["batches"] == 2
    assert v["data"]["conserved"] is True
    # tamper -> detected
    core._disbursements[0]["total_project_payout_minor"] = 999999
    v2 = await core.process({"action": "verify_disbursement"})
    assert v2["data"]["valid"] is False and v2["data"]["broken_at_index"] == 0


async def test_d6_only_verified_projects_are_paid(core):
    # Funded but NOT registered -> pending_registration, never certified.
    await _credit(core, "wild-unverified")
    await _buy(core, "b1", 6000)
    s = await _sched(core)
    assert s["ready_count"] == 0
    assert any(p["project_id"] == "wild-unverified"
               and p["status"] == "pending_registration"
               for p in s["pending_registration"])
    bad = await core.process({"action": "certify_disbursement", "batch_id": "x"})
    assert bad["status"] == "error"     # nothing certifiable
    # register it -> now ready and payable
    await _project(core, "wild-unverified", beneficiary="Mangrove Trust")
    s2 = await _sched(core)
    assert s2["ready_count"] == 1
    ok = await core.process({"action": "certify_disbursement", "batch_id": "y"})
    assert ok["status"] == "ok" and ok["data"]["lines"][0]["project_payout_minor"] == 5100


async def test_d7_whole_book_conservation(core):
    await _project(core, "a", beneficiary="A")
    await _project(core, "b", beneficiary="B")
    await _credit(core, "a", price=1000)
    await _credit(core, "b", price=1000)
    await _buy(core, "pa", 10_000)
    await _buy(core, "pb", 6000, buyer="corp2")
    cert = await core.process({"action": "certify_disbursement", "batch_id": "all"})
    d = cert["data"]
    assert d["total_disbursed_minor"] == d["total_viridis_withhold_minor"] + d["total_project_payout_minor"]
    assert d["total_disbursed_minor"] == 16_000    # 10000 + 6000 gross
    assert d["total_viridis_withhold_minor"] == 2400   # 15% of 16000
    v = await core.process({"action": "verify_disbursement"})
    assert v["data"]["conserved"] is True
