"""Invariant tests for agent-compute-ledger-agent (L1-L8) + fleet contract."""
import math
import pytest
from src.core import build, KB, LN2, J_PER_KWH, _GENESIS

AUDIT_DIGEST = "a" * 64
FACTOR_DIGEST = "b" * 64


@pytest.fixture
def core():
    return build()


async def _work(core, eid, power_w=100.0, duration_s=60.0, **over):
    return await core.process({"action": "record_work", "agent_id": "agent-x",
                               "entry_id": eid, "power_w": power_w,
                               "duration_s": duration_s, **over})


async def _inventory(core, iid, agent_id="ghg-ledger-agent", mass_g=123456,
                     **over):
    payload = {"action": "record_inventory", "agent_id": agent_id,
               "inventory_id": iid, "mass_g": mass_g,
               "content_digest": AUDIT_DIGEST,
               "factor_pack_version": "2026.07-v0.1.0",
               "factor_pack_digest": FACTOR_DIGEST,
               "source_ids": ["EPA-2025", "IPCC-AR6"]}
    payload.update(over)
    return await core.process(payload)


# --- L1 append-only, hash-chained ------------------------------------------ #
async def test_L1_chain_valid_and_tamper_detected(core):
    for i in range(3):
        r = await _work(core, f"e{i}")
        assert r["status"] == "ok"
    assert core._ledgers["agent-x"][0]["prev_hash"] == _GENESIS
    v = await core.process({"action": "verify_chain", "agent_id": "agent-x"})
    assert v["data"]["valid"] is True
    core._ledgers["agent-x"][1]["energy_j"] = 1.0  # tamper
    v2 = await core.process({"action": "verify_chain", "agent_id": "agent-x"})
    assert v2["data"]["valid"] is False and v2["data"]["broken_at_index"] == 1


# --- L2 energy accounting ---------------------------------------------------- #
async def test_L2_energy_is_power_times_duration(core):
    r = await _work(core, "e1", power_w=250.0, duration_s=120.0)
    assert r["data"]["energy_j"] == pytest.approx(30000.0)
    for f, bad in (("power_w", 0), ("power_w", -5), ("duration_s", float("nan")),
                   ("duration_s", float("inf")), ("power_w", "high"), ("power_w", True)):
        rb = await _work(core, f"bad-{f}-{bad}", **{f: bad})
        assert rb["status"] == "error", f"{f}={bad!r} accepted"


# --- L3 deterministic carbon -------------------------------------------------- #
async def test_L3_carbon_deterministic(core):
    r = await _work(core, "e1", power_w=1000.0, duration_s=3600.0,
                    grid_intensity_g_per_kwh=400.0)
    assert r["data"]["carbon_g"] == pytest.approx(400.0)  # exactly 1 kWh * 400 g
    core2 = build()
    r2 = await core2.process({"action": "record_work", "agent_id": "agent-x",
                              "entry_id": "e1", "power_w": 1000.0,
                              "duration_s": 3600.0,
                              "grid_intensity_g_per_kwh": 400.0})
    assert r2["data"]["carbon_g"] == r["data"]["carbon_g"]


# --- L4 Landauer floor --------------------------------------------------------- #
async def test_L4_landauer_floor_enforced(core):
    # physically impossible: claims 1e30 bit ops on 1 J of energy
    floor = 1e30 * KB * 300.0 * LN2  # ~2.87e9 J >> 1 J
    r = await _work(core, "impossible", power_w=1.0, duration_s=1.0, bit_ops=1e30)
    assert r["status"] == "error"
    assert "Landauer" in r["message"]
    # plausible workload: efficiency in (0, 1]
    r2 = await _work(core, "plausible", power_w=100.0, duration_s=10.0, bit_ops=1e18)
    assert r2["status"] == "ok"
    eff = r2["data"]["landauer_efficiency"]
    assert 0.0 < eff <= 1.0
    assert r2["data"]["landauer_floor_j"] == pytest.approx(1e18 * KB * 300.0 * LN2)


# --- L5 content-addressed attestations ------------------------------------------ #
async def test_L5_attest_and_verify(core):
    await _work(core, "e1")
    att = await core.process({"action": "attest", "entry_id": "e1"})
    a = att["data"]["attestation"]
    v = await core.process({"action": "verify_attestation", "attestation": a})
    assert v["data"]["valid"] is True
    v2 = await core.process({"action": "verify_attestation",
                             "attestation": {**a, "attestation_hash": "0" * 64}})
    assert v2["data"]["valid"] is False


