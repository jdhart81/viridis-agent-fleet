"""One test per G-invariant (usage-statistics granularity contract, v0.2.0).

G1  aggregate identity for pre-v0.2.0 data      G6  trusted classification
G2  chain preservation across the upgrade       G7  test-flag hygiene
G3  idempotency unaffected by new fields        G8  list_events pagination
G4  signature compatibility                     G9  usage_timeseries buckets
G5  pickle snapshot forward-compat              G10 flag_meter admin gate
"""
import hashlib
import json
import math
import pickle

import pytest

from src.core import (CONSUMER_CLASSES, _GENESIS, _METER_COMPAT_DEFAULTS,
                      Meter, build)


@pytest.fixture
def agent():
    return build()


# --------------------------------------------------------------------- #
# Legacy-event fixture: byte-exact reproduction of the v0.1.x event body
# (no consumer_class/channel/caller/is_test keys) so we can prove the
# upgrade against true pre-migration data shapes.
# --------------------------------------------------------------------- #
def _legacy_hash(payload: dict, prev: str) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + body).encode()).hexdigest()


def _inject_legacy_events(meter: Meter, specs):
    """specs: list of (event_id, quantity, outcome, recorded_at)."""
    for event_id, qty, outcome, ts in specs:
        prev = meter.events[-1]["entry_hash"] if meter.events else _GENESIS
        body = {"event_id": event_id, "meter_id": meter.meter_id,
                "quantity": float(qty), "unit": meter.unit,
                "outcome": outcome, "metadata": {}, "recorded_at": ts,
                "prev_hash": prev}
        meter.events.append({**body, "entry_hash": _legacy_hash(body, prev)})
        meter.event_ids[event_id] = len(meter.events) - 1


async def _mk_meter(agent, **overrides):
    payload = {"action": "create_meter", "provider": "viridis:taxcredit-engine",
               "consumer": "public-free-tier", "unit": "call",
               "price_minor_per_unit": 200.0}
    payload.update(overrides)
    r = await agent.process(payload)
    assert r["status"] == "ok", r
    return r["data"]["meter_id"]


LEGACY_SPECS = [
    ("evt-1", 1, "ok", "2026-07-10T03:01:00+00:00"),
    ("evt-2", 1, "ok", "2026-07-10T03:02:00+00:00"),
    ("evt-3", 1, "error", "2026-07-10T03:03:00+00:00"),
    ("evt-4", 1, "ok", "2026-07-11T14:00:00+00:00"),
]


async def test_G1_aggregate_identity_for_pre_v020_data(agent):
    mid = await _mk_meter(agent)
    meter = agent._meters[mid]
    # Simulate a meter as v0.1.x left it: legacy events, legacy attributes.
    _inject_legacy_events(meter, LEGACY_SPECS)
    for attr in _METER_COMPAT_DEFAULTS:
        meter.__dict__.pop(attr, None)
    meter.__setstate__(dict(meter.__dict__))  # what unpickling will do
    s = (await agent.process({"action": "usage_summary", "meter_id": mid}))["data"]
    assert s["event_count"] == 4
    assert s["total_quantity"] == 4.0
    assert s["ok_events"] == 3 and s["error_events"] == 1
    assert s["accrued_minor"] == math.ceil(4.0 * 200.0)  # M3, hand-computed
    sla = (await agent.process({"action": "sla_report", "meter_id": mid}))["data"]
    assert sla["success_rate"] == pytest.approx(0.75)


async def test_G2_chain_valid_across_upgrade_boundary(agent):
    mid = await _mk_meter(agent)
    _inject_legacy_events(agent._meters[mid], LEGACY_SPECS)
    v = (await agent.process({"action": "verify_chain", "meter_id": mid}))["data"]
    assert v["valid"] is True
    # A new enriched event appended AFTER legacy events keeps the chain valid.
    r = await agent.process({"action": "record_usage", "meter_id": mid,
                             "event_id": "evt-new", "quantity": 1,
                             "consumer_class": "external", "channel": "script"})
    assert r["status"] == "ok"
    v2 = (await agent.process({"action": "verify_chain", "meter_id": mid}))["data"]
    assert v2["valid"] is True and v2["event_count"] == 5


