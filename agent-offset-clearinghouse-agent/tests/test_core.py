"""Invariant tests for agent-offset-clearinghouse-agent (O1-O8) + fleet contract."""
import math
import pytest
from src.core import build


@pytest.fixture
def core():
    return build()


async def _credit(core, mass_g=1000, price=500, project="forest-1", vref="dscore:abc"):
    return await core.process({"action": "list_credit", "issuer": "viridis",
                               "project_id": project, "mass_g": mass_g,
                               "price_minor_per_kg": price,
                               "verification_ref": vref})


async def _buy(core, pid, mass_g, buyer="agent-x"):
    return await core.process({"action": "buy_offset", "buyer": buyer,
                               "purchase_id": pid, "mass_g": mass_g})


# --- O1 conservation of mass -------------------------------------------------- #
async def test_O1_mass_conserved(core):
    await _credit(core, mass_g=1000)
    await _credit(core, mass_g=500, project="wetland-2")
    await _buy(core, "p1", 700)
    book = await core.process({"action": "book"})
    t = book["data"]["totals"]
    assert t["listed_g"] == 1500
    assert t["retired_g"] == 700
    assert t["available_g"] + t["retired_g"] == t["listed_g"]
    for c in book["data"]["credits"]:
        assert c["available_g"] + c["retired_g"] == c["listed_g"]
        assert c["retired_g"] <= c["listed_g"]


# --- O2 no double-retirement ---------------------------------------------------- #
async def test_O2_idempotent_purchase_never_double_retires(core):
    await _credit(core, mass_g=1000)
    r1 = await _buy(core, "dup", 400)
    r2 = await _buy(core, "dup", 400)  # retry
    assert r2["data"]["duplicate"] is True
    assert r2["data"]["certificate_hash"] == r1["data"]["certificate_hash"]
    book = await core.process({"action": "book"})
    assert book["data"]["totals"]["retired_g"] == 400  # once


async def test_O2_oversubscription_rejected(core):
    await _credit(core, mass_g=100)
    r = await _buy(core, "p1", 200)
    assert r["status"] == "error" and "insufficient" in r["message"]
    book = await core.process({"action": "book"})
    assert book["data"]["totals"]["retired_g"] == 0  # nothing partially retired


# --- O3 deterministic cheapest-first matching -------------------------------------- #
async def test_O3_cheapest_first_deterministic(core):
    await _credit(core, mass_g=1000, price=900, project="expensive")
    await _credit(core, mass_g=300, price=200, project="cheap")
    await _credit(core, mass_g=300, price=200, project="cheap-later")  # same price, later
    r = await _buy(core, "p1", 500)
    fills = r["data"]["fills"]
    assert fills[0]["project_id"] == "cheap" and fills[0]["mass_g"] == 300
    assert fills[1]["project_id"] == "cheap-later" and fills[1]["mass_g"] == 200
    core2 = build()
    for m, p, proj in ((1000, 900, "expensive"), (300, 200, "cheap"),
                       (300, 200, "cheap-later")):
        await core2.process({"action": "list_credit", "issuer": "viridis",
                             "project_id": proj, "mass_g": m,
                             "price_minor_per_kg": p, "verification_ref": "dscore:abc"})
    r2 = await core2.process({"action": "buy_offset", "buyer": "agent-x",
                              "purchase_id": "p1", "mass_g": 500})
    assert [(f["project_id"], f["mass_g"]) for f in r2["data"]["fills"]] == \
           [(f["project_id"], f["mass_g"]) for f in fills]


# --- O4 content-addressed certificates ----------------------------------------------- #
async def test_O4_certificate_verifies_and_detects_forgery(core):
    await _credit(core, mass_g=1000)
    r = await _buy(core, "p1", 250)
    cert = r["data"]
    v = await core.process({"action": "verify_certificate", "certificate": cert})
    assert v["data"]["valid"] is True
    forged = {**cert, "mass_g": 999999}
    v2 = await core.process({"action": "verify_certificate", "certificate": forged})
    assert v2["data"]["valid"] is False


# --- O5 exact net position -------------------------------------------------------------- #
async def test_O5_net_position_exact(core):
    await _credit(core, mass_g=1000)
    await _buy(core, "p1", 300, buyer="agent-x")
    await _buy(core, "p2", 200, buyer="agent-x")
    np = await core.process({"action": "net_position", "buyer": "agent-x",
                             "emitted_g": 600})
    d = np["data"]
    assert d["retired_g"] == 500 and d["net_g"] == 100
    assert d["carbon_accountable"] is False
    np2 = await core.process({"action": "net_position", "buyer": "agent-x",
                              "emitted_g": 400})
    assert np2["data"]["carbon_accountable"] is True


