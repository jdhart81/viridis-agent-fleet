"""FA-B1..B6 safety and autonomy tests for the isolated growth worker."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import main as scheduler
from growth_agent import (
    ALLOWED_CREDENTIAL_ENV,
    FleetSnapshot,
    GeneratedCopy,
    GitHubAppTokenProvider,
    GitHubOwnedContentAdapter,
    GrowthAgent,
    GrowthError,
    LiveFleetClient,
    ModelUsage,
    OutboundLog,
    PAID_DELIVERY_RECEIPT_COPY,
    PAID_DELIVERY_RECEIPT_VERSION,
    REPEAT_BUYER_CTA,
    REGULATORY_RADAR_REPEAT_AUTHORIZATION,
    REGULATORY_RADAR_REPEAT_CAMPAIGN,
    SmitheryMetadataAdapter,
    render_regulatory_radar_repeat,
    render_content,
    render_owned_discovery,
    validate_generated_content,
)


NOW = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)


def snapshot(*, external=1, payers=1, repeats=0, intro=False,
             route_external=None, watch_live=True):
    routes = [
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
    ]
    if watch_live:
        routes.append({
            "agent": "regulatory-radar",
            "tool": "monitor_changes",
            "endpoint": "/x402/regulatory-radar/monitor_changes",
            "price_minor": 25,
            "amount_atomic_usdc": 250_000,
            "description": (
                "Bounded source-linked regulatory deadline and date watch."),
        })
    route_counts = {
        "quantity-takeoff/calculate_takeoff": 0,
        "regulatory-radar/scan_regulations": external,
        **({"regulatory-radar/monitor_changes": 0} if watch_live else {}),
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
            "repeat_external_purchases": (
                min(repeats, count)
                if route == "regulatory-radar/scan_regulations" else 0
            ),
            "external_revenue_atomic": count * 250_000,
            "first_external_settlement": (
                {"tx_hash": f"0xfirst-{route}",
                 "timestamp": "2026-07-20T00:00:00Z"}
                if count else None),
        }
    return FleetSnapshot(
        routes=tuple(routes),
        metrics={
            "settlements_total": external,
            "self_settlements": 0,
            "external_settlements": external,
            "distinct_external_payers": payers,
            "repeat_external_purchases": repeats,
            "external_revenue_atomic": external * 250_000,
            "external_paid_results_delivered": 0,
            "external_paid_results_failed": 0,
            "external_paid_results_receipted": 0,
            "external_paid_results_unknown": external,
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
        self.surface_calls = 0

    def fetch(self, *, now):
        self.calls += 1
        return self.value

    def verify_repeat_campaign_surfaces(self, value):
        assert value is self.value
        self.surface_calls += 1
        return {
            "quickstart": "a" * 64,
            "llms": "b" * 64,
            "buyer_skill": "c" * 64,
        }


class JsonResponse:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit):
        assert len(self.payload) <= limit
        return self.payload


class TextResponse(JsonResponse):
    def __init__(self, payload, status=200):
        self.payload = str(payload).encode()
        self.status = status


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


class FakeGitHubTokenProvider:
    def __init__(self, token="installation-token"):
        self.value = token
        self.calls = []

    def token(self, credentials):
        self.calls.append(dict(credentials))
        return self.value


class FailingCycleAgent:
    def __init__(self, exc):
        self.exc = exc
        self.calls = []

    def run_once(self, *, dry_run):
        self.calls.append(dry_run)
        raise self.exc


def test_scheduler_survives_expected_live_read_failure():
    agent = FailingCycleAgent(GrowthError(
        "live fleet health read failed: HTTPError"))

    result = scheduler.run_cycle(agent, dry_run=False)

    assert agent.calls == [False]
    assert result == {
        "status": "cycle_failed",
        "error_type": "GrowthError",
        "message": "live fleet health read failed: HTTPError",
        "send_attempted": False,
    }


def test_scheduler_does_not_hide_unexpected_programming_errors():
    agent = FailingCycleAgent(RuntimeError("bug"))

    with pytest.raises(RuntimeError, match="bug"):
        scheduler.run_cycle(agent, dry_run=True)


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
        "campaigns": [REGULATORY_RADAR_REPEAT_CAMPAIGN],
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
    assert content.startswith("Start here: Regulatory Radar")
    assert "one bounded x402 compliance scan on Base" in content
    assert "Inspect the live unpaid quote before signing" in content
    assert "quantity-takeoff — $0.50" in content
    assert "regulatory-radar — $0.25" in content
    assert "First paid call from a new wallet is $0.01." in content
    assert "2 settlement(s) from 2 distinct payer(s)" in content
    assert REPEAT_BUYER_CTA in content
    assert "X402-Payer-Address" in content
    assert "never send a private key" in content
    assert PAID_DELIVERY_RECEIPT_VERSION in content
    assert "Buyer acceptance and usefulness remain unobserved." in content
    assert "https://example.test/quickstart" in content


def test_owned_discovery_requires_live_security_and_preserves_route_identity():
    from dataclasses import replace
    base = snapshot(intro=True)
    assert render_owned_discovery(base) == render_content(base)
    live = replace(base, routes=base.routes + ({
        "agent": "security-preflight", "tool": "security_preflight",
        "price_minor": 175,
    },))
    content = render_owned_discovery(live)
    assert "security-preflight/quickstart" in content
    assert "security-preflight/security_preflight — $1.75" in content
    assert "regulatory-radar/scan_regulations — $0.25" in content
    assert "regulatory-radar/monitor_changes — $0.25" in content
    assert "may be $0.01" in content
    assert "not evidence of Security purchases" in content


def test_owned_discovery_does_not_invoke_model_or_change_discord(tmp_path):
    from dataclasses import replace
    live = replace(snapshot(), routes=snapshot().routes + ({
        "agent": "security-preflight", "tool": "security_preflight",
        "price_minor": 100,
    },))
    class ForbiddenWriter:
        def generate(self, *args, **kwargs):
            raise AssertionError("owned copy must not call a model")
    worker, _, _ = agent(tmp_path, copywriter=ForbiddenWriter(), environ={
        "GROWTH_OPENAI_ENABLED": "1"})
    content, metadata = worker._render_for_target(
        live, {"platform": "github_owned_content"}, now=NOW)
    assert content == render_owned_discovery(live)
    assert metadata["reason"] == "owned_buyer_walkthrough"
    assert "$0.01" not in content
    assert render_content(snapshot()).startswith("Start here: Regulatory Radar")


def test_live_market_only_promotes_independently_verified_funding():
    base = snapshot(external=1)
    health = {
        "status": "ok",
        "payment_gate": {
            "x402": {
                "enabled": True,
                "http_front_door": list(base.routes),
                "http_settlement_telemetry": {
                    "total": base.metrics,
                    "per_route": base.route_metrics,
                },
                "intro_pricing": {"enabled": False},
            },
        },
        "human_surfaces": {
            "agents": base.agents_url,
            "quickstart": base.quickstart_url,
        },
    }
    catalog = {
        "open_work": [
            {
                "work_id": "work_unverified",
                "title": "Unverified listing",
                "budget_minor": 5000,
                "currency": "USD",
                "funding_status": "UNVERIFIED",
            },
            {
                "work_id": "work_missing_status",
                "title": "Unknown funding listing",
                "budget_minor": 4000,
                "currency": "USD",
            },
            {
                "work_id": "work_verified",
                "title": "Verified funded listing",
                "budget_minor": 2500,
                "currency": "USD",
                "funding_status": "VERIFIED",
            },
        ],
    }

    def opener(request, timeout):
        assert timeout == 10
        if request.full_url.startswith("https://example.test/health?"):
            return JsonResponse(health)
        if request.full_url.startswith("https://example.test/catalog?"):
            return JsonResponse(catalog)
        raise AssertionError(f"unexpected URL: {request.full_url}")

    live = LiveFleetClient(
        health_url="https://example.test/health",
        market_catalog_url="https://example.test/catalog",
        opener=opener,
    ).fetch(now=NOW)

    assert [job["work_id"] for job in live.open_work] == ["work_verified"]
    assert live.open_work[0]["funding_status"] == "VERIFIED"
    content = render_content(live)
    assert "Independently funded work for outside agents:" in content
    assert "work_verified" in content
    assert "work_unverified" not in content
    assert "work_missing_status" not in content


def test_live_market_with_only_unverified_inventory_claims_no_paid_work():
    base = snapshot(external=1)
    health = {
        "status": "ok",
        "payment_gate": {
            "x402": {
                "enabled": True,
                "http_front_door": list(base.routes),
                "http_settlement_telemetry": {
                    "total": base.metrics,
                    "per_route": base.route_metrics,
                },
                "intro_pricing": {"enabled": False},
            },
        },
    }
    catalog = {
        "open_work": [{
            "work_id": "work_unverified",
            "title": "Unverified listing",
            "budget_minor": 5000,
            "currency": "USD",
            "funding_status": "UNVERIFIED",
        }],
    }

    def opener(request, timeout):
        del timeout
        payload = (health if "/health?" in request.full_url else catalog)
        return JsonResponse(payload)

    live = LiveFleetClient(
        health_url="https://example.test/health",
        market_catalog_url="https://example.test/catalog",
        opener=opener,
    ).fetch(now=NOW)
    content = render_content(live)

    assert live.open_work == ()
    assert "paid work" not in content.lower()
    assert "work_unverified" not in content
    assert "$50.00" not in content


def test_repeat_campaign_surface_gate_reads_all_public_buyer_paths():
    live = snapshot()
    urls = []
    machine = (
        "--route regulatory-watch --max-payment-usdc 0.25\n"
        "exactly one fresh paid attempt over the curated, source-linked "
        "dataset\n"
        "not a subscription or live external regulatory feed"
    )

    def opener(request, timeout):
        assert timeout == 10
        urls.append(request.full_url)
        if request.full_url.endswith("/quickstart"):
            return TextResponse(
                '<h3 id="radar-watch-call">Watch</h3>\n' + machine)
        return TextResponse(machine)

    receipt = LiveFleetClient(opener=opener).verify_repeat_campaign_surfaces(
        live)

    assert urls == [
        "https://example.test/quickstart",
        "https://example.test/llms.txt",
        "https://example.test/.well-known/skills/"
        "viridis-paid-tools/SKILL.md",
    ]
    assert set(receipt) == {"quickstart", "llms", "buyer_skill"}
    assert all(len(value) == 64 for value in receipt.values())


def test_repeat_campaign_surface_gate_fails_closed_on_stale_machine_copy():
    live = snapshot()

    def opener(request, timeout):
        del timeout
        if request.full_url.endswith("/quickstart"):
            return TextResponse(
                '<h3 id="radar-watch-call">Watch</h3>\n'
                "--route regulatory-watch --max-payment-usdc 0.25\n"
                "exactly one fresh paid attempt over the curated, "
                "source-linked dataset\n"
                "not a subscription or live external regulatory feed"
            )
        return TextResponse("old new-wallet-only instructions")

    with pytest.raises(GrowthError, match="omits the repeat campaign command"):
        LiveFleetClient(opener=opener).verify_repeat_campaign_surfaces(live)


def test_repeat_campaign_fails_before_surface_reads_when_watch_is_not_live():
    live = snapshot(watch_live=False)

    with pytest.raises(
            GrowthError, match="dated-watch route is not live"):
        LiveFleetClient(
            opener=lambda *args, **kwargs: pytest.fail(
                "surface reads must wait for the live watch route")
        ).verify_repeat_campaign_surfaces(live)


def test_open_market_work_is_promoted_with_exact_live_budget_and_id():
    base = snapshot(external=1)
    live = FleetSnapshot(
        routes=base.routes, metrics=base.metrics,
        route_metrics=base.route_metrics, intro_enabled=base.intro_enabled,
        agents_url=base.agents_url, quickstart_url=base.quickstart_url,
        captured_at=base.captured_at,
        market_url="https://mcp.viridisconservation.com/network/catalog",
        open_work=({"work_id": "work_abc12345",
                    "title": "Build a LangGraph adapter",
                    "budget_minor": 2500, "currency": "USD"},))
    content = render_content(live)
    assert "Independently funded work for outside agents:" in content
    assert "$25.00 — Build a LangGraph adapter (work_abc12345)" in content
    assert live.market_url in content
    assert validate_generated_content(content, live) == content
    with pytest.raises(GrowthError, match="altered or omitted an open job"):
        validate_generated_content(content.replace("$25.00", "$30.00"), live)


def test_full_live_market_content_stays_within_posting_limit():
    base = snapshot(external=1)
    routes = tuple(
        {
            "agent": f"agent-{index}",
            "tool": f"tool-{index}",
            "endpoint": f"/x402/agent-{index}/tool-{index}",
            "price_minor": 25 + index,
            "amount_atomic_usdc": (25 + index) * 10_000,
            "description": "Detailed deterministic climate workflow " * 20,
        }
        for index in range(5)
    )
    jobs = tuple(
        {
            "work_id": f"work_production_{index}",
            "title": "Build and verify an agent-market integration " * 8,
            "budget_minor": 2500 + index * 2500,
            "currency": "USD",
        }
        for index in range(3)
    )
    live = FleetSnapshot(
        routes=routes, metrics=base.metrics,
        route_metrics=base.route_metrics, intro_enabled=True,
        agents_url=base.agents_url, quickstart_url=base.quickstart_url,
        captured_at=base.captured_at,
        market_url="https://mcp.viridisconservation.com/network/catalog",
        open_work=jobs)
    content = render_content(live)
    assert len(content) <= 1900
    for job in jobs:
        assert job["work_id"] in content
        assert f"${job['budget_minor'] / 100:.2f}" in content
    assert validate_generated_content(content, live) == content


def test_large_live_suite_without_verified_work_compacts_to_posting_limit():
    base = snapshot(external=1)
    routes = tuple(
        {
            "agent": f"agent-{index}",
            "tool": f"tool-{index}",
            "endpoint": f"/x402/agent-{index}/tool-{index}",
            "price_minor": 25 + index,
            "amount_atomic_usdc": (25 + index) * 10_000,
            "description": "Detailed deterministic climate workflow " * 20,
        }
        for index in range(6)
    )
    live = FleetSnapshot(
        routes=routes, metrics=base.metrics,
        route_metrics=base.route_metrics, intro_enabled=False,
        agents_url=base.agents_url, quickstart_url=base.quickstart_url,
        captured_at=base.captured_at,
        market_url="https://mcp.viridisconservation.com/network/catalog",
        open_work=())

    content = render_content(live)

    assert len(content) <= 1900
    assert "Detailed deterministic climate workflow" not in content
    for route in routes:
        assert route["agent"] in content
        assert f"${route['price_minor'] / 100:.2f}" in content
    assert "paid work" not in content.lower()
    assert validate_generated_content(content, live) == content


def test_generated_copy_validator_refuses_price_or_claim_drift():
    live = snapshot(external=2, payers=2, intro=True)
    content = render_content(live)
    assert validate_generated_content(content, live) == content
    with pytest.raises(GrowthError, match="route or exact live price"):
        validate_generated_content(content.replace("$0.50", "$0.40"), live)
    with pytest.raises(GrowthError, match="prohibited claim"):
        validate_generated_content(content + "\nGuaranteed compliance.", live)
    with pytest.raises(GrowthError, match="omitted repeat-buyer guidance"):
        validate_generated_content(content.replace(REPEAT_BUYER_CTA, ""), live)
    with pytest.raises(GrowthError, match="paid-delivery receipt boundary"):
        validate_generated_content(
            content.replace(PAID_DELIVERY_RECEIPT_COPY, ""), live)


def test_repeat_buyer_guidance_requires_live_external_proof():
    content = render_content(snapshot(external=0, payers=0))
    assert REPEAT_BUYER_CTA not in content
    assert validate_generated_content(content, snapshot(
        external=0, payers=0)) == content


def test_live_snapshot_refuses_incomplete_or_unhealthy_health():
    with pytest.raises(GrowthError, match="not ok"):
        FleetSnapshot.from_health({"status": "degraded"},
                                  captured_at=NOW.isoformat())
    with pytest.raises(GrowthError, match="not enabled"):
        FleetSnapshot.from_health(
            {"status": "ok", "payment_gate": {"x402": {"enabled": False}}},
            captured_at=NOW.isoformat())

    base = snapshot()
    total = dict(base.metrics)
    total.pop("external_paid_results_receipted")
    health = {
        "status": "ok",
        "payment_gate": {"x402": {
            "enabled": True,
            "http_front_door": list(base.routes),
            "http_settlement_telemetry": {
                "total": total,
                "per_route": base.route_metrics,
            },
        }},
    }
    with pytest.raises(GrowthError, match="conversion metrics are incomplete"):
        FleetSnapshot.from_health(health, captured_at=NOW.isoformat())

    total["external_paid_results_receipted"] = 1
    total["external_paid_results_delivered"] = 0
    with pytest.raises(GrowthError, match="paid-delivery metrics are inconsistent"):
        FleetSnapshot.from_health(health, captured_at=NOW.isoformat())


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


def test_repeat_campaign_dry_run_is_exact_bounded_and_model_free(tmp_path):
    copywriter = RecordingHarness(fail=True)
    worker, log, adapter = agent(
        tmp_path,
        copywriter=copywriter,
        environ={
            "GROWTH_AGENT_ENABLED": "1",
            "GROWTH_OPENAI_ENABLED": "1",
            "GROWTH_OPENAI_API_KEY": "must-not-be-used",
            "GROWTH_CAMPAIGN": REGULATORY_RADAR_REPEAT_CAMPAIGN,
        },
    )

    result = worker.run_once(dry_run=True)

    assert result["status"] == "dry_run"
    assert result["campaign"] == REGULATORY_RADAR_REPEAT_CAMPAIGN
    assert result["target"]["route"] == \
        "regulatory-radar/monitor_changes"
    assert "--route regulatory-watch --max-payment-usdc 0.25" \
        in result["content"]
    assert "exactly one fresh-quote call" in result["content"]
    assert "No subscription, automatic retry, later-call authority" \
        in result["content"]
    assert result["content"].endswith(
        "https://example.test/quickstart#radar-watch-call")
    assert result["model"] == {
        "mode": "deterministic",
        "reason": "dry_run_no_api",
    }
    assert copywriter.calls == []
    assert adapter.calls == []
    assert log.entries() == []


def test_repeat_campaign_requires_exact_authorization_before_network(tmp_path):
    worker, log, adapter = agent(
        tmp_path,
        client=NeverClient(),
        environ={
            "GROWTH_AGENT_ENABLED": "1",
            "GROWTH_CAMPAIGN": REGULATORY_RADAR_REPEAT_CAMPAIGN,
            "GROWTH_CAMPAIGN_AUTHORIZATION": "almost",
        },
    )

    result = worker.run_once()

    assert result == {
        "status": "campaign_not_authorized",
        "campaign": REGULATORY_RADAR_REPEAT_CAMPAIGN,
        "required_authorization": REGULATORY_RADAR_REPEAT_AUTHORIZATION,
        "send_attempted": False,
    }
    assert adapter.calls == []
    assert log.entries() == []


def test_repeat_campaign_uses_one_allowlisted_target_and_route_attribution(
        tmp_path):
    blocked_for_campaign = target(
        id="other-owned-channel",
        base_weight=10,
        campaigns=[],
    )
    allowed = target(id="repeat-owned-channel", route="*", base_weight=1)
    worker, log, adapter = agent(
        tmp_path,
        targets=[blocked_for_campaign, allowed],
        environ={
            "GROWTH_AGENT_ENABLED": "1",
            "GROWTH_CAMPAIGN": REGULATORY_RADAR_REPEAT_CAMPAIGN,
            "GROWTH_CAMPAIGN_AUTHORIZATION":
                REGULATORY_RADAR_REPEAT_AUTHORIZATION,
            "GROWTH_DISCORD_BOT_TOKEN": "bot-test",
            "GROWTH_OPENAI_ENABLED": "1",
            "GROWTH_OPENAI_API_KEY": "must-not-be-used",
        },
    )

    result = worker.run_once()

    assert result["status"] == "sent"
    assert result["target"] == "repeat-owned-channel"
    assert len(adapter.calls) == 1
    assert adapter.calls[0][0]["route"] == \
        "regulatory-radar/monitor_changes"
    attempt = log.entries("send_attempt")[0]
    assert attempt["payload"]["campaign"] == \
        REGULATORY_RADAR_REPEAT_CAMPAIGN
    assert attempt["payload"]["attribution_scope"] == \
        "regulatory-radar/monitor_changes"
    plan = worker.plan_targets(now=NOW)
    other = next(item for item in plan
                 if item["id"] == "other-owned-channel")
    assert other["reason"] == "campaign_not_allowed"


def test_repeat_campaign_stops_when_live_repeat_exists(tmp_path):
    worker, log, adapter = agent(
        tmp_path,
        client=FakeClient(snapshot(external=2, payers=1, repeats=1)),
        environ={
            "GROWTH_AGENT_ENABLED": "1",
            "GROWTH_CAMPAIGN": REGULATORY_RADAR_REPEAT_CAMPAIGN,
            "GROWTH_CAMPAIGN_AUTHORIZATION":
                REGULATORY_RADAR_REPEAT_AUTHORIZATION,
            "GROWTH_DISCORD_BOT_TOKEN": "bot-test",
        },
    )

    result = worker.run_once()

    assert result == {
        "status": "campaign_complete",
        "campaign": REGULATORY_RADAR_REPEAT_CAMPAIGN,
        "send_attempted": False,
    }
    assert adapter.calls == []
    assert log.entries() == []


def test_dry_run_never_calls_paid_copywriter_when_openai_flag_drifts(tmp_path):
    copywriter = RecordingHarness(fail=True)
    worker, log, adapter = agent(
        tmp_path,
        copywriter=copywriter,
        environ={
            "GROWTH_AGENT_ENABLED": "1",
            "GROWTH_OPENAI_ENABLED": "1",
            "GROWTH_OPENAI_API_KEY": "must-not-be-used",
        },
    )

    result = worker.run_once(dry_run=True)

    assert result["status"] == "dry_run"
    assert result["model"] == {
        "mode": "deterministic",
        "reason": "dry_run_no_api",
    }
    assert result["send_attempted"] is False
    assert copywriter.calls == []
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
        "GROWTH_GITHUB_APP_ID": "123",
        "GROWTH_GITHUB_INSTALLATION_ID": "456",
        "GROWTH_GITHUB_PRIVATE_KEY_PATH": "/run/secrets/key.pem",
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


def test_agent_market_smithery_uses_catalog_homepage():
    captured = {}

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit): return b'{"success":true}'

    def opener(request, timeout):
        captured["request"] = request
        return Response()

    adapter = SmitheryMetadataAdapter(opener=opener)
    receipt = adapter.send({
        "qualified_name": "hartjustin6/agent-market-network",
        "homepage": "https://mcp.viridisconservation.com/network/catalog",
    }, "live market copy", {"GROWTH_SMITHERY_API_KEY": "scoped-key"})
    request = captured["request"]
    assert request.full_url.endswith("hartjustin6%2Fagent-market-network")
    assert json.loads(request.data)["homepage"] == \
        "https://mcp.viridisconservation.com/network/catalog"
    assert receipt["updated"] is True


def test_smithery_rejects_non_viridis_homepage_before_network():
    adapter = SmitheryMetadataAdapter(
        opener=lambda *args, **kwargs: pytest.fail("network must not run"))
    with pytest.raises(GrowthError, match="homepage is restricted"):
        adapter.send({
            "qualified_name": "hartjustin6/agent-market-network",
            "homepage": "https://example.test/redirect",
        }, "copy", {"GROWTH_SMITHERY_API_KEY": "scoped-key"})


def test_root_dockerignore_blocks_all_environment_variants():
    patterns = set((Path(__file__).resolve().parents[2] / ".dockerignore")
                   .read_text().splitlines())
    assert ".env*" in patterns
    assert "**/.env*" in patterns


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

    provider = FakeGitHubTokenProvider()
    adapter = GitHubOwnedContentAdapter(
        opener=opener, token_provider=provider)
    receipt = adapter.send({
        "repo": "jdhart81/viridis-agent-fleet",
        "path": "docs/LIVE_AGENT_SUITE.md",
        "branch": "main",
    }, "grounded live copy", {
        "GROWTH_GITHUB_APP_ID": "123",
        "GROWTH_GITHUB_INSTALLATION_ID": "456",
        "GROWTH_GITHUB_PRIVATE_KEY_PATH": "/run/secrets/key.pem",
    })
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
    assert len(provider.calls) == 1
    assert captured[0].headers["Authorization"] == \
        "Bearer installation-token"


def test_owned_github_content_rejects_other_repo_or_path_before_network():
    adapter = GitHubOwnedContentAdapter(
        opener=lambda *args, **kwargs: pytest.fail("network must not run"),
        token_provider=FakeGitHubTokenProvider())
    credentials = {
        "GROWTH_GITHUB_APP_ID": "123",
        "GROWTH_GITHUB_INSTALLATION_ID": "456",
        "GROWTH_GITHUB_PRIVATE_KEY_PATH": "/run/secrets/key.pem",
    }
    with pytest.raises(GrowthError, match="restricted"):
        adapter.send({"repo": "someone/else",
                      "path": "docs/LIVE_AGENT_SUITE.md"},
                     "copy", credentials)
    with pytest.raises(GrowthError, match="restricted"):
        adapter.send({"repo": "jdhart81/viridis-agent-fleet",
                      "path": "README.md"}, "copy", credentials)


def test_target_missing_its_scoped_credential_is_not_selected(tmp_path):
    github = target(id="owned-doc", platform="github_owned_content",
                    route="*", credential_envs=[
                        "GROWTH_GITHUB_APP_ID",
                        "GROWTH_GITHUB_INSTALLATION_ID",
                        "GROWTH_GITHUB_PRIVATE_KEY_PATH",
                    ])
    worker, _, adapter = agent(
        tmp_path, targets=[github],
        environ={"GROWTH_AGENT_ENABLED": "1"})
    result = worker.run_once()
    assert result["status"] == "no_cleared_target"
    assert result["targets"][0]["reason"] == "credential_missing"
    assert adapter.calls == []


def test_github_app_provider_mints_and_caches_one_hour_token(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    captured = []

    class Response:
        status = 201
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit):
            return json.dumps({
                "token": "short-lived-installation-token",
                "expires_at": "2026-07-20T19:00:00Z",
            }).encode()

    def opener(request, timeout):
        captured.append(request)
        return Response()

    provider = GitHubAppTokenProvider(opener=opener, now_fn=lambda: NOW)
    credentials = {
        "GROWTH_GITHUB_APP_ID": "123",
        "GROWTH_GITHUB_INSTALLATION_ID": "456",
        "GROWTH_GITHUB_PRIVATE_KEY_PATH": str(key_path),
    }
    assert provider.token(credentials) == "short-lived-installation-token"
    assert provider.token(credentials) == "short-lived-installation-token"
    assert len(captured) == 1
    request = captured[0]
    assert request.full_url.endswith("/app/installations/456/access_tokens")
    assert request.headers["Authorization"].startswith("Bearer eyJ")
    payload = json.loads(request.data)
    assert payload["repositories"] == ["viridis-agent-fleet"]
    assert payload["permissions"] == {"contents": "write"}


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
