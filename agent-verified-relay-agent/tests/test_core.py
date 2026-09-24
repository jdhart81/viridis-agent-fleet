"""agent-verified-relay-agent — invariant tests (V1–V10) + fleet contract."""
import asyncio
import json

import pytest

from src.core import build, parse_mcp_response, validate_service_url


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def ok_transport(result=None):
    """Downstream that answers a valid JSON-RPC result. Records calls."""
    calls = []

    def t(url, body, timeout_s):
        calls.append((url, body, timeout_s))
        return (200, "application/json", json.dumps(
            {"jsonrpc": "2.0", "id": 1,
             "result": result if result is not None
             else {"content": [{"type": "text", "text": "42"}]}}))
    t.calls = calls
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


# ----------------------------------------------------------------------- #
def test_v1_ssrf_guard_rejects_dangerous_urls():
    bad = ["http://api.example.com/mcp",                # not https
           "https://localhost/mcp",                     # localhost
           "https://127.0.0.1/mcp",                     # IP literal
           "https://[::1]/mcp",                         # v6 loopback
           "https://169.254.169.254/latest",            # metadata IP
           "https://internal-box/mcp",                  # bare hostname
           "https://svc.local/mcp",                     # mDNS suffix
           "https://db.internal/mcp",                   # internal suffix
           "https://user:pw@api.example.com/mcp",       # userinfo
           "https://api.example.com:8080/mcp",          # bad port
           "x" * 3000]                                  # length
    a = build(transport=ok_transport())
    for url in bad:
        r = run(a.process({"action": "register_service", "url": url,
                           "provider": "p"}))
        assert r["status"] == "error", url
    assert validate_service_url("https://api.example.com:8443/mcp")


def test_v2_receipt_chain_verifies_and_detects_tampering():
    a = build(transport=ok_transport())
    sid = _register(a)
    for i in range(4):
        _call(a, sid, call_id=f"c-{i}")
    v = run(a.process({"action": "verify_receipts", "service_id": sid}))["data"]
    assert v["valid"] is True and v["receipt_count"] == 4
    a._services[sid].receipts[1]["outcome"] = "error"        # tamper
    v2 = run(a.process({"action": "verify_receipts", "service_id": sid}))["data"]
    assert v2["valid"] is False and v2["broken_at_index"] == 1


def test_v3_idempotent_on_call_id_never_recalls_downstream():
    t = ok_transport()
    a = build(transport=t)
    sid = _register(a)
    first = _call(a, sid, call_id="dup")
    replay = _call(a, sid, call_id="dup")
    assert len(t.calls) == 1                                  # one downstream call
    assert replay["data"]["duplicate"] is True
    assert replay["data"]["result"] == first["data"]["result"]
    assert (replay["data"]["receipt"]["receipt_id"]
            == first["data"]["receipt"]["receipt_id"])


def test_v4_payload_fidelity_and_canonical_request_hash():
    captured = {}

    def t(url, body, timeout_s):
        captured["body"] = body
        return (200, "application/json", json.dumps(
            {"jsonrpc": "2.0", "id": 1, "result": {"answer": [3, 1, 2]}}))
    a = build(transport=t)
    sid = _register(a)
    r = _call(a, sid, args={"b": 2, "a": 1})
    # Result returned exactly as downstream sent it.
    assert r["data"]["result"] == {"answer": [3, 1, 2]}
    # Request body is canonical (sorted keys) and hash-committed.
    sent = json.loads(captured["body"])
    assert sent["params"]["arguments"] == {"a": 1, "b": 2}
    assert captured["body"] == json.dumps(sent, sort_keys=True,
                                          separators=(",", ":")).encode()
    import hashlib
    assert (r["data"]["receipt"]["request_hash"]
            == hashlib.sha256(captured["body"]).hexdigest())


def test_v5_failures_produce_envelope_and_receipt():
    def boom(url, body, timeout_s):
        raise ConnectionError("refused")
    a = build(transport=boom)
    sid = _register(a)
    r = _call(a, sid, call_id="fail-1")
    assert r["status"] == "error" and r["error_type"] == "DownstreamError"
    assert r["receipt"]["outcome"] == "error"                 # evidence
    # HTTP failure and JSON-RPC error variants are also receipted.
    a2 = build(transport=lambda u, b, t: (503, "text/plain", "down"))
    sid2 = _register(a2)
    r2 = _call(a2, sid2)
    assert r2["status"] == "error" and "HTTP 503" in r2["message"]
    a3 = build(transport=lambda u, b, t: (200, "application/json", json.dumps(
        {"jsonrpc": "2.0", "id": 1, "error": {"message": "no such tool"}})))
    sid3 = _register(a3)
    r3 = _call(a3, sid3)
    assert r3["status"] == "error" and "no such tool" in r3["message"]
    v = run(a3.process({"action": "verify_receipts", "service_id": sid3}))["data"]
    assert v["valid"] is True and v["receipt_count"] == 1


