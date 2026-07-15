"""
stripe_payments.py — minimal, stdlib-only Stripe payment primitive for the Viridis
fleet's human-facing revenue agents (SmartScale, protogen, regulatory-radar).

WHY THIS SHAPE
- Agent-to-agent settlement uses x402 (metering + escrow agents). This module is
  the *human* rail: an agent hands a caller a Stripe Checkout URL to pay for a
  service (e.g. a SmartScale measurement, a protogen CAD job).
- stdlib only (urllib) so it drops into any agent core with no new dependency.
- The secret key is read from the STRIPE_API_KEY env var and is NEVER accepted as
  a tool argument, logged, echoed, or returned. Claude never handles the live key;
  Justin sets it on the host.

INVARIANTS (one test each; never raises on bad input — returns an error envelope):
  P1  amount_cents is a positive integer (> 0).
  P2  currency is a 3-letter ISO code (defaults "usd").
  P3  if no API key is configured, returns {status:"error", error_type:"no_api_key"}
      — never a crash, never a partial charge.
  P4  the Stripe request is a POST to /v1/checkout/sessions, form-encoded, with
      mode=payment and an inline price_data line item (mockable via `_transport`).
  P5  on success returns {status:"ok", url, session_id, amount_cents, currency}.
  P6  the returned/logged payload never contains the API key.
  P7  test-mode vs live-mode is derived from the key prefix (sk_test_/sk_live_) and
      surfaced as `livemode`, so an agent can refuse real charges until intended.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

STRIPE_API = "https://api.stripe.com/v1/checkout/sessions"
STRIPE_SUBSCRIPTIONS_API = "https://api.stripe.com/v1/subscriptions"
STRIPE_PORTAL_API = "https://api.stripe.com/v1/billing_portal/sessions"
STRIPE_VERSION = "2026-02-25.clover"

_CHECKOUT_ID_RE = re.compile(r"^cs_(?:test_|live_)?[A-Za-z0-9]+$")
_SUBSCRIPTION_ID_RE = re.compile(r"^sub_[A-Za-z0-9]+$")
_CUSTOMER_ID_RE = re.compile(r"^cus_[A-Za-z0-9]+$")
_PRICE_ID_RE = re.compile(r"^price_[A-Za-z0-9]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _err(error_type: str, message: str, **extra) -> dict:
    return {"status": "error", "error_type": error_type, "message": message,
            "timestamp": _now(), **extra}


def _scrub(message: object, key: str) -> str:
    """Never let a configured Stripe credential escape an error envelope."""
    return str(message).replace(key, "***")[:500]


def _default_transport(url: str, data: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec - fixed Stripe host
        return json.loads(resp.read().decode())


def _default_get_transport(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec - fixed Stripe host
        return json.loads(resp.read().decode())


def verify_session(session_id: str, *, api_key: str | None = None,
                   _transport=_default_get_transport) -> dict:
    """Retrieve a Checkout Session and report its payment status (PG10 rail).

    Returns {status:"ok", session_id, payment_status, amount_total, currency,
    livemode} or a structured error envelope. Never echoes the key.
    """
    if not isinstance(session_id, str) or not _CHECKOUT_ID_RE.fullmatch(session_id.strip()):
        return _err("bad_session", "session_id must be a Stripe checkout session id (cs_...)",
                    field="session_id")
    key = api_key or os.environ.get("STRIPE_API_KEY")
    if not key:
        return _err("no_api_key",
                    "STRIPE_API_KEY not configured on the host; set it to enable verification")
    try:
        resp = _transport(f"{STRIPE_API}/{session_id.strip()}",
                          {"Authorization": f"Bearer {key}",
                           "Stripe-Version": STRIPE_VERSION})
    except Exception as e:
        msg = _scrub(e, key)
        return _err("stripe_error", msg)
    return {
        "status": "ok",
        "session_id": resp.get("id"),
        "payment_status": resp.get("payment_status"),
        "amount_total": resp.get("amount_total"),
        "currency": resp.get("currency"),
        "livemode": bool(resp.get("livemode")),
        "timestamp": _now(),
    }


def list_checkout_sessions(*, created_after_epoch: int | None = None,
                           limit: int = 100, api_key: str | None = None,
                           _transport=_default_get_transport) -> dict:
    """List recent Checkout Sessions for revenue reconciliation (read-only).

    Returns {status:"ok", sessions:[{session_id, payment_status, amount_total,
    currency, created, livemode, mode}], has_more} or a structured error
    envelope. Never echoes the key; never mutates anything on Stripe.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        return _err("bad_limit", "limit must be an int in [1, 100]", field="limit")
    key = api_key or os.environ.get("STRIPE_API_KEY")
    if not key:
        return _err("no_api_key",
                    "STRIPE_API_KEY not configured on the host; set it to enable reconciliation")
    url = f"{STRIPE_API}?limit={limit}"
    if created_after_epoch is not None:
        if not isinstance(created_after_epoch, int) or created_after_epoch < 0:
            return _err("bad_created_after", "created_after_epoch must be a unix timestamp",
                        field="created_after_epoch")
        url += f"&created[gte]={created_after_epoch}"
    try:
        resp = _transport(url, {"Authorization": f"Bearer {key}",
                                "Stripe-Version": STRIPE_VERSION})
    except Exception as e:
        return _err("stripe_error", _scrub(e, key))
    sessions = [{
        "session_id": s.get("id"),
        "payment_status": s.get("payment_status"),
        "amount_total": s.get("amount_total"),
        "currency": s.get("currency"),
        "created": s.get("created"),
        "livemode": bool(s.get("livemode")),
        "mode": s.get("mode"),
    } for s in resp.get("data", []) if isinstance(s, dict)]
    return {"status": "ok", "sessions": sessions,
            "has_more": bool(resp.get("has_more")), "timestamp": _now()}


