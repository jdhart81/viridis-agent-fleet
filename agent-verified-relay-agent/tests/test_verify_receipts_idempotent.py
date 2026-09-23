"""verify_receipts purity/idempotency pin — strengthens V2/V7 (receipt hash
chain + "read surface is pure"). Mirrors the fleet-wide verify_* idiom
(metering verify_chain N64; arbitration/surety/provenance/erc8004/covenant
N65; escrow/trust-oracle/compute-ledger/offset-clearinghouse N66): the read
must be repeatable byte-for-byte and must never mutate the receipts or fee
ledger it inspects, and tamper detection must be deterministic across
repeats. Closes the last agent named in the N65 cross-pollination queue.
"""
import asyncio
import json

from src.core import build


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def ok_transport(result=None):
    def t(url, body, timeout_s):
        return (200, "application/json", json.dumps(
            {"jsonrpc": "2.0", "id": 1,
             "result": result if result is not None
             else {"content": [{"type": "text", "text": "42"}]}}))
    return t


def _register(a, url="https://api.example.com/mcp", provider="acme"):
    r = run(a.process({"action": "register_service", "url": url,
                       "provider": provider}))
    assert r["status"] == "ok", r
    return r["data"]["service_id"]


def _call(a, sid, call_id="c-1", tool="lookup", args=None):
    return run(a.process({"action": "call_verified", "service_id": sid,
                          "tool": tool, "call_id": call_id,
                          "arguments": args or {"q": "x"}}))


def test_verify_receipts_is_pure_and_repeatable():
    a = build(transport=ok_transport())
    sid = _register(a)
    for i in range(3):
        _call(a, sid, call_id=f"c-{i}")

    stats_before = run(a.process({"action": "service_stats", "service_id": sid}))
    first = run(a.process({"action": "verify_receipts", "service_id": sid}))
    second = run(a.process({"action": "verify_receipts", "service_id": sid}))
    stats_after = run(a.process({"action": "service_stats", "service_id": sid}))

    assert first["data"] == second["data"] == {
        "service_id": sid, "valid": True, "receipt_count": 3,
        "fees_accrued_minor": first["data"]["fees_accrued_minor"],
        "fees_recomputed_minor": first["data"]["fees_recomputed_minor"],
        "fees_consistent": True,
    }
    # verifying never mutates the service's receipts or fee ledger
    assert stats_before["data"] == stats_after["data"]


def test_verify_receipts_tamper_detection_is_deterministic():
    a = build(transport=ok_transport())
    sid = _register(a)
    for i in range(3):
        _call(a, sid, call_id=f"c-{i}")
    pristine_len = len(a._services[sid].receipts)

    a._services[sid].receipts[1]["outcome"] = "error"  # tamper

    first = run(a.process({"action": "verify_receipts", "service_id": sid}))
    second = run(a.process({"action": "verify_receipts", "service_id": sid}))

    assert first["data"] == second["data"] == {
        "service_id": sid, "valid": False, "broken_at_index": 1,
    }
    # the read itself does not repair, append, or drop receipts
    assert len(a._services[sid].receipts) == pristine_len