def test_v6_fee_ledger_deterministic_and_recomputable():
    a = build(transport=ok_transport())
    r = run(a.process({"action": "register_service", "provider": "acme",
                       "url": "https://api.example.com/mcp", "fee_minor": 5}))
    sid = r["data"]["service_id"]
    for i in range(3):
        _call(a, sid, call_id=f"c-{i}")
    boom = build(transport=lambda u, b, t: (500, "", ""))
    stats = run(a.process({"action": "service_stats", "service_id": sid}))["data"]
    assert stats["fees_accrued_minor"] == 15                  # 3 x 5, ok calls
    v = run(a.process({"action": "verify_receipts", "service_id": sid}))["data"]
    assert v["fees_consistent"] is True
    assert v["fees_recomputed_minor"] == stats["fees_accrued_minor"]


def test_v7_reads_are_pure():
    a = build(transport=ok_transport())
    sid = _register(a)
    _call(a, sid)
    before = run(a.process({"action": "service_stats", "service_id": sid}))["data"]
    for _ in range(3):
        run(a.process({"action": "list_services"}))
        run(a.process({"action": "verify_receipts", "service_id": sid}))
        run(a.process({"action": "service_stats", "service_id": sid}))
    after = run(a.process({"action": "service_stats", "service_id": sid}))["data"]
    assert before == after


def test_v8_contract_never_raises():
    a = build(transport=ok_transport())
    for payload in [None, [], "x",
                    {"action": "nope"},
                    {"action": "call_verified", "service_id": "vsvc-missing",
                     "tool": "t", "call_id": "c"},
                    {"action": "get_receipt", "receipt_id": "vrc-missing"},
                    {"action": "verify_receipts", "service_id": None},
                    {"action": "call_verified"}]:
        r = run(a.process(payload))
        assert r["status"] == "error" and r["error_type"]
    d = a.describe()
    h = run(a.health())
    assert d["name"] == h["agent"] and d["capabilities"]


def test_v9_content_addressed_idempotent_registration():
    a = build(transport=ok_transport())
    s1 = _register(a, provider="acme")
    r2 = run(a.process({"action": "register_service", "provider": "acme",
                        "url": "https://api.example.com/mcp"}))
    assert r2["data"]["service_id"] == s1 and r2["data"]["duplicate"] is True
    s3 = _register(a, url="https://other.example.com/mcp", provider="acme")
    assert s3 != s1
    listing = run(a.process({"action": "list_services"}))["data"]
    assert listing["count"] == 2


def test_v10_resource_safety_timeout_and_size_caps():
    a = build(transport=ok_transport())
    sid = _register(a)
    r = run(a.process({"action": "call_verified", "service_id": sid,
                       "tool": "t", "call_id": "c", "timeout_s": 99}))
    assert r["status"] == "error" and r["field"] == "timeout_s"
    big = build(transport=lambda u, b, t: (200, "application/json",
                                           "x" * (513 * 1024)))
    sid2 = _register(big)
    r2 = _call(big, sid2)
    assert r2["status"] == "error" and "512KiB" in r2["message"]
    assert r2["receipt"]["outcome"] == "error"                # still evidence


def test_default_transport_stops_at_first_sse_message(monkeypatch):
    """Regression (prod 2026-07-15): a streamable-http server whose SSE
    stream stays OPEN after the response event must not hang the read —
    _default_transport returns at the first complete data: message."""
    import src.core as core

    class FakeResp:
        status = 200
        headers = {"content-type": "text/event-stream"}
        def __init__(self):
            self._lines = iter([
                b"event: message\n",
                b'data: {"jsonrpc":"2.0","id":1,"result":{"v":9}}\n',
                b"\n",
                # simulate a stream that would block forever if read to EOF:
                _Boom()])
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __iter__(self): return self._lines
        def read(self, n=-1): raise AssertionError("should not read to EOF")

    class _Boom:
        def __len__(self): raise AssertionError("iterated past first message")

    monkeypatch.setattr(core.urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResp())
    status, ctype, text = core._default_transport("https://x.example.com/mcp",
                                                  b"{}", 20)
    assert status == 200 and "event-stream" in ctype
    assert core.parse_mcp_response(ctype, text)["result"] == {"v": 9}


def test_sse_response_parsing():
    sse = ("event: message\n"
           "data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"v\":7}}\n\n")
    msg = parse_mcp_response("text/event-stream", sse)
    assert msg["result"] == {"v": 7}
    a = build(transport=lambda u, b, t: (200, "text/event-stream", sse))
    sid = _register(a)
    r = _call(a, sid)
    assert r["status"] == "ok" and r["data"]["result"] == {"v": 7}
