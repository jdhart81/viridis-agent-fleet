"""Read-only Stripe-to-seat activation reconciliation tests."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import stripe_payments
from viridis_mcp_gateway import _subscription_activation_reconciliation


SHA = "a" * 64


def session(
    session_id,
    *,
    subscription_id=None,
    checkout_status="complete",
    payment_status="paid",
    created=1785369600,
    livemode=True,
    mode="subscription",
    metadata=None,
):
    return {
        "id": session_id,
        "subscription": subscription_id,
        "status": checkout_status,
        "payment_status": payment_status,
        "created": created,
        "livemode": livemode,
        "mode": mode,
        "metadata": metadata or {
            "plan_id": "taxcredit-seat",
            "catalog_sha256": SHA,
        },
    }


def test_provider_list_paginates_filters_and_never_mutates():
    calls = []
    pages = [
        {
            "data": [
                session("cs_live_1", subscription_id="sub_Active1"),
                session("cs_live_ignore", mode="payment"),
            ],
            "has_more": True,
        },
        {
            "data": [
                session(
                    "cs_live_2",
                    checkout_status="open",
                    payment_status="unpaid",
                ),
                session("cs_live_other", metadata={"campaign": "other"}),
            ],
            "has_more": False,
        },
    ]

    def transport(url, headers):
        calls.append((url, headers))
        return pages[len(calls) - 1]

    result = stripe_payments.list_subscription_checkout_evidence(
        created_after_epoch=1785000000,
        api_key="sk_test_secret",
        _transport=transport,
    )
    assert result["status"] == "ok"
    assert result["pages"] == 2
    assert result["provider_mutation"] is False
    assert [item["session_id"] for item in result["sessions"]] == [
        "cs_live_1", "cs_live_2"]
    first = parse_qs(urlparse(calls[0][0]).query)
    second = parse_qs(urlparse(calls[1][0]).query)
    assert first == {"limit": ["100"], "created[gte]": ["1785000000"]}
    assert second["starting_after"] == ["cs_live_ignore"]
    assert calls[0][1]["Authorization"] == "Bearer sk_test_secret"


@pytest.mark.parametrize("pages,error_type", [
    ([{"data": [session("bad")], "has_more": False}], "stripe_error"),
    ([{"data": [], "has_more": True}], "stripe_error"),
])
def test_provider_list_refuses_malformed_or_stalled_evidence(
        pages, error_type):
    result = stripe_payments.list_subscription_checkout_evidence(
        created_after_epoch=1785000000,
        api_key="sk_test_secret",
        _transport=lambda *_: pages[0],
    )
    assert result["status"] == "error"
    assert result["error_type"] == error_type


def test_provider_list_fails_closed_at_page_cap():
    result = stripe_payments.list_subscription_checkout_evidence(
        created_after_epoch=1785000000,
        max_pages=1,
        api_key="sk_test_secret",
        _transport=lambda *_: {
            "data": [session("cs_live_1", subscription_id="sub_Active1")],
            "has_more": True,
        },
    )
    assert result["status"] == "error"
    assert result["error_type"] == "pagination_incomplete"


class Core:
    def __init__(self):
        self.calls = []

    def provider_activation_reconciliation(self, evidence, **kwargs):
        self.calls.append((evidence, kwargs))
        return {
            "schema": "seat-provider-activation-reconciliation-v1",
            "paid_not_activated": 1,
            "identifiers_returned": 0,
            "provider_mutation": False,
            "customer_action_authorized": False,
        }


def test_admin_join_returns_aggregate_and_no_identifiers(monkeypatch):
    monkeypatch.setenv("VIRIDIS_ADMIN_TOKEN", "admin-secret")
    core = Core()

    def provider_list(**kwargs):
        return {
            "status": "ok",
            "sessions": [{
                "session_id": "cs_live_secret",
                "subscription_id": "sub_secret",
            }],
            "timestamp": "2026-07-30T12:00:00+00:00",
            "created_after_epoch": kwargs["created_after_epoch"],
            "pages": 1,
        }

    result = _subscription_activation_reconciliation(
        core,
        "admin-secret",
        30,
        provider_list=provider_list,
        now=datetime(2026, 7, 30, 12, tzinfo=timezone.utc),
    )
    assert result["status"] == "ok"
    assert result["paid_not_activated"] == 1
    encoded = json.dumps(result, sort_keys=True)
    assert "cs_live_secret" not in encoded
    assert "sub_secret" not in encoded
    assert core.calls[0][1]["created_after_epoch"] == 1782820800


def test_admin_join_requires_auth_and_bounds_window(monkeypatch):
    monkeypatch.setenv("VIRIDIS_ADMIN_TOKEN", "admin-secret")
    assert _subscription_activation_reconciliation(
        Core(), "wrong")["error_type"] == "unauthorized"
    assert _subscription_activation_reconciliation(
        Core(), "admin-secret", 0)["error_type"] == "bad_lookback_days"


def test_admin_join_sanitizes_core_refusal(monkeypatch):
    monkeypatch.setenv("VIRIDIS_ADMIN_TOKEN", "admin-secret")

    class RefusingCore:
        def provider_activation_reconciliation(self, *_args, **_kwargs):
            raise RuntimeError("cs_live_customer_secret")

    result = _subscription_activation_reconciliation(
        RefusingCore(),
        "admin-secret",
        provider_list=lambda **kwargs: {
            "status": "ok",
            "sessions": [],
            "timestamp": "2026-07-30T12:00:00+00:00",
            "created_after_epoch": kwargs["created_after_epoch"],
            "pages": 1,
        },
        now=datetime(2026, 7, 30, 12, tzinfo=timezone.utc),
    )
    assert result["status"] == "error"
    assert "customer_secret" not in json.dumps(result)