# --- O6 price integrity -------------------------------------------------------------------- #
async def test_O6_price_ceil_integer_minor(core):
    await _credit(core, mass_g=1000, price=333)  # 0.25 kg * 333 = 83.25 -> 84
    r = await _buy(core, "p1", 250)
    fill = r["data"]["fills"][0]
    assert fill["cost_minor"] == math.ceil(0.25 * 333) == 84
    assert isinstance(fill["cost_minor"], int)
    assert r["data"]["total_cost_minor"] == sum(f["cost_minor"]
                                                for f in r["data"]["fills"])


# --- O7 verified supply only ------------------------------------------------------------------ #
async def test_O7_unverified_credit_rejected(core):
    r = await core.process({"action": "list_credit", "issuer": "sketchy",
                            "project_id": "trust-me", "mass_g": 1000,
                            "price_minor_per_kg": 1})
    assert r["status"] == "error" and r["field"] == "verification_ref"
    r2 = await core.process({"action": "list_credit", "issuer": "sketchy",
                             "project_id": "trust-me", "mass_g": 1000,
                             "price_minor_per_kg": 1, "verification_ref": ""})
    assert r2["status"] == "error"


async def test_O7_sub_floor_and_non_dscore_listings_rejected(core):
    penny = await core.process({
        "action": "list_credit", "issuer": "viridis-land-trust",
        "project_id": "synthetic-penny", "mass_g": 1_000_000,
        "price_minor_per_kg": 1,
        "verification_ref": "dscore:synthetic",
    })
    assert penny["status"] == "error"
    assert penny["field"] == "price_minor_per_kg"
    fake_verra = await core.process({
        "action": "list_credit", "issuer": "verra-broker",
        "project_id": "timestamp-serial", "mass_g": 1_000_000,
        "price_minor_per_kg": 1_200,
        "verification_ref": "verra:VCS-1477-1784148092-A",
        "registry": "verra", "vcs_project_id": "VCS1477",
        "vintage": "2024", "serial_number": "VCS-1477-1784148092-A",
    })
    assert fake_verra["status"] == "error"
    assert fake_verra["field"] == "verification_ref"


# --- O8 unknown ids ------------------------------------------------------------------------------ #
async def test_O8_unknown_purchase_error_envelope(core):
    r = await core.process({"action": "get_purchase", "purchase_id": "ghost"})
    assert r["status"] == "error" and r["field"] == "purchase_id"
    for key in ("error_type", "field", "value", "constraint", "message", "timestamp"):
        assert key in r


# --- fleet contract --------------------------------------------------------------------------------- #
async def test_contract_never_raises_and_unknown_action(core):
    for payload in [{}, {"action": None}, {"action": "nope"}, "not-a-dict", 42]:
        r = await core.process(payload)
        assert isinstance(r, dict) and r["status"] == "error"


async def test_contract_describe_health_consistent(core):
    d = core.describe()
    h = await core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"] and d["a2a_role"] == "offsets"
    assert set(h) >= {"status", "agent", "version", "timestamp", "checks"}


# --- O9 budget purchases never overspend ------------------------------------------------- #
async def test_O9_budget_purchase_within_budget_and_maximal(core):
    await _credit(core, mass_g=2000, price=500, project="cheap")     # 0.5 minor/g
    await _credit(core, mass_g=2000, price=1500, project="dear")     # 1.5 minor/g
    r = await core.process({"action": "buy_offset_budget", "buyer": "energyai",
                            "purchase_id": "b1", "budget_minor": 1750})
    assert r["status"] == "ok"
    d = r["data"]
    assert d["total_cost_minor"] <= 1750                              # O9
    # cheapest-first: all 2000g of 'cheap' (cost 1000) then 500g of 'dear' (cost 750)
    assert [f["project_id"] for f in d["fills"]] == ["cheap", "dear"]
    assert d["mass_g"] == 2500 and d["total_cost_minor"] == 1750
    # certificate is real and verifiable (O4 path shared with buy_offset)
    v = await core.process({"action": "verify_certificate",
                            "certificate": {k: d[k] for k in
                                            ("purchase_id", "buyer", "mass_g", "fills",
                                             "total_cost_minor", "retired_at",
                                             "certificate_hash")}})
    assert v["data"]["valid"] is True


async def test_O9_budget_idempotent_on_purchase_id(core):
    await _credit(core, mass_g=1000, price=1000)
    r1 = await core.process({"action": "buy_offset_budget", "buyer": "energyai",
                             "purchase_id": "b2", "budget_minor": 500})
    r2 = await core.process({"action": "buy_offset_budget", "buyer": "energyai",
                             "purchase_id": "b2", "budget_minor": 500})
    assert r2["data"]["duplicate"] is True
    assert r2["data"]["mass_g"] == r1["data"]["mass_g"]
    book = await core.process({"action": "book"})
    assert book["data"]["totals"]["retired_g"] == r1["data"]["mass_g"]  # no double retire


