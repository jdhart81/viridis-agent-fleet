"""agent-compute-ledger — x402-C carbon_receipt invariants (X1-X5)."""
import asyncio
import hashlib
import json

import pytest

from src.core import KB, LN2, J_PER_KWH, build


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _work(a, entry_id="e1", bit_ops=None, power_w=100.0, duration_s=2.0,
          grid=400.0):
    payload = {"action": "record_work", "agent_id": "acme", "entry_id": entry_id,
               "power_w": power_w, "duration_s": duration_s,
               "grid_intensity_g_per_kwh": grid}
    if bit_ops is not None:
        payload["bit_ops"] = bit_ops
    return run(a.process(payload))


def _receipt(a, entry_id="e1", **kw):
    return run(a.process({"action": "carbon_receipt", "entry_id": entry_id, **kw}))


def test_x1_values_verbatim_and_method_selection():
    a = build()
    _work(a, "measured", bit_ops=None)
    r = _receipt(a, "measured")["data"]["carbon"]
    assert r["version"] == "x402c/0.1"
    assert r["method"] == "measured" and "landauer_efficiency" not in r
    # bit_ops present -> landauer-floor method + efficiency in (0,1].
    a2 = build()
    _work(a2, "lf", bit_ops=1e12)
    r2 = _receipt(a2, "lf")["data"]["carbon"]
    assert r2["method"] == "landauer-floor"
    assert 0 < r2["landauer_efficiency"] <= 1
    # g_co2e/energy match the recorded entry exactly (no drift).
    entry = run(a2.process({"action": "list_entries", "agent_id": "acme"}))["data"]["entries"][0]
    assert r2["energy_j"] == entry["energy_j"]
    assert r2["g_co2e"] == round(entry["carbon_g"], 6)


def test_x2_landauer_floor_guaranteed_by_record_validation():
    a = build()
    # An impossible workload (energy below Landauer floor) is rejected at
    # record time, so no receipt can ever assert a false floor.
    floor = 1e15 * KB * 300.0 * LN2       # floor for 1e15 bit-ops
    bad = run(a.process({"action": "record_work", "agent_id": "acme",
                         "entry_id": "imp", "power_w": floor, "duration_s": 1e-9,
                         "bit_ops": 1e15}))
    assert bad["status"] == "error" and bad["field"] == "energy_j"
    assert _receipt(a, "imp")["status"] == "error"   # never recorded


def test_x3_c2_recomputable():
    a = build()
    _work(a, "e1", grid=380.0)
    r = _receipt(a, "e1")["data"]["carbon"]
    assert abs(r["g_co2e"] - (r["energy_j"] / J_PER_KWH) * 380.0) < 1e-6
    assert _receipt(a, "e1")["data"]["conformance"]["C2_recomputable"] is True


def test_x4_c3_attestation_hash_binds_to_entry_and_recomputes():
    a = build()
    _work(a, "e1", bit_ops=1e12)
    out = _receipt(a, "e1")["data"]
    carbon = out["carbon"]
    stored = carbon.pop("attestation_hash")
    canon = json.dumps(carbon, sort_keys=True, separators=(",", ":"))
    recomputed = hashlib.sha256((canon + out["entry_hash"]).encode()).hexdigest()
    assert recomputed == stored               # any party can verify
    # Different entry -> different binding hash.
    _work(a, "e2", bit_ops=2e12)
    other = _receipt(a, "e2")["data"]["carbon"]["attestation_hash"]
    assert other != stored


def test_x5_read_only_and_offset_ref_passthrough():
    a = build()
    _work(a, "e1")
    before = run(a.process({"action": "verify_chain", "agent_id": "acme"}))["data"]
    for _ in range(3):
        _receipt(a, "e1")
    after = run(a.process({"action": "verify_chain", "agent_id": "acme"}))["data"]
    assert before == after and after["valid"]
    # offset_ref rides through into the receipt (C4 pointer).
    r = _receipt(a, "e1", offset_ref="viridis:offsets/ret-000042")["data"]["carbon"]
    assert r["offset_ref"] == "viridis:offsets/ret-000042"
    # unknown entry -> error, never crash.
    assert _receipt(a, "nope")["status"] == "error"
    # bad offset_ref type rejected.
    assert run(a.process({"action": "carbon_receipt", "entry_id": "e1",
                          "offset_ref": 5}))["status"] == "error"