def create_checkout(
    amount_cents,
    product_name: str,
    *,
    currency: str = "usd",
    success_url: str = "https://mcp.viridisconservation.com/pay/success",
    cancel_url: str = "https://mcp.viridisconservation.com/pay/cancel",
    metadata: dict | None = None,
    api_key: str | None = None,
    _transport=_default_transport,
) -> dict:
    """Create a Stripe Checkout Session and return its payment URL.

    api_key defaults to os.environ["STRIPE_API_KEY"]; pass explicitly only in tests.
    """
    # P1
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
        return _err("bad_amount", "amount_cents must be a positive integer",
                    field="amount_cents", value=amount_cents)
    # P2
    if not (isinstance(currency, str) and len(currency) == 3 and currency.isalpha()):
        return _err("bad_currency", "currency must be a 3-letter ISO code",
                    field="currency", value=currency)
    if not (isinstance(product_name, str) and product_name.strip()):
        return _err("bad_product", "product_name is required", field="product_name")

    key = api_key or os.environ.get("STRIPE_API_KEY")
    # P3
    if not key:
        return _err("no_api_key",
                    "STRIPE_API_KEY not configured on the host; set it to enable charging")

    # P4 — build the form-encoded Checkout Session request
    form = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": currency.lower(),
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][product_data][name]": product_name.strip(),
    }
    for k, v in (metadata or {}).items():
        form[f"metadata[{k}]"] = str(v)

    data = urllib.parse.urlencode(form).encode()
    headers = {"Authorization": f"Bearer {key}",
               "Stripe-Version": STRIPE_VERSION,
               "Content-Type": "application/x-www-form-urlencoded"}

    try:
        resp = _transport(STRIPE_API, data, headers)
    except Exception as e:  # network / Stripe error — never crash the agent
        # P6: never echo the key; scrub anything that looks like it
        msg = _scrub(e, key)
        return _err("stripe_error", msg)

    url = resp.get("url")
    if not url:
        return _err("stripe_error", "Stripe response missing checkout url",
                    stripe_id=resp.get("id"))

    # P5 / P7
    return {
        "status": "ok",
        "url": url,
        "session_id": resp.get("id"),
        "amount_cents": amount_cents,
        "currency": currency.lower(),
        "livemode": bool(resp.get("livemode", key.startswith("sk_live_"))),
        "timestamp": _now(),
    }


