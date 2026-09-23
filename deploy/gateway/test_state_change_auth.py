import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state_change_auth as state_auth
from state_change_auth import (
    Mutation,
    StateChangeAuthMiddleware,
    _mutation,
    status,
)


TOKEN = "energyai-test-token-0123456789abcdef"
ADMIN = "fleet-admin-test-token-0123456789abcdef"


def _scope(path="/offsets/mcp", headers=()):
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
    }


def _body(tool, arguments=None, request_id=1):
    return json.dumps({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments or {}},
    }).encode()


def _call(monkeypatch, body, *, path="/offsets/mcp", headers=(),
          mode="enforce"):
    monkeypatch.setenv("VIRIDIS_STATE_AUTH_MODE", mode)
    monkeypatch.setenv("VIRIDIS_STATE_AUTH_TOKENS_JSON", json.dumps({
        "viridis:energyai": {"token": TOKEN, "role": "agent"},
        "fleet-admin": {"token": ADMIN, "role": "admin"},
    }))
    sent = []
    downstream = {"called": False, "body": b""}

    async def app(scope, receive, send):
        downstream["called"] = True
        request = await receive()
        downstream["body"] = request.get("body", b"")
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    first = True

    async def receive():
        nonlocal first
        if first:
            first = False
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(StateChangeAuthMiddleware(app)(
        _scope(path, headers), receive, send))
    return sent, downstream


def _status(sent):
    return next(m["status"] for m in sent
                if m["type"] == "http.response.start")


def test_initialize_and_read_only_calls_stay_open(monkeypatch):
    initialize = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
    }).encode()
    sent, downstream = _call(monkeypatch, initialize)
    assert _status(sent) == 200
    assert downstream["called"] is True
    sent, downstream = _call(monkeypatch, _body("book"))
    assert _status(sent) == 200
    assert downstream["called"] is True


def test_unauthenticated_mutation_rejected_in_enforce(monkeypatch):
    sent, downstream = _call(monkeypatch, _body(
        "buy_offset_budget", {
            "buyer": "viridis:energyai", "purchase_id": "p1",
            "budget_minor": 100, "dry_run": False,
        }))
    assert _status(sent) == 401
    assert downstream["called"] is False


def test_authenticated_mutation_succeeds_and_body_is_replayed(monkeypatch):
    body = _body("buy_offset_budget", {
        "buyer": "viridis:energyai", "purchase_id": "p1",
        "budget_minor": 100, "dry_run": False,
    })
    sent, downstream = _call(monkeypatch, body, headers=(
        ("Authorization", f"Bearer {TOKEN}"),
        ("X-Viridis-Agent-Id", "viridis:energyai"),
    ))
    assert _status(sent) == 200
    assert downstream["called"] is True
    assert downstream["body"] == body


def test_agent_token_cannot_claim_another_buyer(monkeypatch):
    sent, downstream = _call(monkeypatch, _body(
        "buy_offset_budget", {
            "buyer": "viridis:someone-else", "purchase_id": "p1",
            "budget_minor": 100,
        }), headers=(
            ("Authorization", f"Bearer {TOKEN}"),
            ("X-Viridis-Agent-Id", "viridis:energyai"),
        ))
    assert _status(sent) == 403
    assert downstream["called"] is False


def test_observe_mode_allows_only_energyai_compatibility_writes(monkeypatch):
    sent, downstream = _call(monkeypatch, _body(
        "buy_offset_budget", {
            "buyer": "viridis:energyai", "purchase_id": "p1",
            "budget_minor": 100,
        }), mode="observe")
    assert _status(sent) == 200
    assert downstream["called"] is True
    sent, downstream = _call(monkeypatch, _body(
        "list_credit", {
            "issuer": "attacker", "project_id": "junk",
            "mass_g": 1_000_000, "price_minor_per_kg": 1,
            "verification_ref": "dscore:fake",
        }), mode="observe")
    assert _status(sent) == 401
    assert downstream["called"] is False


def test_observe_compatibility_refuses_wrong_actor_claim(monkeypatch):
    sent, downstream = _call(monkeypatch, _body(
        "buy_offset_budget", {
            "buyer": "viridis:someone-else", "purchase_id": "p1",
            "budget_minor": 100,
        }), mode="observe")
    assert _status(sent) == 401
    assert downstream["called"] is False


