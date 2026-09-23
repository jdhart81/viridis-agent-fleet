"""One test per invariant P1–P7 for stripe_payments.create_checkout. No network."""
import stripe_payments as sp


def _fake_ok(url, data, headers):
    # capture the request for assertions; return a Stripe-shaped success
    _fake_ok.calls.append((url, data.decode(), headers))
    return {"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/cs_test_123",
            "livemode": False}
_fake_ok.calls = []


def test_p1_amount_must_be_positive_int():
    for bad in (0, -5, 3.5, "10", True):
        r = sp.create_checkout(bad, "SmartScale measurement", api_key="sk_test_x")
        assert r["status"] == "error" and r["error_type"] == "bad_amount", bad


def test_p2_currency_three_letter():
    r = sp.create_checkout(500, "x", currency="dollars", api_key="sk_test_x")
    assert r["status"] == "error" and r["error_type"] == "bad_currency"


def test_p3_no_api_key_errors_not_crash(monkeypatch):
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    r = sp.create_checkout(500, "x")  # no key anywhere
    assert r["status"] == "error" and r["error_type"] == "no_api_key"


def test_p4_builds_checkout_session_post():
    from urllib.parse import parse_qs
    _fake_ok.calls.clear()
    sp.create_checkout(1299, "SmartScale measurement", currency="usd",
                       api_key="sk_test_x", _transport=_fake_ok)
    url, body, headers = _fake_ok.calls[-1]
    q = parse_qs(body)
    assert url.endswith("/v1/checkout/sessions")
    assert q["mode"] == ["payment"]
    assert q["line_items[0][price_data][unit_amount]"] == ["1299"]
    assert q["line_items[0][price_data][currency]"] == ["usd"]
    assert q["line_items[0][price_data][product_data][name]"] == ["SmartScale measurement"]
    assert q["integration_identifier"] == [sp.ONE_TIME_INTEGRATION_ID]
    assert headers["Authorization"] == "Bearer sk_test_x"


def test_one_time_checkout_collects_valid_customer_email():
    from urllib.parse import parse_qs
    _fake_ok.calls.clear()
    result = sp.create_checkout(
        4900, "Viridis Compliance Snapshot",
        customer_email="buyer@example.test",
        api_key="sk_test_x", _transport=_fake_ok)
    assert result["status"] == "ok"
    form = parse_qs(_fake_ok.calls[-1][1])
    assert form["customer_email"] == ["buyer@example.test"]

    bad = sp.create_checkout(
        4900, "Viridis Compliance Snapshot",
        customer_email="not-an-email", api_key="sk_test_x")
    assert bad["status"] == "error"
    assert bad["error_type"] == "bad_email"


def test_p5_success_shape():
    r = sp.create_checkout(1299, "SmartScale measurement",
                           api_key="sk_test_x", _transport=_fake_ok)
    assert r["status"] == "ok"
    assert r["url"].startswith("https://checkout.stripe.com/")
    assert r["session_id"] == "cs_test_123"
    assert r["amount_cents"] == 1299 and r["currency"] == "usd"


def test_p6_key_never_leaks_on_error():
    def boom(url, data, headers):
        raise RuntimeError("boom with sk_test_SECRETKEY in message")
    r = sp.create_checkout(500, "x", api_key="sk_test_SECRETKEY", _transport=boom)
    assert r["status"] == "error"
    assert "sk_test_SECRETKEY" not in __import__("json").dumps(r)