# --- L6 conservative aggregation -------------------------------------------------- #
async def test_L6_footprint_sums_exactly(core):
    energies = []
    for i, (p, d) in enumerate([(100.0, 60.0), (250.0, 120.0), (50.0, 30.0)]):
        r = await _work(core, f"e{i}", power_w=p, duration_s=d,
                        price_minor_per_kwh=15000)
        energies.append(r["data"]["energy_j"])
    fp = await core.process({"action": "footprint", "agent_id": "agent-x"})
    d = fp["data"]
    assert d["entry_count"] == 3
    assert d["total_energy_j"] == pytest.approx(sum(energies))
    assert d["total_energy_kwh"] == pytest.approx(sum(energies) / J_PER_KWH)
    entries = (await core.process({"action": "list_entries",
                                   "agent_id": "agent-x"}))["data"]["entries"]
    assert d["total_carbon_g"] == pytest.approx(sum(e["carbon_g"] for e in entries))
    assert d["total_cost_minor"] == sum(e["cost_minor"] for e in entries)


# --- L7 idempotency ------------------------------------------------------------------ #
async def test_L7_entry_id_idempotent(core):
    r1 = await _work(core, "dup", power_w=100.0, duration_s=60.0)
    r2 = await _work(core, "dup", power_w=9999.0, duration_s=9999.0)
    assert r2["data"]["duplicate"] is True
    assert r2["data"]["energy_j"] == r1["data"]["energy_j"]
    fp = await core.process({"action": "footprint", "agent_id": "agent-x"})
    assert fp["data"]["entry_count"] == 1  # never double-counted


# --- L8 unknown ids --------------------------------------------------------------------- #
async def test_L8_unknown_account_and_entry(core):
    for action in ("footprint", "verify_chain", "list_entries"):
        r = await core.process({"action": action, "agent_id": "ghost"})
        assert r["status"] == "error" and r["field"] == "agent_id"
    r2 = await core.process({"action": "attest", "entry_id": "ghost"})
    assert r2["status"] == "error" and r2["field"] == "entry_id"
    for key in ("error_type", "field", "value", "constraint", "message", "timestamp"):
        assert key in r2


# --- I1 separate inventory namespace --------------------------------------- #
async def test_I1_inventory_never_changes_compute_footprint(core):
    await _work(core, "work-1", power_w=1000.0, duration_s=3600.0)
    before = (await core.process({"action": "footprint",
                                  "agent_id": "agent-x"}))["data"]
    recorded = await _inventory(core, "inv-1", mass_g=999999)
    assert recorded["status"] == "ok"
    after = (await core.process({"action": "footprint",
                                 "agent_id": "agent-x"}))["data"]
    assert after == before
    assert len(core._ledgers["agent-x"]) == 1
    assert len(core._inventories["ghg-ledger-agent"]) == 1


# --- I2 exact integer grams ------------------------------------------------- #
async def test_I2_inventory_mass_is_nonnegative_integer(core):
    zero = await _inventory(core, "zero", mass_g=0)
    assert zero["status"] == "ok" and zero["data"]["mass_g"] == 0
    for index, bad in enumerate((-1, 1.5, True, "123")):
        result = await _inventory(core, f"bad-mass-{index}", mass_g=bad)
        assert result["status"] == "error" and result["field"] == "mass_g"


# --- I3 digest + factor lineage -------------------------------------------- #
async def test_I3_inventory_lineage_validated_and_canonical(core):
    result = await _inventory(core, "lineage", source_ids=["z", "a", "z"])
    assert result["data"]["source_ids"] == ["a", "z"]
    assert result["data"]["content_digest"] == AUDIT_DIGEST
    assert result["data"]["factor_pack_digest"] == FACTOR_DIGEST
    for field, bad in (("content_digest", "abc"),
                       ("factor_pack_digest", "A" * 64),
                       ("factor_pack_version", ""),
                       ("source_ids", ["ok", ""])):
        invalid = await _inventory(core, f"bad-{field}", **{field: bad})
        assert invalid["status"] == "error" and invalid["field"] == field


