"""SF1-SF7 contracts for the public seat checkout front door.

The tests use an injected subscriptions-core contract so no Stripe request,
card flow, or secret is involved.  They intentionally exercise the same
``process`` path used by the mounted core: StateStore persistence and bearer
injection are attached to that method in production.
"""

from __future__ import annotations

import html
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.testclient import TestClient

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from account_auth import AccountContextMiddleware, current_account_key  # noqa: E402
from viridis_mcp_gateway import (  # noqa: E402
    _StripeSubscriptionProvider,
    _attach_subscription_bearer,
    _build_seat_routes,
)


PUBLIC_BASE = "https://mcp.viridisconservation.com"
RAW_ACCOUNT_KEY = "vir_acct_" + "s" * 48
SECRET_SENTINEL = "sk_live_MUST_NEVER_LEAK"


def _plan(*, plan_id: str, name: str, price_minor: int,
          stripe_price_id: str | None, ready: bool) -> dict:
    return {
        "id": plan_id,
        "name": name,
        "price_minor": price_minor,
        "interval": "month",
        "covered_agents": [
            "taxcredit-engine" if plan_id == "taxcredit-seat" else "ghg-ledger"
        ],
        "included_calls_per_month": 1000,
        "overage": "per_call_rate",
        "stripe_price_id": stripe_price_id,
        "approval_status": "approved" if ready else "draft",
        "checkout_enabled": ready,
        "coverage_ready": True,
        "checkout_status": "ready" if ready else "configuration_required",
        "configuration_required": not ready,
        "coverage_note": "covered agent is mounted",
        "incumbent_anchor": "test anchor",
    }


class FakeSubscriptions:
    """Small async facsimile of the public subscriptions process contract."""

    def __init__(self):
        self.catalog = {
            "schema_version": "1.0",
            "pack_version": "0.1.0",
            "plan_catalog_sha256": "a" * 64,
            "currency": "usd",
            "configuration_notice": "Test catalog; unconfigured plans fail closed.",
            "plans": [
                _plan(
                    plan_id="taxcredit-seat", name="Tax Credit Seat",
                    price_minor=14900,
                    stripe_price_id="price_TaxCreditSeat149", ready=True,
                ),
                _plan(
                    plan_id="ghg-seat", name="GHG Seat", price_minor=9900,
                    stripe_price_id=None, ready=False,
                ),
            ],
        }
        self.actions: list[dict] = []
        self.checkout_calls = 0
        self.record_calls = 0
        self.activation_count = 0
        self.portal_calls = 0
        self.checkout_error = False
        self.checkout_url = "https://checkout.stripe.com/c/pay/cs_test_seat"
        self.portal_url = "https://billing.stripe.com/p/session/test-seat"

    @staticmethod
    def _ok(data: dict) -> dict:
        return {"status": "ok", "data": deepcopy(data), "error": None}

    @staticmethod
    def _error(error_type: str, message: str) -> dict:
        return {"status": "error", "error_type": error_type,
                "message": message}

    def _find(self, plan_id: str) -> dict | None:
        return next(
            (plan for plan in self.catalog["plans"] if plan["id"] == plan_id),
            None,
        )

    @staticmethod
    def _ready(plan: dict | None) -> bool:
        return bool(
            plan
            and plan.get("approval_status") == "approved"
            and plan.get("checkout_enabled") is True
            and plan.get("coverage_ready") is True
            and plan.get("stripe_price_id")
        )

    async def process(self, payload: dict) -> dict:
        self.actions.append(deepcopy(payload))
        action = payload.get("action")
        if action == "list_plans":
            return self._ok(self.catalog)
        if action in {"record_frontdoor_view", "record_seat_page_view"}:
            return self._ok({"recorded": True})
        if action == "frontdoor_summary":
            return self._ok({
                "page_views": 0, "checkouts_started": self.checkout_calls,
                "active_subscriptions": self.activation_count,
                "mrr_minor": 14900 if self.activation_count else 0,
                "currency": "usd", "plan_mix": {},
                "catalog": {"version": self.catalog["pack_version"],
                            "sha256": self.catalog["plan_catalog_sha256"]},
            })
        if action == "create_checkout_link":
            plan = self._find(payload.get("plan_id"))
            if not self._ready(plan):
                return self._error(
                    "configuration_required", "Stripe Price is not configured"
                )
            self.checkout_calls += 1
            if self.checkout_error:
                return self._error("VerificationError", SECRET_SENTINEL)
            return self._ok({
                "plan_id": plan["id"],
                "checkout_url": self.checkout_url,
                "mode": "subscription",
                "money_movement": "human_completed_on_stripe",
                "catalog": {
                    "version": self.catalog["pack_version"],
                    "sha256": self.catalog["plan_catalog_sha256"],
                },
            })
        if action == "record_subscription":
            self.record_calls += 1
            created = self.record_calls == 1
            if created:
                self.activation_count += 1
            data = {
                "subscription_id": "sub_TestSeat001",
                "account_id": "acct_test_buyer",
                "plan_id": "taxcredit-seat",
                "status": "active",
                "activation_created": created,
                "idempotent_replay": not created,
                "account_key_issued_once": created,
            }
            if created:
                data["account_key"] = RAW_ACCOUNT_KEY
            return self._ok(data)
        if action == "customer_portal_link":
            if (payload.get("account_id") != "acct_test_buyer"
                    or payload.get("account_key") != RAW_ACCOUNT_KEY):
                return self._error(
                    "ValidationError", "bearer account key does not own account"
                )
            self.portal_calls += 1
            return self._ok({
                "account_id": "acct_test_buyer",
                "portal_url": self.portal_url,
                "money_movement": "human_managed_on_stripe",
            })
        return self._error("ValidationError", f"unexpected action: {action}")


