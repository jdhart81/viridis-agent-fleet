"""FA-B1..B6 safety and autonomy tests for the isolated growth worker."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from growth_agent import (
    ALLOWED_CREDENTIAL_ENV,
    FleetSnapshot,
    GeneratedCopy,
    GitHubOwnedContentAdapter,
    GrowthAgent,
    GrowthError,
    ModelUsage,
    OutboundLog,
    SmitheryMetadataAdapter,
    render_content,
    validate_generated_content,
)


NOW = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)


def snapshot(*, external=1, payers=1, intro=False,
             route_external=None):
    routes = (
        {
            "agent": "quantity-takeoff",
            "tool": "calculate_takeoff",
            "endpoint": "/x402/quantity-takeoff/calculate_takeoff",
            "price_minor": 50,
            "amount_atomic_usdc": 500_000,
            "description": "Embodied carbon quantity takeoff from a bill of materials.",
        },
        {
            "agent": "regulatory-radar",
            "tool": "scan_regulations",
            "endpoint": "/x402/regulatory-radar/scan_regulations",
            "price_minor": 25,
            "amount_atomic_usdc": 250_000,
            "description": "Energy and climate compliance regulation scan.",
        },
    )
    route_counts = {
        "quantity-takeoff/calculate_takeoff": 0,
        "regulatory-radar/scan_regulations": external,
    }
    if route_external is not None:
        route_counts.update(route_external)
    per_route = {}
    for route, count in route_counts.items():
        per_route[route] = {
            "settlements_total": count,
            "self_settlements": 0,
            "external_settlements": count,
            "distinct_external_payers": min(count, payers),
            "external_revenue_atomic": count * 250_000,
            "first_external_settlement": (
                {"tx_hash": f"0xfirst-{route}",
                 "timestamp": "2026-07-20T00:00:00Z"}
                if count else None),
        }
    return FleetSnapshot(
        routes=routes,
        metrics={
            "settlements_total": external,
            "self_settlements": 0,
            "external_settlements": external,
            "distinct_external_payers": payers,
            "external_revenue_atomic": external * 250_000,
            "first_external_settlement": (
                {"tx_hash": "0xfirst", "timestamp": "2026-07-20T00:00:00Z"}
                if external else None
            ),
        },
        route_metrics=per_route,
        intro_enabled=intro,
        agents_url="https://example.test/agents",
        quickstart_url="https://example.test/quickstart",
        captured_at=NOW.isoformat(),
    )


class FakeClient:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def fetch(self, *, now):
        self.calls += 1
        return self.value


class NeverClient:
    def fetch(self, *, now):
        raise AssertionError("kill switch must stop before any network read")


class RecordingAdapter:
    def __init__(self, log, *, fail=False):
        self.log = log
        self.fail = fail
        self.calls = []

    def send(self, target, content, credentials):
        # FA-I7: the durable attempt must already exist when the API starts.
        attempts = self.log.entries("send_attempt")
        assert len(attempts) == 1
        assert attempts[0]["target_id"] == target["id"]
        self.calls.append((target, content, credentials))
        if self.fail:
            raise GrowthError("mock posting failure")
        return {"message_id": "msg-1"}


class RecordingHarness:
    def __init__(self, *, content=None, fail=False):
        self.content = content
        self.fail = fail
        self.calls = []

    def generate(self, fleet_snapshot, target, deterministic_content):
        self.calls.append((fleet_snapshot, target, deterministic_content))
        if self.fail:
            raise GrowthError("mock OpenAI failure")
        return GeneratedCopy(
            content=self.content or deterministic_content,
            strategy="Lead with the chainable workflow and live proof.",
            usage=ModelUsage(input_tokens=100, cached_input_tokens=20,
                             output_tokens=50),
            model="gpt-5.6-terra",
        )


def target(**updates):
    item = {
        "id": "cleared-discord",
        "platform": "discord",
        "channel": "authorized test channel",
        "channel_id": "123456789012345678",
        "enabled": True,
        "policy_cleared": True,
        "cooldown_days": 14,
        "base_weight": 1.0,
        "route": "regulatory-radar/scan_regulations",
    }
    item.update(updates)
    return item


def agent(tmp_path, *, client=None, targets=None, adapter=None, environ=None,
          copywriter=None, now=NOW):
    log = OutboundLog(str(tmp_path / "growth.sqlite3"))
    chosen_adapter = adapter or RecordingAdapter(log)
    worker = GrowthAgent(
        client=client or FakeClient(snapshot()),
        log=log,
        targets=targets or [target()],
        adapters={"discord": chosen_adapter},
        copywriter=copywriter,
        environ=environ or {},
        now_fn=lambda: now,
    )
    return worker, log, chosen_adapter


def test_live_snapshot_drives_prices_and_intro_copy():
    content = render_content(snapshot(external=2, payers=2, intro=True))
    assert "quantity-takeoff — $0.50" in content
    assert "regulatory-radar — $0.25" in content
    assert "First paid call from a new wallet is $0.01." in content
    assert "2 settlement(s) from 2 distinct payer(s)" in content
    assert "https://example.test/quickstart" in content


def test_generated_copy_validator_refuses_price_or_claim_drift():
    live = snapshot(external=2, payers=2, intro=True)
    content = render_content(live)
    assert validate_generated_content(content, live) == content
    with pytest.raises(GrowthError, match="route or exact live price"):
        validate_generated_content(content.replace("$0.50", "$0.40"), live)
    with pytest.raises(GrowthError, match="prohibited claim"):
        validate_generated_content(content + "\nGuaranteed compliance.", live)


def test_live_snapshot_refuses_incomplete_or_unhealthy_health():
    with pytest.raises(GrowthError, match="not ok"):
        FleetSnapshot.from_health({"status": "degraded"},
                                  captured_at=NOW.isoformat())
    with pytest.raises(GrowthError, match="not enabled"):
        FleetSnapshot.from_health(
            {"status": "ok", "payment_gate": {"x402": {"enabled": False}}},
            captured_at=NOW.isoformat())


def test_default_off_stops_before_network_or_send(tmp_path):
    worker, log, adapter = agent(tmp_path, client=NeverClient())
    result = worker.run_once()
    assert result["status"] == "disabled"
    assert log.entries() == []
    assert adapter.calls == []


def test_dry_run_generates_and_selects_without_logging_or_send(tmp_path):
    client = FakeClient(snapshot(intro=False))
    worker, log, adapter = agent(tmp_path, client=client)
    result = worker.run_once(dry_run=True)
    assert result["status"] == "dry_run"
    assert result["target"]["id"] == "cleared-discord"
    assert result["send_attempted"] is False
    assert "First paid call" not in result["content"]
    assert client.calls == 1
    assert adapter.calls == []
    assert log.entries() == []


def test_write_before_send_survives_mocked_api_failure(tmp_path):
    log = OutboundLog(str(tmp_path / "growth.sqlite3"))
    adapter = RecordingAdapter(log, fail=True)
    worker = GrowthAgent(
        client=FakeClient(snapshot()), log=log, targets=[target()],
        adapters={"discord": adapter},
        environ={"GROWTH_AGENT_ENABLED": "true",
                 "GROWTH_DISCORD_BOT_TOKEN": "bot-test"},
        now_fn=lambda: NOW,
    )
    result = worker.run_once()
    assert result["status"] == "send_failed"
    assert len(log.entries("send_attempt")) == 1
    failures = log.entries("send_result")
    assert len(failures) == 1
    assert failures[0]["payload"]["success"] is False


def test_outbound_log_is_append_only(tmp_path):
    log = OutboundLog(str(tmp_path / "growth.sqlite3"))
    log.append("send_attempt", target(), "body", {}, occurred_at=NOW,
               attempt_id="attempt-1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        log.conn.execute("UPDATE outbound_log SET content='changed'")
    log.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        log.conn.execute("DELETE FROM outbound_log")


def test_success_enforces_cooldown(tmp_path):
    worker, log, adapter = agent(
        tmp_path, environ={"GROWTH_AGENT_ENABLED": "1",
                           "GROWTH_DISCORD_BOT_TOKEN": "bot-test"})
    first = worker.run_once()
    second = worker.run_once()
    assert first["status"] == "sent"
    assert second["status"] == "no_cleared_target"
    assert len(adapter.calls) == 1
    assert worker.plan_targets(now=NOW)[0]["reason"] == "cooldown_active"
    assert worker.plan_targets(now=NOW + timedelta(days=15))[0]["eligible"]


def test_policy_allowlist_blocks_live_post_even_when_enabled(tmp_path):
    blocked = target(policy_cleared=False)
    worker, log, adapter = agent(
        tmp_path, targets=[blocked],
        environ={"GROWTH_AGENT_ENABLED": "1",
                 "GROWTH_DISCORD_BOT_TOKEN": "bot-test"})
    result = worker.run_once()
    assert result["status"] == "no_cleared_target"
    assert result["targets"][0]["reason"] == "policy_not_cleared"
    assert adapter.calls == [] and log.entries() == []


def test_feedback_observation_reweights_converting_target(tmp_path):
    worker, log, _ = agent(
        tmp_path, environ={"GROWTH_AGENT_ENABLED": "1",
                           "GROWTH_DISCORD_BOT_TOKEN": "bot-test"})
    assert worker.run_once()["status"] == "sent"
    before_score = worker.plan_targets(now=NOW)[0]["score"]
    appended = worker.observe_outcomes(snapshot(external=2, payers=2),
                                       now=NOW + timedelta(minutes=1))
    assert appended == 1
    observation = log.entries("outcome_observation")[0]
    assert observation["payload"]["conversion"] is True
    assert observation["payload"]["attribution_scope"] == \
        "regulatory-radar/scan_regulations"
    assert observation["payload"]["distinct_payer_delta"] == 1
    assert observation["payload"]["external_revenue_atomic_delta"] == 250_000
    assert observation["payload"]["first_external_settlement_after"][
        "tx_hash"].startswith("0xfirst-")
    assert worker.plan_targets(now=NOW)[0]["score"] > before_score


def test_feedback_does_not_credit_an_unrelated_route(tmp_path):
    quantity = target(id="quantity-campaign",
                      route="quantity-takeoff/calculate_takeoff")
    worker, log, _ = agent(
        tmp_path, targets=[quantity],
        client=FakeClient(snapshot(external=1, route_external={
            "quantity-takeoff/calculate_takeoff": 0})),
        environ={"GROWTH_AGENT_ENABLED": "1",
                 "GROWTH_DISCORD_BOT_TOKEN": "bot-test"})
    assert worker.run_once()["status"] == "sent"
    # Regulatory Radar converts; Quantity Takeoff did not.
    later = snapshot(external=2, route_external={
        "quantity-takeoff/calculate_takeoff": 0})
    assert worker.observe_outcomes(later, now=NOW + timedelta(days=1)) == 0
    assert worker.observe_outcomes(later, now=NOW + timedelta(days=8)) == 1
    observation = log.entries("outcome_observation")[0]
    assert observation["payload"]["conversion"] is False
    assert observation["payload"]["settlement_delta"] == 0


def test_credentials_are_growth_scoped_only(tmp_path):
    env = {
        "GROWTH_DISCORD_BOT_TOKEN": "discord",
        "GROWTH_GITHUB_TOKEN": "github",
        "GROWTH_SMITHERY_API_KEY": "smithery",
        "GROWTH_OPENAI_API_KEY": "model-only",
        "STRIPE_API_KEY": "must-never-be-read",
        "CDP_API_KEY_SECRET": "must-never-be-read",
    }
    worker, _, _ = agent(tmp_path, environ=env)
    credentials = worker.credentials()
    assert set(credentials) == set(ALLOWED_CREDENTIAL_ENV)
    assert all(not key.startswith(("STRIPE_", "CDP_")) for key in credentials)
    assert "GROWTH_OPENAI_API_KEY" not in credentials


def test_openai_copy_is_grounded_logged_and_sent(tmp_path):
    harness = RecordingHarness()
    worker, log, adapter = agent(
        tmp_path, copywriter=harness,
        environ={"GROWTH_AGENT_ENABLED": "1",
                 "GROWTH_OPENAI_ENABLED": "1",
                 "GROWTH_OPENAI_API_KEY": "model-test",
                 "GROWTH_DISCORD_BOT_TOKEN": "bot-test"})
    result = worker.run_once()
    assert result["status"] == "sent"
    assert result["model"]["mode"] == "openai"
    assert result["model"]["model"] == "gpt-5.6-terra"
    assert len(harness.calls) == 1 and len(adapter.calls) == 1
    assert "GROWTH_OPENAI_API_KEY" not in adapter.calls[0][2]
    rows = log.entries("llm_result")
    assert len(rows) == 1 and rows[0]["payload"]["success"] is True
    assert rows[0]["payload"]["cost_microusd"] == 955
    assert log.entries("send_attempt")[0]["payload"]["model"]["mode"] == "openai"


def test_openai_failure_falls_back_to_grounded_template(tmp_path):
    harness = RecordingHarness(fail=True)
    worker, log, adapter = agent(
        tmp_path, copywriter=harness,
        environ={"GROWTH_AGENT_ENABLED": "1",
                 "GROWTH_OPENAI_ENABLED": "1",
                 "GROWTH_OPENAI_API_KEY": "model-test",
                 "GROWTH_DISCORD_BOT_TOKEN": "bot-test"})
    result = worker.run_once()
    assert result["status"] == "sent"
    assert result["model"]["mode"] == "deterministic_fallback"
    assert adapter.calls[0][1] == render_content(snapshot())
    model_row = log.entries("llm_result")[0]
    assert model_row["payload"]["success"] is False
    assert model_row["payload"]["cost_estimated"] is True
    assert model_row["payload"]["cost_microusd"] == 50_000


def test_monthly_model_budget_is_a_hard_stop(tmp_path):
    harness = RecordingHarness()
    worker, log, adapter = agent(
        tmp_path, copywriter=harness,
        environ={"GROWTH_AGENT_ENABLED": "1",
                 "GROWTH_OPENAI_ENABLED": "1",
                 "GROWTH_OPENAI_API_KEY": "model-test",
                 "GROWTH_OPENAI_MONTHLY_BUDGET_USD": "0.04",
                 "GROWTH_OPENAI_MAX_CALL_RESERVE_USD": "0.05",
                 "GROWTH_DISCORD_BOT_TOKEN": "bot-test"})
    result = worker.run_once()
    assert result["status"] == "sent"
    assert result["model"]["reason"] == "monthly_budget_hard_stop"
    assert harness.calls == []
    assert adapter.calls[0][1] == render_content(snapshot())
    assert log.entries("llm_result")[0]["payload"]["cost_microusd"] == 0


def test_model_spend_is_durable_across_restart(tmp_path):
    db = tmp_path / "growth.sqlite3"
    first = OutboundLog(str(db))
    first.append("llm_result", target(), "copy",
                 {"cost_microusd": 1234}, occurred_at=NOW)
    second = OutboundLog(str(db))
    assert second.monthly_llm_cost_microusd(NOW) == 1234
    assert second.monthly_llm_cost_microusd(
        NOW.replace(month=8)) == 0


def test_smithery_uses_official_owned_listing_api():
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b'{"success":true}'

    def opener(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    adapter = SmitheryMetadataAdapter(opener=opener)
    receipt = adapter.send(
        {"qualified_name": "hartjustin6/quantity-takeoff"}, "live copy",
        {"GROWTH_SMITHERY_API_KEY": "scoped-key"})
    request = captured["request"]
    assert request.full_url.endswith("hartjustin6%2Fquantity-takeoff")
    assert request.method == "PATCH"
    assert request.headers["Authorization"] == "Bearer scoped-key"
    payload = json.loads(request.data)
    assert payload == {
        "description": "live copy",
        "homepage": "https://mcp.viridisconservation.com/agents",
        "unlisted": False,
    }
    assert receipt["updated"] is True


def test_smithery_rejects_non_owned_listing_before_network():
    adapter = SmitheryMetadataAdapter(
        opener=lambda *args, **kwargs: pytest.fail("network must not run"))
    with pytest.raises(GrowthError, match="restricted"):
        adapter.send({"qualified_name": "someone-else/project"}, "copy",
                     {"GROWTH_SMITHERY_API_KEY": "scoped-key"})


def test_owned_github_content_uses_contents_api_not_issues():
    captured = []

    class Response:
        def __init__(self, status, payload):
            self.status = status
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return json.dumps(self.payload).encode()

    def opener(request, timeout):
        captured.append(request)
        if request.get_method() == "GET":
            return Response(200, {"sha": "blob-old"})
        return Response(200, {
            "content": {"html_url": "https://github.test/live-suite"},
            "commit": {"sha": "commit-new"},
        })

    adapter = GitHubOwnedContentAdapter(opener=opener)
    receipt = adapter.send({
        "repo": "jdhart81/viridis-agent-fleet",
        "path": "docs/LIVE_AGENT_SUITE.md",
        "branch": "main",
    }, "grounded live copy", {"GROWTH_GITHUB_TOKEN": "scoped-key"})
    assert len(captured) == 2
    assert captured[0].get_method() == "GET"
    assert captured[1].get_method() == "PUT"
    assert "/contents/docs/LIVE_AGENT_SUITE.md" in captured[1].full_url
    assert "/issues" not in captured[1].full_url
    payload = json.loads(captured[1].data)
    assert payload["sha"] == "blob-old" and payload["branch"] == "main"
    document = __import__("base64").b64decode(payload["content"]).decode()
    assert "grounded live copy" in document
    assert receipt["commit_sha"] == "commit-new"
    assert receipt["updated"] is True


def test_owned_github_content_rejects_other_repo_or_path_before_network():
    adapter = GitHubOwnedContentAdapter(
        opener=lambda *args, **kwargs: pytest.fail("network must not run"))
    credentials = {"GROWTH_GITHUB_TOKEN": "scoped-key"}
    with pytest.raises(GrowthError, match="restricted"):
        adapter.send({"repo": "someone/else",
                      "path": "docs/LIVE_AGENT_SUITE.md"},
                     "copy", credentials)
    with pytest.raises(GrowthError, match="restricted"):
        adapter.send({"repo": "jdhart81/viridis-agent-fleet",
                      "path": "README.md"}, "copy", credentials)


def test_target_missing_its_scoped_credential_is_not_selected(tmp_path):
    github = target(id="owned-doc", platform="github_owned_content",
                    route="*", credential_env="GROWTH_GITHUB_TOKEN")
    worker, _, adapter = agent(
        tmp_path, targets=[github],
        environ={"GROWTH_AGENT_ENABLED": "1"})
    result = worker.run_once()
    assert result["status"] == "no_cleared_target"
    assert result["targets"][0]["reason"] == "credential_missing"
    assert adapter.calls == []


def test_separate_deploy_unit_never_references_money_credentials():
    root = Path(__file__).resolve().parents[1]
    deployment = "\n".join(
        (root / name).read_text()
        for name in ("Dockerfile", "docker-compose.yml", "agent.yaml",
                     ".env.example")
    )
    assert "STRIPE_" not in deployment
    assert "CDP_API_KEY" not in deployment
    assert "deploy/droplet" not in (root / "docker-compose.yml").read_text()
    assert "openai-agents==0.18.3" in (root / "requirements.txt").read_text()
    assert "GROWTH_OPENAI_API_KEY" in deployment