# --- I4 independent append/hash chain -------------------------------------- #
async def test_I4_inventory_chain_detects_tampering(core):
    await _inventory(core, "inv-1")
    await _inventory(core, "inv-2", mass_g=42)
    assert core._inventories["ghg-ledger-agent"][0]["prev_hash"] == _GENESIS
    valid = await core.process({"action": "verify_inventory_chain",
                                "agent_id": "ghg-ledger-agent"})
    assert valid["data"] == {"agent_id": "ghg-ledger-agent", "valid": True,
                              "inventory_count": 2}
    core._inventories["ghg-ledger-agent"][1]["mass_g"] = 43
    broken = await core.process({"action": "verify_inventory_chain",
                                 "agent_id": "ghg-ledger-agent"})
    assert broken["data"]["valid"] is False
    assert broken["data"]["broken_at_index"] == 1


# --- I5 exact idempotency; conflicting reuse fails closed ------------------ #
async def test_I5_exact_inventory_replay_is_idempotent(core):
    first = await _inventory(core, "same", mass_g=100)
    replay = await _inventory(core, "same", mass_g=100)
    assert replay["status"] == "ok"
    assert replay["data"]["duplicate"] is True
    assert replay["data"]["inventory_hash"] == first["data"]["inventory_hash"]
    assert replay["data"]["mass_g"] == 100
    assert len(core._inventories["ghg-ledger-agent"]) == 1


@pytest.mark.parametrize(("changed", "conflict_field"), [
    ({"agent_id": "different-agent"}, "agent_id"),
    ({"mass_g": 999}, "mass_g"),
    ({"content_digest": "c" * 64}, "content_digest"),
    ({"factor_pack_version": "different-pack"}, "factor_pack_version"),
    ({"factor_pack_digest": "d" * 64}, "factor_pack_digest"),
    ({"source_ids": ["DIFFERENT-SOURCE"]}, "source_ids"),
])
async def test_I5_conflicting_inventory_replay_fails_closed(
        core, changed, conflict_field):
    first = await _inventory(core, "same")
    conflict = await _inventory(core, "same", **changed)
    assert conflict["status"] == "error"
    assert conflict["error_type"] == "ConflictError"
    assert conflict["field"] == "inventory_id"
    assert conflict["value"] == "same"
    assert conflict_field in conflict["message"]
    assert "data" not in conflict
    assert len(core._inventories["ghg-ledger-agent"]) == 1
    assert core._inventories["ghg-ledger-agent"][0]["inventory_hash"] \
        == first["data"]["inventory_hash"]


# --- I6 retrieval and fail-loud unknowns ----------------------------------- #
async def test_I6_inventory_reads_and_unknowns_fail_loud(core):
    recorded = await _inventory(core, "known")
    got = await core.process({"action": "get_inventory",
                              "inventory_id": "known"})
    assert got["data"]["inventory_hash"] == recorded["data"]["inventory_hash"]
    listed = await core.process({"action": "list_inventories",
                                 "agent_id": "ghg-ledger-agent"})
    assert listed["data"]["count"] == 1
    for payload, field in (({"action": "get_inventory",
                             "inventory_id": "ghost"}, "inventory_id"),
                           ({"action": "list_inventories",
                             "agent_id": "ghost"}, "agent_id"),
                           ({"action": "verify_inventory_chain",
                             "agent_id": "ghost"}, "agent_id")):
        error = await core.process(payload)
        assert error["status"] == "error" and error["field"] == field


# --- domain sanity --------------------------------------------------------------------- #
async def test_zero_grid_intensity_zero_carbon(core):
    r = await _work(core, "green", grid_intensity_g_per_kwh=0.0)
    assert r["data"]["carbon_g"] == 0.0


async def test_cost_ceiling_integer_minor_units(core):
    r = await _work(core, "e1", power_w=1000.0, duration_s=3600.0,
                    price_minor_per_kwh=1)  # 1 kWh -> 1 minor unit
    assert r["data"]["cost_minor"] == 1 and isinstance(r["data"]["cost_minor"], int)


# --- fleet contract ------------------------------------------------------------------------ #
async def test_contract_never_raises_and_unknown_action(core):
    for payload in [{}, {"action": None}, {"action": "nope"}, "not-a-dict", 42]:
        r = await core.process(payload)
        assert isinstance(r, dict) and r["status"] == "error"


async def test_contract_describe_health_consistent(core):
    d = core.describe()
    h = await core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"] and d["a2a_role"] == "accounting"
    assert d["version"] == h["version"] == "0.3.0"
    assert set(("record_inventory", "get_inventory", "list_inventories",
                "verify_inventory_chain")) <= set(d["capabilities"])
    assert set(h) >= {"status", "agent", "version", "timestamp", "checks"}
