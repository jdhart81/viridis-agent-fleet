from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

import pytest


ADAPTER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADAPTER_DIR))

import app as adapter  # noqa: E402


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def health(self):
        return {"status": "ok"}

    async def scan(self, brief):
        self.calls.append(dict(brief))
        return {"regulatory_scan": {"status": "success", "count": 1}}


class FakePlatform:
    def __init__(self):
        self.completed = []
        self.failed = []
        self.replies = []

    async def complete_job(self, event, result):
        self.completed.append((dict(event), dict(result)))
        return {"ok": True}

    async def fail_job(self, event, reason):
        self.failed.append((dict(event), reason))
        return {"ok": True}

    async def reply_to_inquiry(self, thread_id):
        self.replies.append(thread_id)
        return {"ok": True}


@pytest.fixture
def config(tmp_path):
    return adapter.Config(
        api_key="api-test",
        webhook_secret="webhook-test",
        state_db=str(tmp_path / "events.sqlite3"),
        radar_package_root=str(
            Path(__file__).resolve().parents[3] / "regulatory-radar-agent"
        ),
        service_id="svc-radar",
    )


@pytest.fixture
def service(config):
    runner = FakeRunner()
    platform = FakePlatform()
    ledger = adapter.EventLedger(config.state_db)
    instance = adapter.WebhookService(
        config,
        ledger,
        runner,
        platform,
        now=lambda: 1_700_000_000,
    )
    return instance, runner, platform


def signed(event, *, secret="webhook-test", api_key="api-test"):
    raw = json.dumps(event, separators=(",", ":")).encode()
    timestamp = "1700000000"
    signature = "sha256=" + hmac.new(
        secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    return raw, {
        "x-platform-secret": api_key,
        "x-webhook-timestamp": timestamp,
        "x-webhook-signature": signature,
    }


def test_verify_webhook_accepts_current_signature():
    raw, headers = signed({"type": "test", "id": "one"})
    assert adapter.verify_webhook(
        raw,
        headers["x-webhook-signature"],
        headers["x-webhook-timestamp"],
        "webhook-test",
        now=1_700_000_000,
    )


def test_verify_webhook_rejects_stale_signature():
    raw, headers = signed({"type": "test", "id": "one"})
    assert not adapter.verify_webhook(
        raw,
        headers["x-webhook-signature"],
        headers["x-webhook-timestamp"],
        "webhook-test",
        now=1_700_000_301,
    )


@pytest.mark.asyncio
async def test_job_dispatch_completes_once(service):
    instance, runner, platform = service
    event = {
        "type": "job_dispatch",
        "job_id": "job-one",
        "service_id": "svc-radar",
        "brief": {
            "jurisdiction": "US",
            "sector": "energy",
            "query": "45V emissions disclosure",
        },
        "callback_url": (
            "https://api.the402.ai/v1/threads/thread-one/update"
        ),
    }
    raw, headers = signed(event)

    code, response = await instance.handle(raw, headers)
    replay_code, replay = await instance.handle(raw, headers)

    assert code == 200
    assert response["status"] == "completed"
    assert replay_code == 200
    assert replay["idempotent_replay"] is True
    assert len(runner.calls) == 1
    assert len(platform.completed) == 1


@pytest.mark.asyncio
async def test_duplicate_event_with_different_body_conflicts(service):
    instance, _, _ = service
    base = {
        "type": "thread_inquiry",
        "thread_id": "thread-one",
        "service_id": "svc-radar",
        "message": "hello",
    }
    raw, headers = signed(base)
    assert (await instance.handle(raw, headers))[0] == 200

    changed = {**base, "message": "different"}
    changed_raw, changed_headers = signed(changed)
    code, response = await instance.handle(changed_raw, changed_headers)

    assert code == 409
    assert response["error"] == "idempotency conflict"


@pytest.mark.asyncio
async def test_thread_inquiry_gets_one_inbound_reply(service):
    instance, _, platform = service
    event = {
        "type": "thread_inquiry",
        "thread_id": "thread-two",
        "service_id": "svc-radar",
        "message": "Can this scan US hydrogen tax-credit rules?",
    }
    raw, headers = signed(event)

    first = await instance.handle(raw, headers)
    second = await instance.handle(raw, headers)

    assert first[0] == 200
    assert first[1]["replied"] is True
    assert second[1]["idempotent_replay"] is True
    assert platform.replies == ["thread-two"]


@pytest.mark.asyncio
async def test_request_created_never_autobids(service):
    instance, runner, platform = service
    raw, headers = signed(
        {
            "type": "request.created",
            "posting_id": "post-one",
            "title": "Need a regulatory scan",
        }
    )

    code, response = await instance.handle(raw, headers)

    assert code == 200
    assert response["status"] == "ignored"
    assert response["reason"] == "automatic bidding is disabled"
    assert runner.calls == []
    assert platform.completed == []


@pytest.mark.asyncio
async def test_invalid_brief_reports_failure_without_running(service):
    instance, runner, platform = service
    raw, headers = signed(
        {
            "type": "job_dispatch",
            "job_id": "job-bad",
            "service_id": "svc-radar",
            "brief": {
                "jurisdiction": "mars",
                "sector": "energy",
                "query": "rules",
            },
            "callback_url": (
                "https://api.the402.ai/v1/threads/thread-bad/update"
            ),
        }
    )

    code, response = await instance.handle(raw, headers)

    assert code == 200
    assert response["status"] == "failed"
    assert runner.calls == []
    assert len(platform.failed) == 1


@pytest.mark.asyncio
async def test_wrong_platform_secret_is_rejected(service):
    instance, _, _ = service
    raw, headers = signed(
        {
            "type": "thread_inquiry",
            "thread_id": "thread-three",
            "service_id": "svc-radar",
        },
        api_key="wrong",
    )
    with pytest.raises(adapter.AuthenticationError):
        await instance.handle(raw, headers)


def test_callback_url_rejects_ssrf():
    with pytest.raises(adapter.CallbackError):
        adapter.validate_callback_url(
            "https://example.com/v1/threads/thread-one/update"
        )
    with pytest.raises(adapter.CallbackError):
        adapter.validate_callback_url(
            "https://api.the402.ai.evil.example/v1/threads/x/update"
        )
    assert adapter.validate_callback_url(
        "https://api.the402.ai/v1/threads/thread-one/update"
    ) == "https://api.the402.ai/v1/threads/thread-one/update"


@pytest.mark.asyncio
async def test_real_radar_runner_uses_isolated_package():
    package_root = Path(__file__).resolve().parents[3] / "regulatory-radar-agent"
    runner = adapter.RadarRunner(str(package_root))
    result = await runner.scan(
        {
            "jurisdiction": "us",
            "sector": "energy",
            "query": "45V emissions disclosure",
        }
    )
    assert result["service"] == "Viridis Regulatory Radar"
    assert result["regulatory_scan"]["status"] == "success"
    assert "legal" in result["claim_boundary"].lower()


def test_signature_comparison_is_not_plain_equality(monkeypatch):
    calls = []
    original = hmac.compare_digest

    def observed(left, right):
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(adapter.hmac, "compare_digest", observed)
    raw, headers = signed({"type": "test", "id": "one"})
    adapter.verify_webhook(
        raw,
        headers["x-webhook-signature"],
        headers["x-webhook-timestamp"],
        "webhook-test",
        now=1_700_000_000,
    )
    assert calls