async def test_G3_idempotency_ignores_new_fields(agent):
    mid = await _mk_meter(agent)
    first = await agent.process({"action": "record_usage", "meter_id": mid,
                                 "event_id": "dup-1", "quantity": 1,
                                 "consumer_class": "external"})
    replay = await agent.process({"action": "record_usage", "meter_id": mid,
                                  "event_id": "dup-1", "quantity": 99,
                                  "consumer_class": "internal",
                                  "is_test": True})
    assert replay["data"]["duplicate"] is True
    assert replay["data"]["consumer_class"] == "external"   # original wins
    assert replay["data"]["quantity"] == 1.0
    s = (await agent.process({"action": "usage_summary", "meter_id": mid}))["data"]
    assert s["event_count"] == 1


async def test_G4_default_call_reproduces_old_behavior(agent):
    mid = await _mk_meter(agent)
    r = await agent.process({"action": "record_usage", "meter_id": mid,
                             "event_id": "plain", "quantity": 2})
    e = r["data"]
    assert e["consumer_class"] == "unknown" and e["channel"] == "unknown"
    assert e["caller"] is None and e["is_test"] is False
    s = (await agent.process({"action": "usage_summary", "meter_id": mid}))["data"]
    assert s["accrued_minor"] == math.ceil(2 * 200.0)
    # And a meter created without _origin is public, never gateway.
    assert agent._meters[mid].origin == "public"


async def test_G5_pre_v020_pickle_restores_with_defaults(agent):
    mid = await _mk_meter(agent, _origin="gateway")
    meter = agent._meters[mid]
    _inject_legacy_events(meter, LEGACY_SPECS[:2])
    # Craft the exact pickle a v0.1.x snapshot holds: state WITHOUT the new
    # attributes (old class had no origin/is_test/flag_note).
    old_state = {k: v for k, v in meter.__dict__.items()
                 if k not in _METER_COMPAT_DEFAULTS}
    blob = pickle.dumps(old_state)
    restored = Meter.__new__(Meter)
    restored.__setstate__(pickle.loads(blob))
    assert restored.origin == "legacy"          # not "gateway": unknowable
    assert restored.is_test is False and restored.flag_note == ""
    assert restored.meter_id == mid and len(restored.events) == 2
    # The restored meter serves every read tool.
    agent._meters[mid] = restored
    for action in ("usage_summary", "sla_report", "verify_chain"):
        r = await agent.process({"action": action, "meter_id": mid})
        assert r["status"] == "ok", (action, r)
    r = await agent.process({"action": "list_events", "meter_id": mid})
    assert r["status"] == "ok" and r["data"]["count"] == 2
    assert all(e["pre_v020"] for e in r["data"]["events"])


async def test_G6_gateway_meters_are_write_protected(agent):
    gw = await _mk_meter(agent, _origin="gateway")
    pub = await _mk_meter(agent)
    # Public write to a gateway meter: refused with an envelope, never a raise.
    r = await agent.process({"action": "record_usage", "meter_id": gw,
                             "event_id": "spoof", "quantity": 1})
    assert r["status"] == "error" and "write-protected" in r["message"]
    r = await agent.process({"action": "close_period", "meter_id": gw})
    assert r["status"] == "error"
    # The gateway itself still writes.
    r = await agent.process({"action": "record_usage", "meter_id": gw,
                             "event_id": "real", "quantity": 1,
                             "_origin": "gateway",
                             "consumer_class": "external",
                             "channel": "smithery-proxy", "caller": "ext:abc"})
    assert r["status"] == "ok" and r["data"]["channel"] == "smithery-proxy"
    # Public meters keep pre-v0.2.0 behavior (G4).
    r = await agent.process({"action": "record_usage", "meter_id": pub,
                             "event_id": "fine", "quantity": 1})
    assert r["status"] == "ok"
    # Bad consumer_class is rejected structurally.
    r = await agent.process({"action": "record_usage", "meter_id": pub,
                             "event_id": "bad", "quantity": 1,
                             "consumer_class": "superuser"})
    assert r["status"] == "error" and r["field"] == "consumer_class"
    assert "superuser" not in CONSUMER_CLASSES


async def test_G7_test_flag_excluded_from_stats_never_from_billing(agent):
    mid = await _mk_meter(agent)
    for i, is_test in enumerate([False, True, True]):
        await agent.process({"action": "record_usage", "meter_id": mid,
                             "event_id": f"e{i}", "quantity": 1,
                             "is_test": is_test,
                             "consumer_class": "internal" if is_test else "external"})
    le = (await agent.process({"action": "list_events", "meter_id": mid}))["data"]
    assert le["count"] == 1                                   # excluded
    le_all = (await agent.process({"action": "list_events", "meter_id": mid,
                                   "include_test": True}))["data"]
    assert le_all["count"] == 3                                # includable
    ts = (await agent.process({"action": "usage_timeseries",
                               "meter_id": mid}))["data"]
    assert sum(b["events"] for b in ts["series"]) == 1
    # Billing NEVER changes because of the flag (G7 second clause).
    s = (await agent.process({"action": "usage_summary", "meter_id": mid}))["data"]
    assert s["event_count"] == 3 and s["accrued_minor"] == math.ceil(3 * 200.0)