def _template() -> str:
    return (HERE / "seats.html").read_text()


def _client(core: FakeSubscriptions, *, pledge_percent: str = "7") -> TestClient:
    # Match production: bearer ownership proof wraps process before routes use it.
    _attach_subscription_bearer(core, current_account_key)
    routes = _build_seat_routes(
        core,
        public_base=PUBLIC_BASE,
        template_html=_template(),
        pledge_percent=pledge_percent,
    )
    return TestClient(AccountContextMiddleware(Starlette(routes=list(routes))))


def test_sf1_checkout_uses_only_core_and_redirects_to_exact_stripe_host():
    core = FakeSubscriptions()
    with _client(core) as client:
        response = client.post(
            "/seats/checkout",
            data={"plan": "taxcredit-seat", "email": "buyer@example.test"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == core.checkout_url
    target = urlparse(response.headers["location"])
    assert target.scheme == "https" and target.hostname == "checkout.stripe.com"
    assert core.checkout_calls == 1
    checkout_payload = next(
        item for item in core.actions if item.get("action") == "create_checkout_link"
    )
    assert checkout_payload == {
        "action": "create_checkout_link",
        "plan_id": "taxcredit-seat",
        "account_ref": "buyer@example.test",
        "acquisition_source": "unattributed",
    }


def test_sf1_provider_binds_checkout_and_portal_to_seat_return_routes(monkeypatch):
    import stripe_payments

    seen = {}

    def checkout(*args, **kwargs):
        seen["checkout"] = {"args": args, "kwargs": kwargs}
        return {"status": "ok",
                "url": "https://checkout.stripe.com/c/pay/cs_test_return",
                "livemode": True}

    def portal(*args, **kwargs):
        seen["portal"] = {"args": args, "kwargs": kwargs}
        return {"status": "ok",
                "url": "https://billing.stripe.com/p/session/test-return",
                "livemode": True}

    monkeypatch.setattr(stripe_payments, "create_subscription_checkout", checkout)
    monkeypatch.setattr(stripe_payments, "create_customer_portal", portal)
    provider = _StripeSubscriptionProvider(PUBLIC_BASE + "/")
    provider.create_subscription_checkout(
        price_id="price_SeatReturn", plan_id="taxcredit-seat",
        account_ref="buyer@example.test", catalog_version="0.1.0",
        catalog_sha256="a" * 64, acquisition_source="github")
    provider.create_customer_portal(customer_id="cus_TestSeat")

    assert seen["checkout"]["kwargs"]["success_url"] == (
        PUBLIC_BASE + "/seats/success?session_id={CHECKOUT_SESSION_ID}")
    assert seen["checkout"]["kwargs"]["cancel_url"] == PUBLIC_BASE + "/seats"
    assert seen["checkout"]["kwargs"]["acquisition_source"] == "github"
    assert seen["portal"]["kwargs"]["return_url"] == PUBLIC_BASE + "/seats"


def test_sf1_sf2_errors_are_friendly_nonredirects_and_never_leak_secrets(caplog):
    core = FakeSubscriptions()
    core.checkout_error = True
    with _client(core) as client:
        response = client.post(
            "/seats/checkout",
            data={"plan": "taxcredit-seat", "email": "buyer@example.test"},
            follow_redirects=False,
        )

    assert response.status_code < 300 or response.status_code >= 400
    assert "location" not in response.headers
    assert SECRET_SENTINEL not in response.text
    assert SECRET_SENTINEL not in caplog.text
    assert "traceback" not in response.text.lower()
    assert "STRIPE_API_KEY" not in response.text


def test_sf2_sf3_catalog_drives_readiness_price_coverage_and_live_mutation():
    core = FakeSubscriptions()
    with _client(core) as client:
        first = client.get("/seats")
        core.catalog["plans"][0]["price_minor"] = 12345
        core.catalog["plans"][0]["covered_agents"] = [
            "ghg-ledger", "taxcredit-engine"
        ]
        second = client.get("/seats")

    assert first.status_code == second.status_code == 200
    assert "Tax Credit Seat" in first.text
    assert "$149.00" in first.text
    assert "GHG Seat" in first.text
    assert "Coming soon" in first.text
    assert 'value="taxcredit-seat"' in first.text
    assert 'value="ghg-seat"' not in first.text
    assert "$123.45" in second.text
    assert "$149.00" not in second.text
    assert "ghg-ledger" in second.text and "taxcredit-engine" in second.text
    assert "1,000" in second.text
    assert 'method="post"' in second.text
    assert 'method="get"' not in second.text
    assert "Review and subscribe in Stripe" in second.text
    assert "Stripe shows the exact recurring total before you confirm." in second.text
    # The changed bundle must fail closed to generic copy rather than retaining
    # a plan-specific claim that no longer matches its exact covered-agent set.
    assert "Project teams testing US clean-energy credit scenarios" in first.text
    assert "supported 45Q, 45V, 45Y, 48E, and 45X scenarios" in first.text
    assert "Teams that need repeat access to the covered tools." in second.text
    assert "supported 45Q, 45V, 45Y, 48E, and 45X scenarios" not in second.text
    assert "noindex" not in first.headers.get("x-robots-tag", "").lower()
    assert "noindex" not in second.headers.get("x-robots-tag", "").lower()


def test_sf2_unconfigured_plan_never_calls_checkout_or_redirects():
    core = FakeSubscriptions()
    with _client(core) as client:
        response = client.post(
            "/seats/checkout",
            data={"plan": "ghg-seat", "email": "buyer@example.test"},
            follow_redirects=False,
        )

    assert response.status_code < 300 or response.status_code >= 400
    assert "location" not in response.headers
    assert "coming soon" in response.text.lower() or "not configured" in response.text.lower()
    assert core.checkout_calls == 0


def test_sf2_checkout_rejects_get_query_email_without_touching_core():
    core = FakeSubscriptions()
    with _client(core) as client:
        response = client.get(
            "/seats/checkout",
            params={"plan": "taxcredit-seat", "email": "buyer@example.test"},
            follow_redirects=False,
        )

    assert response.status_code == 405
    assert core.checkout_calls == 0
    assert not any(
        item.get("action") == "create_checkout_link" for item in core.actions
    )


def test_sf2_checkout_form_rejects_duplicate_extra_or_oversized_fields():
    core = FakeSubscriptions()
    cases = (
        "plan=taxcredit-seat&email=buyer%40example.test&email=other%40example.test",
        "plan=taxcredit-seat&email=buyer%40example.test&unexpected=value",
        "plan=taxcredit-seat&email=" + ("a" * 4100),
    )
    with _client(core) as client:
        responses = [
            client.post(
                "/seats/checkout",
                content=body,
                headers={"content-type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
            for body in cases
        ]

    assert all(response.status_code == 400 for response in responses)
    assert core.checkout_calls == 0
    assert not any(
        item.get("action") == "create_checkout_link" for item in core.actions
    )


def test_sf3_live_catalog_bundle_guidance_is_exact_and_compliance_first():
    core = FakeSubscriptions()
    catalog_path = (
        HERE.parents[1] / "subscriptions-agent" / "data"
        / "plan_catalog.v0.3.1.json"
    )
    core.catalog = json.loads(catalog_path.read_text())
    core.catalog["plan_catalog_sha256"] = "b" * 64
    for plan in core.catalog["plans"]:
        plan["checkout_status"] = "ready"
        plan["configuration_required"] = False

    with _client(core) as client:
        response = client.get("/seats")

    assert response.status_code == 200
    names = (
        "Compliance Seat", "Energy Seat", "Climate Seat",
        "Tax Credit Seat", "GHG Seat",
    )
    positions = [response.text.index(f"<h2>{name}</h2>") for name in names]
    assert positions == sorted(positions)
    for expected in (
        "Screen current jurisdiction-and-sector applicability",
        "Clean-energy teams comparing incentive and emissions scenarios",
        "Teams turning activity data into emissions inventories",
        "supported 45Q, 45V, 45Y, 48E, and 45X scenarios",
        "content-addressed audit hash",
    ):
        assert expected in response.text
    assert response.text.count('action="/seats/checkout" method="post"') == 5


def test_sf3_catalog_text_is_html_escaped():
    core = FakeSubscriptions()
    core.catalog["plans"][0]["name"] = '<script id="catalog-injection">bad()</script>'
    with _client(core) as client:
        response = client.get("/seats")

    assert response.status_code == 200
    assert '<script id="catalog-injection">' not in response.text
    assert html.escape(core.catalog["plans"][0]["name"]) in response.text


def test_sf4_sf5_success_issues_key_once_replay_is_idempotent_and_no_store():
    core = FakeSubscriptions()
    with _client(core) as client:
        first = client.get("/seats/success?session_id=cs_test_Seat001")
        replay = client.get("/seats/success?session_id=cs_test_Seat001")

    assert first.status_code == replay.status_code == 200
    assert first.text.count(RAW_ACCOUNT_KEY) == 1
    assert RAW_ACCOUNT_KEY not in replay.text
    assert core.record_calls == 2
    assert core.activation_count == 1
    assert "no-store" in first.headers.get("cache-control", "").lower()
    assert "no-store" in replay.headers.get("cache-control", "").lower()
    assert "noindex" in first.headers.get("x-robots-tag", "").lower()
    assert "noindex" in replay.headers.get("x-robots-tag", "").lower()
    assert first.headers.get("referrer-policy", "").lower() == "no-referrer"
    assert RAW_ACCOUNT_KEY not in "\n".join(
        f"{key}: {value}" for key, value in first.headers.items()
    )
    # The key may appear only as copyable body text, never inside a URL.
    assert not re.search(r'href=["\'][^"\']*' + re.escape(RAW_ACCOUNT_KEY), first.text)


def test_sf4_manage_requires_bearer_and_redirects_only_to_exact_portal_host():
    core = FakeSubscriptions()
    with _client(core) as client:
        anonymous = client.get(
            "/seats/manage?account=acct_test_buyer", follow_redirects=False
        )
        authorized = client.get(
            "/seats/manage?account=acct_test_buyer",
            headers={"Authorization": f"Bearer {RAW_ACCOUNT_KEY}"},
            follow_redirects=False,
        )
        # A key in the query string is never accepted as ownership proof.
        query_key = client.get(
            f"/seats/manage?account=acct_test_buyer&account_key={RAW_ACCOUNT_KEY}",
            follow_redirects=False,
        )

    assert anonymous.status_code < 300 or anonymous.status_code >= 400
    assert query_key.status_code < 300 or query_key.status_code >= 400
    assert "location" not in anonymous.headers
    assert "location" not in query_key.headers
    assert authorized.status_code == 302
    target = urlparse(authorized.headers["location"])
    assert target.scheme == "https" and target.hostname == "billing.stripe.com"
    assert core.portal_calls == 1


def test_sf6_plain_page_is_deterministic_and_invokes_no_stripe_action():
    core = FakeSubscriptions()
    with _client(core) as client:
        first = client.get("/seats")
        second = client.get("/seats")

    assert first.status_code == second.status_code == 200
    assert first.text == second.text
    assert core.checkout_calls == core.record_calls == core.portal_calls == 0
    assert SECRET_SENTINEL not in first.text


def test_sf6_seat_source_attribution_is_finite_and_discards_raw_context():
    core = FakeSubscriptions()
    with _client(core) as client:
        tagged = client.get(
            "/seats?source=meshmcp",
            headers={"referer": "https://attacker.example/private?id=1"},
        )
        paid_success = client.get(
            "/seats?source=x402-success",
            headers={"referer": "https://attacker.example/private?id=2"},
        )
        fallback = client.get(
            "/seats?source=https://discord.com/channels/private",
            headers={"referer": "https://github.com/example/private?buyer=1"},
        )

    assert tagged.status_code == paid_success.status_code == \
        fallback.status_code == 200
    view_actions = [
        item for item in core.actions
        if item.get("action") == "record_frontdoor_view"
    ]
    assert view_actions == [
        {"action": "record_frontdoor_view", "source": "meshmcp"},
        {"action": "record_frontdoor_view", "source": "x402_success"},
        {"action": "record_frontdoor_view", "source": "github"},
    ]
    encoded = json.dumps(view_actions, sort_keys=True)
    assert "attacker.example" not in encoded
    assert "discord.com" not in encoded
    assert "buyer=1" not in encoded


def test_sf6_source_continues_from_page_to_checkout_without_raw_context():
    core = FakeSubscriptions()
    with _client(core) as client:
        page = client.get(
            "/seats?source=meshmcp",
            headers={"referer": "https://attacker.example/private?id=1"},
        )
        checkout = client.post(
            "/seats/checkout",
            data={
                "plan": "taxcredit-seat",
                "email": "buyer@example.test",
                "source": "meshmcp",
            },
            follow_redirects=False,
        )
    assert page.status_code == 200
    assert 'name="source" value="meshmcp"' in page.text
    assert checkout.status_code == 302
    action = next(
        item for item in core.actions
        if item.get("action") == "create_checkout_link"
    )
    assert action["acquisition_source"] == "meshmcp"
    encoded = json.dumps(action, sort_keys=True)
    assert "attacker.example" not in encoded
    assert "private?id=1" not in encoded


def test_sf6_arbitrary_checkout_source_fails_before_core_or_stripe():
    core = FakeSubscriptions()
    with _client(core) as client:
        response = client.post(
            "/seats/checkout",
            data={
                "plan": "taxcredit-seat",
                "email": "buyer@example.test",
                "source": "https://private.example/buyer/42",
            },
            follow_redirects=False,
        )
    assert response.status_code == 400
    assert core.checkout_calls == 0
    assert not any(
        item.get("action") == "create_checkout_link"
        for item in core.actions
    )


def test_sf7_conservation_percentage_is_config_driven_and_explicitly_pledged():
    core_a = FakeSubscriptions()
    core_b = FakeSubscriptions()
    with _client(core_a, pledge_percent="7") as client:
        seven = client.get("/seats")
    with _client(core_b, pledge_percent="12.5") as client:
        twelve = client.get("/seats")

    assert "7%" in seven.text
    assert "12.5%" in twelve.text
    assert "7%" not in twelve.text
    assert "pledged" in seven.text.lower() and "pledged" in twelve.text.lower()
    for body in (seven.text.lower(), twelve.text.lower()):
        assert "already retired" not in body
        assert "has been retired" not in body
        assert "retirement complete" not in body


def test_sf7_zero_pledge_is_not_advertised_as_a_pledge():
    core = FakeSubscriptions()
    with _client(core, pledge_percent="0") as client:
        response = client.get("/seats")

    body = response.text.lower()
    assert response.status_code == 200
    assert "0% of your subscription funds are pledged" not in body
    assert "conservation allocation is not active yet" in body
    assert "future pledge" in body
    assert "verified retirement evidence" in body
    assert "already retired" not in body
    assert "retirement complete" not in body
