"""Contracts for the paid Compliance Snapshot human front door."""

from __future__ import annotations

import sys
from pathlib import Path

from starlette.testclient import TestClient

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import stripe_payments  # noqa: E402
import viridis_mcp_gateway as gateway  # noqa: E402


VALID_ORDER = {
    "email": "buyer@example.test",
    "company": "Example Components",
    "jurisdiction": "EU",
    "sector": "manufacturing",
    "question": (
        "Which 2026 and 2027 climate requirements should we investigate first?"
    ),
    "website": "",
}


def _client(tmp_path, monkeypatch, *, create_checkout, verify_session=None):
    monkeypatch.setenv("STATE_DB", str(tmp_path / "gateway.db"))
    monkeypatch.setenv(
        "PUBLIC_BASE", "https://mcp.viridisconservation.com")
    monkeypatch.setattr(stripe_payments, "create_checkout", create_checkout)
    if verify_session is not None:
        monkeypatch.setattr(
            stripe_payments, "verify_session", verify_session)
    old_members = gateway.EXTERNAL_MEMBERS
    gateway.EXTERNAL_MEMBERS = []
    client = TestClient(gateway.build_app())
    client.__enter__()

    def close():
        try:
            client.__exit__(None, None, None)
        finally:
            gateway.EXTERNAL_MEMBERS = old_members

    return client, close


def test_snapshot_page_checkout_and_paid_success_are_attributed(
        tmp_path, monkeypatch):
    created = []

    def create_checkout(amount, product, **kwargs):
        created.append((amount, product, kwargs))
        return {
            "status": "ok",
            "url": "https://checkout.stripe.com/c/pay/cs_live_snapshot",
            "session_id": "cs_live_snapshot",
            "amount_cents": amount,
            "currency": "usd",
            "livemode": True,
        }

    def verify_session(session_id):
        return {
            "status": "ok",
            "session_id": session_id,
            "payment_status": "paid",
            "amount_total": 4900,
            "currency": "usd",
            "mode": "payment",
            "offer_id": "compliance-snapshot-v1",
            "livemode": True,
        }

    client, close = _client(
        tmp_path, monkeypatch, create_checkout=create_checkout,
        verify_session=verify_session)
    try:
        page = client.get("/compliance-snapshot")
        example = client.get("/compliance-snapshot/example")
        example_og = client.get(
            "/brand/compliance-snapshot-example-og.png")
        checkout = client.post(
            "/compliance-snapshot/checkout", data=VALID_ORDER,
            follow_redirects=False)
        success = client.get(
            "/compliance-snapshot/success"
            "?session_id=cs_live_snapshot")
        replay = client.get(
            "/compliance-snapshot/success"
            "?session_id=cs_live_snapshot")
        health = client.get("/healthz").json()
    finally:
        close()

    assert page.status_code == 200
    assert "$49" in page.text
    assert "30 Sep 2027" in page.text
    assert "not legal advice" in page.text
    assert "/brand/viridis-mark.svg" in page.text
    assert "/compliance-snapshot/example" in page.text
    assert '<option value="CALIFORNIA">California</option>' in page.text
    assert example.status_code == 200
    assert "India → Germany" in example.text
    assert "Pune-based steel component manufacturer" in example.text
    assert "30 September 2027" in example.text
    assert "What Viridis refuses to guess" in example.text
    assert "/brand/viridis-mark.svg" in example.text
    assert "/compliance-snapshot#order" in example.text
    assert (
        "https://taxation-customs.ec.europa.eu/"
        "carbon-border-adjustment-mechanism/"
        "cbam-communication-and-faqs_en"
    ) in example.text
    assert example_og.status_code == 200
    assert example_og.headers["content-type"] == "image/png"
    assert example_og.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert checkout.status_code == 303
    assert checkout.headers["location"].startswith(
        "https://checkout.stripe.com/")
    assert success.status_code == replay.status_code == 200
    assert "payment is verified" in success.text.lower()
    assert "already verified" in replay.text.lower()

    assert created[0][0:2] == (4900, "Viridis Compliance Snapshot")
    payload = created[0][2]
    assert payload["customer_email"] == "buyer@example.test"
    assert payload["metadata"] == {
        "offer_id": "compliance-snapshot-v1",
        "company_or_project": "Example Components",
        "jurisdiction": "EU",
        "sector": "manufacturing",
        "question": VALID_ORDER["question"],
    }
    funnel = health["subscriptions"]["frontdoor_funnel"]
    assert funnel["snapshot_page_views"] == 1
    assert funnel["snapshot_checkouts_started"] == 1
    assert funnel["snapshot_paid"] == 1


def test_snapshot_california_order_is_attributed_without_charging_in_test(
        tmp_path, monkeypatch):
    created = []

    def create_checkout(amount, product, **kwargs):
        created.append((amount, product, kwargs))
        return {
            "status": "ok",
            "url": "https://checkout.stripe.com/c/pay/cs_test_california",
            "session_id": "cs_test_california",
            "amount_cents": amount,
            "currency": "usd",
            "livemode": False,
        }

    client, close = _client(
        tmp_path, monkeypatch, create_checkout=create_checkout)
    try:
        response = client.post(
            "/compliance-snapshot/checkout",
            data={**VALID_ORDER, "jurisdiction": "CALIFORNIA"},
            follow_redirects=False)
    finally:
        close()

    assert response.status_code == 503
    assert "No charge was made" in response.text
    assert created[0][2]["metadata"]["jurisdiction"] == "CALIFORNIA"


def test_snapshot_invalid_order_and_non_live_checkout_fail_closed(
        tmp_path, monkeypatch):
    calls = []

    def create_checkout(amount, product, **kwargs):
        calls.append((amount, product, kwargs))
        return {
            "status": "ok",
            "url": "https://checkout.stripe.com/c/pay/cs_test_snapshot",
            "session_id": "cs_test_snapshot",
            "amount_cents": amount,
            "currency": "usd",
            "livemode": False,
        }

    client, close = _client(
        tmp_path, monkeypatch, create_checkout=create_checkout)
    try:
        invalid = client.post(
            "/compliance-snapshot/checkout",
            data={**VALID_ORDER, "question": "too short"},
            follow_redirects=False)
        test_mode = client.post(
            "/compliance-snapshot/checkout", data=VALID_ORDER,
            follow_redirects=False)
        health = client.get("/healthz").json()
    finally:
        close()

    assert invalid.status_code == 400
    assert len(calls) == 1
    assert test_mode.status_code == 503
    assert "No charge was made" in test_mode.text
    funnel = health["subscriptions"]["frontdoor_funnel"]
    assert funnel["snapshot_checkouts_started"] == 0
    assert funnel["snapshot_paid"] == 0


def test_snapshot_success_rejects_wrong_offer_or_amount(
        tmp_path, monkeypatch):
    def create_checkout(*_args, **_kwargs):
        raise AssertionError("checkout creation is not part of this test")

    def verify_session(session_id):
        return {
            "status": "ok",
            "session_id": session_id,
            "payment_status": "paid",
            "amount_total": 2500,
            "currency": "usd",
            "mode": "payment",
            "offer_id": "another-offer",
            "livemode": True,
        }

    client, close = _client(
        tmp_path, monkeypatch, create_checkout=create_checkout,
        verify_session=verify_session)
    try:
        response = client.get(
            "/compliance-snapshot/success"
            "?session_id=cs_live_wrong")
        health = client.get("/healthz").json()
    finally:
        close()

    assert response.status_code == 409
    assert health["subscriptions"]["frontdoor_funnel"][
        "snapshot_paid"] == 0