async def test_G8_pagination_is_stable_and_complete(agent):
    mid = await _mk_meter(agent)
    for i in range(25):
        await agent.process({"action": "record_usage", "meter_id": mid,
                             "event_id": f"pg-{i:02d}", "quantity": 1,
                             "outcome": "error" if i % 5 == 0 else "ok"})
    seen, cursor = [], None
    while True:
        payload = {"action": "list_events", "meter_id": mid, "limit": 10}
        if cursor:
            payload["cursor"] = cursor
        page = (await agent.process(payload))["data"]
        seen.extend(e["event_id"] for e in page["events"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [f"pg-{i:02d}" for i in range(25)]  # ordered, no dup/loss
    errs = (await agent.process({"action": "list_events", "meter_id": mid,
                                 "outcome": "error"}))["data"]
    assert errs["count"] == 5
    bad = await agent.process({"action": "list_events", "cursor": "zzz"})
    assert bad["status"] == "error"


async def test_G9_timeseries_buckets_on_recorded_at_not_meter_created(agent):
    # Two meters (the daily-fragmentation reality) for one provider, with
    # legacy events spanning two days — buckets must follow recorded_at.
    m1 = await _mk_meter(agent)
    m2 = await _mk_meter(agent)
    _inject_legacy_events(agent._meters[m1], LEGACY_SPECS[:3])   # 07-10
    _inject_legacy_events(agent._meters[m2], [LEGACY_SPECS[3]])  # 07-11
    ts = (await agent.process({"action": "usage_timeseries", "bucket": "day",
                               "provider": "viridis:taxcredit-engine"}))["data"]
    assert [b["bucket_start"] for b in ts["series"]] == ["2026-07-10", "2026-07-11"]
    assert ts["series"][0]["events"] == 3 and ts["series"][1]["events"] == 1
    assert ts["series"][0]["by_provider"] == {"viridis:taxcredit-engine": 3}
    assert ts["series"][0]["est_accrued_minor"] == pytest.approx(3 * 200.0)
    hourly = (await agent.process({"action": "usage_timeseries",
                                   "bucket": "hour", "meter_id": m1,
                                   "since": "2026-07-10",
                                   "until": "2026-07-11"}))["data"]
    assert [b["bucket_start"] for b in hourly["series"]] == ["2026-07-10T03:00"]
    bad = await agent.process({"action": "usage_timeseries", "bucket": "week"})
    assert bad["status"] == "error"


async def test_G10_flag_meter_requires_admin_token(agent, monkeypatch):
    mid = await _mk_meter(agent)
    await agent.process({"action": "record_usage", "meter_id": mid,
                         "event_id": "e", "quantity": 1})
    before = (await agent.process({"action": "usage_summary",
                                   "meter_id": mid}))["data"]
    monkeypatch.delenv("VIRIDIS_ADMIN_TOKEN", raising=False)
    r = await agent.process({"action": "flag_meter", "meter_id": mid,
                             "is_test": True, "admin_token": "anything"})
    assert r["status"] == "error"                     # unset env => refused
    monkeypatch.setenv("VIRIDIS_ADMIN_TOKEN", "s3cret")
    r = await agent.process({"action": "flag_meter", "meter_id": mid,
                             "is_test": True, "admin_token": "wrong"})
    assert r["status"] == "error"
    r = await agent.process({"action": "flag_meter", "meter_id": mid,
                             "is_test": True, "admin_token": "s3cret",
                             "note": "synthetic evaluator meter"})
    assert r["status"] == "ok" and r["data"]["is_test"] is True
    # Flagging touched neither events, nor the chain, nor accrual (G10).
    after = (await agent.process({"action": "usage_summary",
                                  "meter_id": mid}))["data"]
    assert after == before
    assert (await agent.process({"action": "verify_chain",
                                 "meter_id": mid}))["data"]["valid"] is True
    # Flagged meter drops out of stats by default.
    ts = (await agent.process({"action": "usage_timeseries",
                               "meter_id": mid}))["data"]
    assert ts["series"] == []
