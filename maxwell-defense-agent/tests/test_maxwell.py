import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("maxwell_candidate", ROOT / "src/__init__.py",
                                            submodule_search_locations=[str(ROOT / "src")])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from maxwell_candidate.defense import Guard, binding, solve
from maxwell_candidate.core import MaxwellDefenseCore
from maxwell_candidate.middleware import MaxwellMiddleware

KEY = b"test-key-for-maxwell-only-32-bytes!"


def request_digest(**overrides):
    fields = dict(tenant="tenant-a", subject="verified-a", method="POST", target="/expensive?x=1", body=b'{"job":1}')
    return binding(**(fields | overrides))


def solution(guard, digest=None):
    challenge = guard.issue(digest or request_digest())
    proof = solve(challenge, max_seconds=2)
    assert "nonce" in proof
    return proof


def test_binding_tamper_replay_and_restart(tmp_path):
    path = tmp_path / "replay.db"
    guard = Guard(KEY, path, bits=4)
    proof = solution(guard)
    for field, value in [("tenant", "tenant-b"), ("subject", "verified-b"),
                         ("method", "GET"), ("target", "/other"), ("body", b"changed")]:
        assert not guard.verify(proof["token"], proof["nonce"], request_digest(**{field: value}))["admitted"]
    assert not guard.verify(proof["token"] + "x", proof["nonce"], request_digest())["admitted"]
    assert guard.verify(proof["token"], proof["nonce"], request_digest())["admitted"]
    guard.close()
    restarted = Guard(KEY, path, bits=4)
    assert restarted.verify(proof["token"], proof["nonce"], request_digest())["reason"] == "replay"
    restarted.close()


def test_atomic_consumption_across_workers(tmp_path):
    first = Guard(KEY, tmp_path / "shared.db", bits=4)
    second = Guard(KEY, tmp_path / "shared.db", bits=4)
    proof = solution(first)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda g: g.verify(proof["token"], proof["nonce"], request_digest()), [first, second]))
    assert sum(r["admitted"] for r in results) == 1
    first.close(); second.close()


def test_expiry_capacity_and_store_fail_closed(tmp_path):
    now = [1000]
    guard = Guard(KEY, tmp_path / "replay.db", bits=4, ttl=10, capacity=1, clock=lambda: now[0])
    first, second = solution(guard), solution(guard)
    assert guard.verify(first["token"], first["nonce"], request_digest())["admitted"]
    assert guard.verify(second["token"], second["nonce"], request_digest())["reason"] == "capacity"
    now[0] = 1010
    assert not guard.verify(second["token"], second["nonce"], request_digest())["admitted"]
    third = solution(guard)
    assert guard.verify(third["token"], third["nonce"], request_digest())["admitted"]
    fourth = solution(guard)
    guard.close()
    assert guard.verify(fourth["token"], fourth["nonce"], request_digest())["reason"] == "store_unavailable"


def test_rate_limit_and_solver_budget(tmp_path):
    guard = Guard(KEY, tmp_path / "r.db", bits=20, max_checks_per_second=1)
    challenge = guard.issue(request_digest())
    assert guard.issue(request_digest())["status"] == "busy"
    assert not guard.verify("x" * 3000, "1", request_digest())["admitted"]
    with pytest.raises(ValueError):
        solve(challenge, max_attempts=100000000)
    assert solve(challenge, max_attempts=1, max_seconds=0.000000001)["status"] == "budget_exhausted"
    guard.close()


async def call(app, *, headers=(), body=b"job", path="/costly", query=b"", subject="verified-a"):
    messages = []
    async def receive():
        return {"type": "http.request", "body": body}
    async def send(message):
        messages.append(message)
    await app({"type": "http", "path": path, "method": "POST", "headers": headers,
               "query_string": query, "server_subject": subject}, receive, send)
    return messages[0]["status"], json.loads(messages[1]["body"])


def test_middleware_blocks_before_backend_and_preserves_body(tmp_path):
    seen = []
    async def backend(scope, receive, send):
        seen.append((await receive())["body"])
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})
    async def identity(scope):
        return scope.get("server_subject")
    guard = Guard(KEY, tmp_path / "guard.db", bits=4)
    app = MaxwellMiddleware(backend, guard=guard, tenant="buyer-a", paths=["/costly"], identity=identity)
    status, issued = asyncio.run(call(app))
    assert status == 429 and seen == []
    proof = solve(issued["maxwell"])
    headers = [(b"x-maxwell-token", proof["token"].encode()), (b"x-maxwell-nonce", proof["nonce"].encode())]
    assert asyncio.run(call(app, headers=headers, query=b"changed"))[0] == 403
    assert asyncio.run(call(app, headers=headers, subject="other"))[0] == 403
    assert asyncio.run(call(app, headers=headers, body=b"different"))[0] == 403
    assert seen == []
    assert asyncio.run(call(app, headers=headers))[0] == 200
    assert seen == [b"job"]
    assert asyncio.run(call(app, headers=headers))[0] == 403
    assert asyncio.run(call(app, body=b"x" * 65537))[0] == 413
    assert asyncio.run(call(app, subject=None, headers=[(b"x-trusted", b"true")]))[0] == 401
    assert seen == [b"job"]
    guard.close()


def test_rehearsal_limits_claims_and_disabled(monkeypatch):
    core = MaxwellDefenseCore()
    args = {"action": "rehearse_defense", "client_hashes_per_second": 100000,
            "client_p95_budget_ms": 250, "backend_cost_ms": 2000, "peak_requests_per_second": 100}
    monkeypatch.delenv("MAXWELL_FLEET_ENABLED", raising=False)
    assert core._paid_preflight(args)["error_type"] == "ServiceUnavailable"
    monkeypatch.setenv("MAXWELL_FLEET_ENABLED", "1")
    assert core._paid_preflight(args | {"client_hashes_per_second": True})["error_type"] == "ValidationError"
    assert core._paid_preflight(args | {"client_hashes_per_second": 10**30})["error_type"] == "ValidationError"
    result = asyncio.run(core.process(args))
    assert result["modeled_client"]["p95_ms"] <= 250
    assert result["protection_activated"] is False
    assert result["energy_savings_measured"] is False
    assert result["measured_local"]["sha256_samples"] == 8192
    low = asyncio.run(core.process(args | {"client_hashes_per_second": 100, "client_p95_budget_ms": 1}))
    assert low["decision"] == "CLIENT_BUDGET_TOO_LOW"