async def test_O9_free_credit_retired_entirely(core):
    rejected = await _credit(core, mass_g=300, price=0, project="donated")
    assert rejected["status"] == "error"
    await _credit(core, mass_g=1000, price=1000, project="paid")
    r = await core.process({"action": "buy_offset_budget", "buyer": "energyai",
                            "purchase_id": "b3", "budget_minor": 100})
    fills = {f["project_id"]: f for f in r["data"]["fills"]}
    assert "donated" not in fills
    assert r["data"]["total_cost_minor"] <= 100


async def test_O14_delist_credit_excludes_fill_and_retains_history(core):
    first = await _credit(core, mass_g=1000, price=200, project="bad")
    second = await _credit(core, mass_g=1000, price=900, project="hdfm")
    credit_id = first["data"]["credit_id"]
    removed = await core.process({
        "action": "delist_credit", "credit_id": credit_id,
        "reason": "synthetic production smoke listing",
    })
    assert removed["status"] == "ok"
    assert removed["data"]["listing_status"] == "delisted"
    preview = await core.process({
        "action": "buy_offset_budget", "buyer": "viridis:energyai",
        "purchase_id": "dry-delist", "budget_minor": 100,
        "dry_run": True,
    })
    assert [fill["project_id"] for fill in preview["data"]["fills"]] == ["hdfm"]
    book = await core.process({"action": "book"})
    bad = next(c for c in book["data"]["credits"]
               if c["credit_id"] == credit_id)
    assert bad["listing_status"] == "delisted"
    assert book["data"]["totals"]["delisted_available_g"] == 1000
    replay = await core.process({
        "action": "delist_credit", "credit_id": credit_id,
        "reason": "retry",
    })
    assert replay["data"]["duplicate"] is True


# --- O10 dry_run mutates nothing ------------------------------------------------------------ #
async def test_O10_dry_run_no_mutation_both_actions(core):
    await _credit(core, mass_g=1000, price=1000)
    before = await core.process({"action": "book"})
    d1 = await core.process({"action": "buy_offset", "buyer": "energyai",
                             "purchase_id": "dry1", "mass_g": 400, "dry_run": True})
    d2 = await core.process({"action": "buy_offset_budget", "buyer": "energyai",
                             "purchase_id": "dry2", "budget_minor": 400, "dry_run": True})
    after = await core.process({"action": "book"})
    assert d1["data"]["dry_run"] is True and d2["data"]["dry_run"] is True
    assert d1["data"]["fills"] and d2["data"]["fills"]                # real preview
    assert before["data"] == after["data"]                            # book unchanged
    # dry runs are never idempotency-recorded: a REAL purchase under the same id works
    real = await core.process({"action": "buy_offset", "buyer": "energyai",
                               "purchase_id": "dry1", "mass_g": 400})
    assert real["data"]["duplicate"] is False
    np_ = await core.process({"action": "net_position", "buyer": "energyai",
                              "emitted_g": 0})
    assert np_["data"]["retired_g"] == 400                            # only the real one


# --- O11 settlement_batch read-only + exact ---------------------------------------------- #
async def test_O11_settlement_batch_exact_and_readonly(core):
    await _credit(core, mass_g=5000, price=1000)
    await _buy(core, "s1", 1000, buyer="energyai")
    await _buy(core, "s2", 500, buyer="energyai")
    await _buy(core, "other", 700, buyer="someone-else")
    await core.process({"action": "buy_offset_budget", "buyer": "energyai",
                        "purchase_id": "sdry", "budget_minor": 100, "dry_run": True})
    before = await core.process({"action": "book"})
    b = await core.process({"action": "settlement_batch", "buyer": "energyai"})
    after = await core.process({"action": "book"})
    assert before["data"] == after["data"]                            # read-only
    t = b["data"]["totals"]
    assert t["purchases"] == 2 and t["mass_g"] == 1500                # dry + others excluded
    assert t["cost_minor"] == sum(p["total_cost_minor"] for p in b["data"]["purchases"])
    # 'since' filter: nothing before a future timestamp
    b2 = await core.process({"action": "settlement_batch", "buyer": "energyai",
                             "since": "2999-01-01T00:00:00+00:00"})
    assert b2["data"]["totals"]["purchases"] == 0


# --- O12 dust budget rejected --------------------------------------------------------------- #
async def test_O12_dust_budget_error_envelope(core):
    await _credit(core, mass_g=1000, price=100000)  # 100 minor per gram
    r = await core.process({"action": "buy_offset_budget", "buyer": "energyai",
                            "purchase_id": "dust", "budget_minor": 5})
    assert r["status"] == "error" and r["field"] == "budget_minor"
    empty = build_empty = None  # noqa: F841 (explicitness only)
    # empty book also rejects
    from src.core import build as _build
    fresh = _build()
    r2 = await fresh.process({"action": "buy_offset_budget", "buyer": "x",
                              "purchase_id": "dust2", "budget_minor": 5})
    assert r2["status"] == "error"