def test_observe_compatibility_never_accepts_invalid_credentials(monkeypatch):
    sent, downstream = _call(monkeypatch, _body(
        "buy_offset_budget", {
            "buyer": "viridis:energyai", "purchase_id": "p1",
            "budget_minor": 100,
        }), headers=(
            ("Authorization", "Bearer invalid-token-is-not-a-legacy-call"),
            ("X-Viridis-Agent-Id", "viridis:energyai"),
        ), mode="observe")
    assert _status(sent) == 401
    assert downstream["called"] is False


def test_dry_run_purchase_is_read_only(monkeypatch):
    sent, downstream = _call(monkeypatch, _body(
        "buy_offset_budget", {
            "buyer": "viridis:energyai", "purchase_id": "preview",
            "budget_minor": 100, "dry_run": True,
        }))
    assert _status(sent) == 200
    assert downstream["called"] is True


def test_unknown_infrastructure_tool_fails_closed_as_mutation():
    payload = json.loads(_body("new_write_tool"))
    mutation = _mutation(_scope(), payload)
    assert mutation is not None
    assert mutation.tool == "new_write_tool"


def test_rejection_diagnostics_are_actionable_and_privacy_safe(monkeypatch):
    key = "offsets/list_credit/missing_credentials/uncredentialed"
    before = (
        status()["diagnostics"]["rejected_by_route_action_reason"]
        .get(key, 0)
    )
    secret_argument = "must-never-appear-in-health"
    sent, downstream = _call(monkeypatch, _body(
        "list_credit", {
            "issuer": secret_argument,
            "project_id": "private-project",
            "mass_g": 1_000_000,
            "price_minor_per_kg": 1,
            "verification_ref": "private-proof",
        }, request_id="private-request-id"))
    assert _status(sent) == 401
    assert downstream["called"] is False

    auth_status = status()
    diagnostics = auth_status["diagnostics"]
    assert diagnostics["rejected_by_route_action_reason"][key] == before + 1
    assert diagnostics["last_rejection"]["mount"] == "offsets"
    assert diagnostics["last_rejection"]["tool"] == "list_credit"
    assert diagnostics["last_rejection"]["reason"] == "missing_credentials"
    assert diagnostics["last_rejection"]["principal_class"] == "uncredentialed"
    serialized = json.dumps(auth_status, sort_keys=True)
    for forbidden in (
            TOKEN, ADMIN, secret_argument, "private-project",
            "private-proof", "private-request-id", "viridis:energyai"):
        assert forbidden not in serialized


def test_rejection_diagnostics_distinguish_invalid_known_principal(monkeypatch):
    key = "offsets/buy_offset_budget/invalid_token/configured-agent"
    before = (
        status()["diagnostics"]["rejected_by_route_action_reason"]
        .get(key, 0)
    )
    sent, downstream = _call(monkeypatch, _body(
        "buy_offset_budget", {
            "buyer": "viridis:energyai",
            "purchase_id": "p1",
            "budget_minor": 100,
        }), headers=(
            ("Authorization", "Bearer wrong-but-redacted"),
            ("X-Viridis-Agent-Id", "viridis:energyai"),
        ), mode="observe")
    assert _status(sent) == 401
    assert downstream["called"] is False
    assert (
        status()["diagnostics"]["rejected_by_route_action_reason"][key]
        == before + 1
    )


def test_diagnostic_cardinality_is_bounded():
    bucket_name = "rejected_by_route_action_reason"
    with state_auth._lock:
        original = dict(state_auth._diagnostic_counts[bucket_name])
        state_auth._diagnostic_counts[bucket_name].clear()
    try:
        for index in range(state_auth._DIAGNOSTIC_BUCKET_MAX + 20):
            state_auth._record_outcome(
                "rejected",
                Mutation("offsets", f"unknown-tool-{index}", {}, index),
                "missing_credentials",
                "uncredentialed",
            )
        diagnostics = status()["diagnostics"][bucket_name]
        assert len(diagnostics) == state_auth._DIAGNOSTIC_BUCKET_MAX
        assert diagnostics["_overflow"] == 21
    finally:
        with state_auth._lock:
            state_auth._diagnostic_counts[bucket_name].clear()
            state_auth._diagnostic_counts[bucket_name].update(original)