def create_subscription_checkout(
    price_id: str,
    plan_id: str,
    account_ref: str,
    *,
    catalog_version: str,
    catalog_sha256: str,
    success_url: str = "https://mcp.viridisconservation.com/pay/success?session_id={CHECKOUT_SESSION_ID}",
    cancel_url: str = "https://mcp.viridisconservation.com/pay/cancel",
    api_key: str | None = None,
    _transport=_default_transport,
) -> dict:
    """Prepare a Stripe-hosted recurring Checkout Session.

    This function only creates a hosted URL.  It never accepts card details and
    never confirms or captures a payment.  ``price_id`` must be a recurring
    Stripe Price created by the account owner outside this agent.
    """
    if not isinstance(price_id, str) or not _PRICE_ID_RE.fullmatch(price_id):
        return _err("price_not_configured",
                    "plan does not have a configured recurring Stripe price_id",
                    field="price_id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        return _err("bad_plan", "plan_id is required", field="plan_id")
    if (not isinstance(catalog_version, str) or not catalog_version.strip()
            or len(catalog_version.strip()) > 32):
        return _err("bad_catalog_version", "catalog_version is required",
                    field="catalog_version")
    if (not isinstance(account_ref, str) or not account_ref.strip()
            or len(account_ref.strip()) > 200):
        return _err("bad_account_ref", "account_ref is required (max 200 characters)",
                    field="account_ref")
    if not isinstance(catalog_sha256, str) or not _SHA256_RE.fullmatch(catalog_sha256):
        return _err("bad_catalog_sha", "catalog_sha256 must be a lowercase SHA-256",
                    field="catalog_sha256")
    key = api_key or os.environ.get("STRIPE_API_KEY")
    if not key:
        return _err("no_api_key",
                    "STRIPE_API_KEY not configured on the host; set it to enable Checkout")

    form = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "client_reference_id": account_ref.strip(),
        "metadata[plan_id]": plan_id.strip(),
        "metadata[catalog_version]": catalog_version.strip(),
        "metadata[catalog_sha256]": catalog_sha256,
        "subscription_data[metadata][plan_id]": plan_id.strip(),
        "subscription_data[metadata][account_ref]": account_ref.strip(),
        "subscription_data[metadata][catalog_version]": catalog_version.strip(),
        "subscription_data[metadata][catalog_sha256]": catalog_sha256,
    }
    data = urllib.parse.urlencode(form).encode()
    headers = {"Authorization": f"Bearer {key}",
               "Stripe-Version": STRIPE_VERSION,
               "Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = _transport(STRIPE_API, data, headers)
    except Exception as e:
        return _err("stripe_error", _scrub(e, key))
    url = resp.get("url")
    if not isinstance(url, str) or not url.startswith("https://checkout.stripe.com/"):
        return _err("stripe_error", "Stripe response missing hosted Checkout URL",
                    stripe_id=resp.get("id"))
    return {"status": "ok", "url": url, "session_id": resp.get("id"),
            "plan_id": plan_id.strip(),
            "catalog_version": catalog_version.strip(),
            "catalog_sha256": catalog_sha256,
            "livemode": bool(resp.get("livemode", key.startswith("sk_live_"))),
            "timestamp": _now()}


def create_customer_portal(
    customer_id: str,
    *,
    return_url: str = "https://mcp.viridisconservation.com/deck",
    api_key: str | None = None,
    _transport=_default_transport,
) -> dict:
    """Create a Stripe-hosted billing-portal URL for an existing customer."""
    if not isinstance(customer_id, str) or not _CUSTOMER_ID_RE.fullmatch(customer_id):
        return _err("bad_customer", "customer_id must be a Stripe customer id (cus_...)",
                    field="customer_id")
    key = api_key or os.environ.get("STRIPE_API_KEY")
    if not key:
        return _err("no_api_key",
                    "STRIPE_API_KEY not configured on the host; set it to enable Portal")
    data = urllib.parse.urlencode({"customer": customer_id,
                                  "return_url": return_url}).encode()
    headers = {"Authorization": f"Bearer {key}",
               "Stripe-Version": STRIPE_VERSION,
               "Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = _transport(STRIPE_PORTAL_API, data, headers)
    except Exception as e:
        return _err("stripe_error", _scrub(e, key))
    url = resp.get("url")
    if not isinstance(url, str) or not url.startswith("https://billing.stripe.com/"):
        return _err("stripe_error", "Stripe response missing hosted portal URL",
                    stripe_id=resp.get("id"))
    return {"status": "ok", "url": url, "portal_session_id": resp.get("id"),
            "livemode": bool(resp.get("livemode", key.startswith("sk_live_"))),
            "timestamp": _now()}


def _stripe_id(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("id"), str):
        return value["id"]
    return None


def _subscription_period(subscription: dict) -> tuple[object, object]:
    start = subscription.get("current_period_start")
    end = subscription.get("current_period_end")
    if start is not None and end is not None:
        return start, end
    items = ((subscription.get("items") or {}).get("data") or [])
    if items and isinstance(items[0], dict):
        return items[0].get("current_period_start"), items[0].get("current_period_end")
    return None, None


def _subscription_price_items(subscription: dict) -> list[dict]:
    items = ((subscription.get("items") or {}).get("data") or [])
    found = []
    for item in items:
        if not isinstance(item, dict):
            continue
        price = item.get("price")
        price_id = _stripe_id(price)
        if price_id:
            price_obj = price if isinstance(price, dict) else {}
            recurring = price_obj.get("recurring") \
                if isinstance(price_obj.get("recurring"), dict) else {}
            found.append({
                "price_id": price_id,
                "quantity": item.get("quantity"),
                "unit_amount": price_obj.get("unit_amount"),
                "currency": price_obj.get("currency"),
                "interval": recurring.get("interval"),
                "interval_count": recurring.get("interval_count", 1),
                "active": price_obj.get("active"),
            })
    return found


def verify_subscription(
    stripe_session_or_sub_id: str,
    *,
    api_key: str | None = None,
    _transport=_default_get_transport,
) -> dict:
    """Pull-verify a recurring Checkout Session or Subscription.

    Returns only the normalized fields needed by the deterministic subscription
    ledger.  A session must be ``mode=subscription``.  When Stripe returns only
    a subscription ID, the subscription is retrieved in a second fixed-host GET.
    """
    value = stripe_session_or_sub_id.strip() \
        if isinstance(stripe_session_or_sub_id, str) else ""
    is_checkout = bool(_CHECKOUT_ID_RE.fullmatch(value))
    is_subscription = bool(_SUBSCRIPTION_ID_RE.fullmatch(value))
    if not (is_checkout or is_subscription):
        return _err("bad_subscription_ref",
                    "reference must be a Stripe Checkout Session (cs_...) or subscription (sub_...)",
                    field="stripe_session_or_sub_id")
    key = api_key or os.environ.get("STRIPE_API_KEY")
    if not key:
        return _err("no_api_key",
                    "STRIPE_API_KEY not configured on the host; set it to enable verification")
    headers = {"Authorization": f"Bearer {key}",
               "Stripe-Version": STRIPE_VERSION}
    session = None
    try:
        if is_checkout:
            session = _transport(
                f"{STRIPE_API}/{value}?expand[]=subscription&expand[]=line_items",
                headers)
            if session.get("mode") != "subscription":
                return _err("not_subscription_checkout",
                            "Checkout Session mode is not subscription",
                            session_id=session.get("id"))
            if session.get("status") != "complete":
                return _err("incomplete_checkout",
                            "Checkout Session is not complete",
                            session_id=session.get("id"))
            if session.get("payment_status") != "paid":
                return _err("unpaid_checkout",
                            "Checkout Session payment_status is not paid",
                            session_id=session.get("id"))
            subscription = session.get("subscription")
            if isinstance(subscription, str):
                subscription = _transport(
                    f"{STRIPE_SUBSCRIPTIONS_API}/{subscription}?expand[]=items.data.price",
                    headers)
        else:
            subscription = _transport(
                f"{STRIPE_SUBSCRIPTIONS_API}/{value}?expand[]=items.data.price",
                headers)
    except Exception as e:
        return _err("stripe_error", _scrub(e, key))
    if not isinstance(subscription, dict):
        return _err("stripe_error", "Stripe response missing subscription object")

    period_start, period_end = _subscription_period(subscription)
    metadata = {}
    if isinstance(subscription.get("metadata"), dict):
        metadata.update(subscription["metadata"])
    if isinstance(session, dict) and isinstance(session.get("metadata"), dict):
        metadata.update(session["metadata"])
    account_ref = (session or {}).get("client_reference_id") if session else None
    if not account_ref:
        account_ref = metadata.get("account_ref")
    customer_id = _stripe_id(subscription.get("customer"))
    if not customer_id and session:
        customer_id = _stripe_id(session.get("customer"))

    subscription_id = _stripe_id(subscription)
    price_items = _subscription_price_items(subscription)
    if not subscription_id or not _SUBSCRIPTION_ID_RE.fullmatch(subscription_id):
        return _err("stripe_error", "Stripe response missing subscription id")
    if not customer_id or not _CUSTOMER_ID_RE.fullmatch(customer_id):
        return _err("stripe_error", "Stripe response missing customer id")
    if not isinstance(account_ref, str) or not account_ref.strip():
        return _err("stripe_error", "Stripe subscription is missing account_ref metadata")
    if not isinstance(period_start, int) or isinstance(period_start, bool) \
            or not isinstance(period_end, int) or isinstance(period_end, bool) \
            or period_start >= period_end:
        return _err("bad_subscription_period",
                    "Stripe subscription period is missing or invalid")
    if len(price_items) != 1:
        return _err("ambiguous_subscription_items",
                    "subscription must contain exactly one recurring Price",
                    item_count=len(price_items))
    price_item = price_items[0]
    if not _PRICE_ID_RE.fullmatch(str(price_item.get("price_id", ""))):
        return _err("bad_price_id", "subscription contains an invalid Price id")
    if price_item.get("quantity") != 1:
        return _err("bad_subscription_quantity",
                    "subscription Price quantity must be exactly 1")

    return {
        "status": "ok",
        "verified": True,
        "mode": "subscription",
        "session_id": (session or {}).get("id") if session else None,
        "subscription_id": subscription_id,
        "customer_id": customer_id,
        "subscription_status": subscription.get("status"),
        "current_period_start": period_start,
        "current_period_end": period_end,
        "price_id": price_item["price_id"],
        "quantity": price_item["quantity"],
        "unit_amount": price_item["unit_amount"],
        "currency": price_item["currency"],
        "interval": price_item["interval"],
        "interval_count": price_item["interval_count"],
        "price_active": price_item["active"],
        "price_items": price_items,
        "line_item_count": len(price_items),
        "plan_id": metadata.get("plan_id"),
        "catalog_version": metadata.get("catalog_version"),
        "catalog_sha256": metadata.get("catalog_sha256"),
        "account_ref": account_ref,
        "checkout_status": (session or {}).get("status") if session else None,
        "checkout_payment_status": (session or {}).get("payment_status") if session else None,
        "livemode": bool(subscription.get(
            "livemode", (session or {}).get("livemode", key.startswith("sk_live_")))),
        "timestamp": _now(),
    }