def test_p7_livemode_flag_from_key_prefix():
    def response_without_mode(url, data, headers):
        return {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/x"}

    for key, expected in (("sk_live_x", True), ("rk_live_x", True),
                          ("sk_test_x", False), ("rk_test_x", False)):
        r = sp.create_checkout(500, "x", api_key=key,
                               _transport=response_without_mode)
        assert r["livemode"] is expected, key


def test_verify_session_exposes_only_allowlisted_offer_metadata():
    result = sp.verify_session(
        "cs_live_ABC123", api_key="rk_live_x",
        _transport=lambda *_: {
            "id": "cs_live_ABC123",
            "payment_status": "paid",
            "amount_total": 4900,
            "currency": "usd",
            "mode": "payment",
            "status": "expired",
            "created": 1785000000,
            "expires_at": 1785086400,
            "metadata": {
                "offer_id": "compliance-snapshot-v1",
                "company_or_project": "Private Buyer",
                "question": "Private question",
            },
            "livemode": True,
        })
    assert result["offer_id"] == "compliance-snapshot-v1"
    assert result["mode"] == "payment"
    assert result["checkout_status"] == "expired"
    assert result["created"] == 1785000000
    assert result["expires_at"] == 1785086400
    assert "company_or_project" not in result
    assert "Private Buyer" not in __import__("json").dumps(result)


def test_subscription_checkout_is_hosted_recurring_and_reference_attributed():
    from urllib.parse import parse_qs
    calls = []

    def transport(url, data, headers):
        calls.append((url, parse_qs(data.decode()), headers))
        return {"id": "cs_test_SUB123", "url":
                "https://checkout.stripe.com/c/pay/cs_test_SUB123", "livemode": False}

    r = sp.create_subscription_checkout(
        "price_ABC123", "ghg-seat", "buyer-42", catalog_version="0.1.0",
        catalog_sha256="a" * 64,
        acquisition_source="github",
        api_key="sk_test_secret", _transport=transport)
    assert r["status"] == "ok" and r["session_id"] == "cs_test_SUB123"
    url, form, headers = calls[0]
    assert url == sp.STRIPE_API
    assert form["mode"] == ["subscription"]
    assert form["line_items[0][price]"] == ["price_ABC123"]
    assert form["client_reference_id"] == ["buyer-42"]
    assert form["metadata[plan_id]"] == ["ghg-seat"]
    assert form["metadata[catalog_version]"] == ["0.1.0"]
    assert form["subscription_data[metadata][account_ref]"] == ["buyer-42"]
    assert form["subscription_data[metadata][catalog_sha256]"] == ["a" * 64]
    assert form["metadata[acquisition_source]"] == ["github"]
    assert form["subscription_data[metadata][acquisition_source]"] == [
        "github"]
    assert form["integration_identifier"] == [
        sp.SUBSCRIPTION_INTEGRATION_ID]
    assert headers["Authorization"] == "Bearer sk_test_secret"


def test_subscription_checkout_fails_closed_until_price_configured(monkeypatch):
    monkeypatch.setenv("STRIPE_API_KEY", "sk_live_will_not_be_used")
    r = sp.create_subscription_checkout(
        "", "ghg-seat", "buyer", catalog_version="0.1.0",
        catalog_sha256="a" * 64)
    assert r["status"] == "error" and r["error_type"] == "price_not_configured"


def test_customer_portal_is_stripe_hosted():
    from urllib.parse import parse_qs
    calls = []

    def transport(url, data, headers):
        calls.append((url, parse_qs(data.decode()), headers))
        return {"id": "bps_test_1", "url":
                "https://billing.stripe.com/p/session/test", "livemode": False}

    r = sp.create_customer_portal("cus_ABC123", api_key="sk_test_x",
                                  _transport=transport)
    assert r["status"] == "ok"
    assert calls[0][0] == sp.STRIPE_PORTAL_API
    assert calls[0][1]["customer"] == ["cus_ABC123"]


def _subscription_object():
    return {
        "id": "sub_ABC123", "status": "active", "customer": "cus_ABC123",
        "current_period_start": 1_800_000_000,
        "current_period_end": 1_802_678_400,
        "metadata": {"plan_id": "ghg-seat", "account_ref": "buyer-42",
                     "catalog_version": "0.1.0",
                     "catalog_sha256": "a" * 64,
                     "acquisition_source": "github"},
        "livemode": False,
        "items": {"data": [{"quantity": 1, "price": {
            "id": "price_ABC123", "unit_amount": 9900, "currency": "usd",
            "active": True, "recurring": {"interval": "month", "interval_count": 1}
        }}]},
    }


def test_verify_subscription_checkout_normalizes_recurring_fields():
    calls = []

    def transport(url, headers):
        calls.append((url, headers))
        return {"id": "cs_test_ABC123", "mode": "subscription", "status": "complete",
                "payment_status": "paid",
                "client_reference_id": "buyer-42", "customer": "cus_ABC123",
                "metadata": {"plan_id": "ghg-seat"},
                "subscription": _subscription_object(), "livemode": False}

    r = sp.verify_subscription("cs_test_ABC123", api_key="sk_test_x",
                               _transport=transport)
    assert r["status"] == "ok"
    assert r["verified"] is True and r["mode"] == "subscription"
    assert r["subscription_id"] == "sub_ABC123"
    assert r["account_ref"] == "buyer-42"
    assert r["customer_id"] == "cus_ABC123"
    assert r["plan_id"] == "ghg-seat"
    assert r["price_id"] == "price_ABC123"
    assert r["line_item_count"] == 1 and r["quantity"] == 1
    assert r["catalog_version"] == "0.1.0"
    assert r["acquisition_source"] == "github"
    assert r["current_period_end"] == 1_802_678_400
    assert calls[0][0].startswith(sp.STRIPE_API + "/cs_test_ABC123")


def test_verify_subscription_id_and_checkout_indirection():
    calls = []

    def transport(url, headers):
        calls.append(url)
        if "/checkout/sessions/" in url:
            return {"id": "cs_test_DEF456", "mode": "subscription", "status": "complete",
                    "payment_status": "paid",
                    "client_reference_id": "buyer-2", "subscription": "sub_ABC123"}
        return _subscription_object()

    via_session = sp.verify_subscription("cs_test_DEF456", api_key="sk_test_x",
                                         _transport=transport)
    direct = sp.verify_subscription("sub_ABC123", api_key="sk_test_x",
                                    _transport=transport)
    assert via_session["status"] == direct["status"] == "ok"
    assert via_session["subscription_id"] == direct["subscription_id"] == "sub_ABC123"
    assert any("/subscriptions/sub_ABC123" in url for url in calls)


def test_verify_rejects_one_time_checkout_and_scrubs_secret():
    one_time = sp.verify_subscription(
        "cs_test_PAYMENT", api_key="sk_test_SECRET",
        _transport=lambda *_: {"id": "cs_test_PAYMENT", "mode": "payment"})
    assert one_time["error_type"] == "not_subscription_checkout"

    def boom(*_):
        raise RuntimeError("upstream echoed sk_test_SECRET")

    failed = sp.verify_subscription("sub_ABC123", api_key="sk_test_SECRET",
                                    _transport=boom)
    assert failed["error_type"] == "stripe_error"
    assert "sk_test_SECRET" not in __import__("json").dumps(failed)
