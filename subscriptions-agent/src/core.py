"""Deterministic B2B seat/subscription entitlement engine.

This core owns account attribution, the versioned plan catalog, verified
subscription lifecycle, exact quota accounting, and fail-safe entitlement
decisions.  It does not charge cards and never handles a Stripe secret.

ST1  Account/subscription/usage state is plain picklable instance state so the
     fleet StateStore can persist it durable-before-ack.
ST2  Any verification error or entitlement ambiguity returns the existing
     per-call fallback; an error can never grant free access.
ST3  A request id takes exactly one recorded path: included-quota waiver or
     direct overage metering.  Replays do not consume twice.
ST4  Lifecycle is active|past_due|canceled|expired.  Entitlement requires
     active and now in the half-open verified interval [start, end); there is
     explicitly no past-due grace.
ST5  Activation is immutable/idempotent per (subscription_id, verified period)
     while lifecycle refreshes inside that period remain mutable.
ST6  Stripe access is injected as a verifier/link provider.  No Stripe secret
     is accepted, logged, persisted, or returned; checkout/portal are hosted.
ST7  Included, overage, and period counters conserve exactly.  A new quota is
     created only for a newly Stripe-verified period, never by local guessing.
ST8  Every activation and entitlement snapshots/references the versioned plan
     catalog and its SHA-256; bundle coverage is exact and deterministic.

The payment gate mutates this core out-of-band, so quota mutation uses an
explicit reserve -> StateStore.save -> commit/rollback protocol.  The reserve
holds the core transaction lock until finalized, preventing concurrent quota
decisions from overtaking the durable snapshot.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import logging
import re
import secrets
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse


VERSION = "0.1.1"
# Catalog resolution: the VIRIDIS_PLAN_CATALOG env var (absolute path) wins
# when set AND readable, so a priced/approved catalog can ship as pure data
# (docker cp + env) with zero code edits; otherwise the baked default loads.
# A bad override falls back to the baked catalog — never a boot failure.
_DEFAULT_DATA_PATH = (Path(__file__).resolve().parents[1] / "data" /
                      "plan_catalog.v0.2.0.json")
_OVERRIDE = os.environ.get("VIRIDIS_PLAN_CATALOG", "")
DATA_PATH = _DEFAULT_DATA_PATH
if _OVERRIDE:
    _p = Path(_OVERRIDE)
    if _p.is_file():
        DATA_PATH = _p
_RAW_CATALOG = DATA_PATH.read_bytes()
PLAN_CATALOG = json.loads(_RAW_CATALOG)
PLAN_CATALOG_SHA256 = hashlib.sha256(_RAW_CATALOG).hexdigest()
LIFECYCLE = frozenset({"active", "past_due", "canceled", "expired"})
SEAT_ACQUISITION_SOURCES = (
    "awesome_x402",
    "meshmcp",
    "x402_success",
    "openclaw",
    "github",
    "internal",
    "search",
    "direct",
    "other",
    "unattributed",
)
_PRICE_ID_RE = re.compile(r"^price_[A-Za-z0-9]+$")
_SUBSCRIPTION_ID_RE = re.compile(r"^sub_[A-Za-z0-9]+$")
_STRIPE_LIFECYCLE = {
    "active": "active",
    "past_due": "past_due",
    "unpaid": "past_due",
    "canceled": "canceled",
    "incomplete_expired": "expired",
    "trialing": "expired",
    "incomplete": "expired",
    "paused": "expired",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_account_key() -> str:
    return "vir_acct_" + secrets.token_urlsafe(32)


def _instant(value: Any, field_name: str) -> datetime:
    """Normalize a Stripe-adapter instant to timezone-aware UTC."""
    if isinstance(value, bool) or value is None:
        raise ValidationError(f"'{field_name}' must be an ISO instant or epoch",
                              field_name, value, "UTC instant")
    try:
        if isinstance(value, int):
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        elif isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
    except (OSError, OverflowError, TypeError, ValueError):
        raise ValidationError(f"'{field_name}' must be an ISO instant or epoch",
                              field_name, value, "UTC instant")
    if parsed.tzinfo is None:
        raise ValidationError(f"'{field_name}' must include a timezone",
                              field_name, value, "timezone-aware UTC instant")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_text(value: Any, field_name: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"'{field_name}' must be a non-empty string",
                              field_name, value, "non-empty string")
    text = value.strip()
    if len(text) > maximum:
        raise ValidationError(f"'{field_name}' is too long", field_name,
                              "[redacted]", f"length <= {maximum}")
    return text


def _minor(value: Any, field_name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"'{field_name}' must be integer minor units",
                              field_name, value, "integer minor units")
    minimum = 1 if positive else 0
    if value < minimum:
        raise ValidationError(f"'{field_name}' must be >= {minimum}",
                              field_name, value, f">= {minimum}")
    return value


class ValidationError(ValueError):
    def __init__(self, message: str, field: str = "", value: Any = None,
                 constraint: str = ""):
        super().__init__(message)
        self.field = field
        self.value = value
        self.constraint = constraint


class ConfigurationError(RuntimeError):
    pass


class VerificationError(RuntimeError):
    pass


class ConservationError(RuntimeError):
    pass


class DurabilityError(RuntimeError):
    """A verified activation could not be committed before acknowledgement."""

    pass


def _validate_catalog(catalog: dict) -> Dict[str, dict]:
    if not isinstance(catalog, dict) or not isinstance(catalog.get("plans"), list):
        raise RuntimeError("invalid bundled plan catalog")
    plans: Dict[str, dict] = {}
    price_ids: set[str] = set()
    for raw in catalog["plans"]:
        required = {"id", "name", "price_minor", "interval",
                    "covered_agents", "included_calls_per_month", "overage",
                    "stripe_price_id", "approval_status", "checkout_enabled",
                    "coverage_ready"}
        if not isinstance(raw, dict) or not required.issubset(raw):
            raise RuntimeError("plan catalog entry is incomplete")
        plan_id = raw["id"]
        if not isinstance(plan_id, str) or not plan_id or plan_id in plans:
            raise RuntimeError("plan ids must be unique non-empty strings")
        if raw["interval"] != "month" or raw["overage"] != "per_call_rate":
            raise RuntimeError(f"unsupported plan terms for {plan_id}")
        _minor(raw["price_minor"], "price_minor", positive=True)
        _minor(raw["included_calls_per_month"],
               "included_calls_per_month", positive=True)
        covered = raw["covered_agents"]
        if (not isinstance(covered, list) or not covered or
                any(not isinstance(item, str) or not item for item in covered) or
                covered != sorted(set(covered))):
            raise RuntimeError(f"covered_agents must be sorted/unique for {plan_id}")
        if raw["stripe_price_id"] is not None and not (
                isinstance(raw["stripe_price_id"], str) and
                _PRICE_ID_RE.fullmatch(raw["stripe_price_id"])):
            raise RuntimeError(f"invalid Stripe Price id for {plan_id}")
        if raw["stripe_price_id"] is not None:
            if raw["stripe_price_id"] in price_ids:
                raise RuntimeError("configured Stripe Price ids must be unique")
            price_ids.add(raw["stripe_price_id"])
        if not isinstance(raw["checkout_enabled"], bool):
            raise RuntimeError(f"checkout_enabled must be boolean for {plan_id}")
        if not isinstance(raw["coverage_ready"], bool):
            raise RuntimeError(f"coverage_ready must be boolean for {plan_id}")
        plans[plan_id] = deepcopy(raw)
    return plans


_PLAN_INDEX = _validate_catalog(PLAN_CATALOG)


@dataclass
class AgentConfig:
    name: str = "subscriptions-agent"
    version: str = VERSION
    debug: bool = False
    # These dependencies live on config because the fleet StateStore excludes
    # config from snapshots.  Provider credentials therefore cannot be
    # persisted accidentally by this core (ST6).
    stripe_provider: Optional[Any] = field(default=None, repr=False)
    clock: Callable[[], datetime] = field(default=_utcnow, repr=False)
    key_factory: Callable[[], str] = field(default=_new_account_key, repr=False)
    catalog: Optional[dict] = field(default=None, repr=False)
    catalog_sha256: Optional[str] = field(default=None, repr=False)
    stripe_livemode_expected: bool = True
    # Production injects ``lambda: store.save("subscriptions", core)`` so a
    # newly verified activation is durable before its one-time account key is
    # acknowledged.  The hook is deliberately held on excluded config state:
    # callback identity and storage internals must never enter snapshots.
    durable_activation_commit: Optional[Callable[[], bool]] = field(
        default=None, repr=False)
    transaction_lock: Any = field(default_factory=threading.RLock, repr=False)
    rollback_journal: Dict[str, dict] = field(default_factory=dict, repr=False)


@dataclass
class Account:
    account_id: str
    account_ref_sha256: str
    account_key_sha256: str
    account_key_last4: str
    created_at: str
    stripe_customer_id: Optional[str] = None

    def public(self) -> dict:
        return {
            "account_id": self.account_id,
            "account_key": "****" + self.account_key_last4,
            "created_at": self.created_at,
        }


@dataclass
class Subscription:
    subscription_id: str
    account_id: str
    plan_id: str
    status: str
    current_period_key: str
    stripe_customer_id: str
    created_at: str
    updated_at: str


@dataclass
class SubscriptionPeriod:
    period_key: str
    subscription_id: str
    account_id: str
    plan_id: str
    status: str
    stripe_status: str
    current_period_start: str
    current_period_end: str
    included_calls: int
    plan_price_minor: int
    covered_agents: List[str]
    catalog_version: str
    catalog_sha256: str
    livemode: bool
    activated_at: str
    updated_at: str


@dataclass
class UsageCounter:
    period_key: str
    subscription_id: str
    account_id: str
    plan_id: str
    included_limit: int
    included_used: int = 0
    overage_calls: int = 0
    overage_minor: int = 0
    last_used_at: Optional[str] = None

    def public(self) -> dict:
        used = self.included_used + self.overage_calls
        return {
            "period_key": self.period_key,
            "subscription_id": self.subscription_id,
            "plan_id": self.plan_id,
            "included_calls": self.included_limit,
            "included_used": self.included_used,
            "included_remaining": max(0, self.included_limit - self.included_used),
            "overage_calls": self.overage_calls,
            "overage_minor": self.overage_minor,
            "used_calls": used,
            "last_value_at": getattr(self, "last_used_at", None),
        }


class SubscriptionsCore:
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.logger = logging.getLogger(self.config.name)
        self.logger.setLevel(logging.DEBUG if self.config.debug else logging.INFO)
        self._accounts: Dict[str, Account] = {}
        self._account_by_ref: Dict[str, str] = {}
        self._account_by_key: Dict[str, str] = {}
        self._subscriptions: Dict[str, Subscription] = {}
        self._periods: Dict[str, SubscriptionPeriod] = {}
        self._activation_keys: set[str] = set()
        self._usage: Dict[str, UsageCounter] = {}
        self._request_decisions: Dict[str, dict] = {}
        self._audit_events: List[dict] = []
        # Aggregate-only seat-front-door funnel state.  These counters are
        # intentionally free of account refs, Stripe identifiers, hosted
        # URLs, bearer keys, and request metadata so StateStore can persist
        # useful capital metrics without creating a PII side channel.
        self._frontdoor_metrics: Dict[str, int] = {
            "page_views": 0,
            "checkouts_started": 0,
            "snapshot_page_views": 0,
            "snapshot_checkouts_started": 0,
            "snapshot_paid": 0,
            "landing_page_views": 0,
        }
        # Acquisition attribution is deliberately finite and aggregate-only.
        # The gateway maps request context into these fixed labels before
        # calling the core; raw URLs, referrers, query strings, IPs, user
        # agents, and account identifiers are never accepted or retained.
        self._acquisition_surface_views: Dict[str, int] = {
            "agents": 0,
            "quickstart": 0,
        }
        self._acquisition_source_views: Dict[str, int] = {
            source: 0
            for source in SEAT_ACQUISITION_SOURCES
            if source != "unattributed"
        }
        # Seat acquisition is tracked separately from the /agents and
        # /quickstart landing surfaces so the monthly-revenue funnel has a
        # source denominator of its own. Only the same finite labels are
        # accepted; raw referrers and campaign values never enter core state.
        self._seat_source_views: Dict[str, int] = {
            source: 0
            for source in SEAT_ACQUISITION_SOURCES
            if source != "unattributed"
        }
        # Complete aggregate seat funnel. Subscription ids are already part of
        # the entitlement ledger; this parallel map binds each one to only a
        # finite source label and never stores raw campaign or referrer data.
        self._seat_funnel_by_source: Dict[str, Dict[str, int]] = {
            source: {
                "checkout_starts": 0,
                "paid": 0,
                "activated": 0,
                "renewed": 0,
            }
            for source in SEAT_ACQUISITION_SOURCES
        }
        self._subscription_acquisition_source: Dict[str, str] = {}
        # Stripe Checkout Session identifiers are never retained.  Only their
        # SHA-256 digests are persisted to make paid-success recording
        # idempotent across reloads.
        self._snapshot_paid_sessions: set[str] = set()

    # ---------------------------- catalog / time ----------------------------
    @property
    def catalog(self) -> dict:
        return self.config.catalog if self.config.catalog is not None else PLAN_CATALOG

    @property
    def catalog_sha256(self) -> str:
        if self.config.catalog_sha256:
            return self.config.catalog_sha256
        if self.config.catalog is None:
            return PLAN_CATALOG_SHA256
        return _digest(self.config.catalog)

    @property
    def plans(self) -> Dict[str, dict]:
        if self.config.catalog is None:
            return _PLAN_INDEX
        return _validate_catalog(self.config.catalog)

    def _now(self) -> datetime:
        value = self.config.clock()
        return _instant(value, "clock")

    def _catalog_ref(self, *, version: Optional[str] = None,
                     sha256: Optional[str] = None) -> dict:
        return {"version": version or self.catalog["pack_version"],
                "sha256": sha256 or self.catalog_sha256}

    def _get_plan(self, plan_id: Any) -> dict:
        key = _require_text(plan_id, "plan_id", maximum=80)
        plan = self.plans.get(key)
        if plan is None:
            raise ValidationError("unknown plan", "plan_id", key,
                                  "one of: " + ", ".join(sorted(self.plans)))
        return plan

    # ------------------------------- envelopes ------------------------------
    def _err(self, message: str, *, error_type: str = "Error", field: str = "",
             value: Any = None, constraint: str = "") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _iso(self._now())}

    def _ok(self, data: Any) -> dict:
        return {"status": "ok", "data": data, "error": None,
                "timestamp": _iso(self._now())}

    def _audit(self, event_type: str, detail: dict) -> dict:
        # Account keys, account refs, hosted URLs, and provider payloads must
        # never enter this log.  Call sites pass allow-listed identifiers only.
        previous = (self._audit_events[-1]["event_sha256"]
                    if self._audit_events else "0" * 64)
        body = {"sequence": len(self._audit_events) + 1,
                "event_type": event_type, "detail": deepcopy(detail),
                "previous_event_sha256": previous,
                "occurred_at": _iso(self._now())}
        event = {**body, "event_sha256": _digest(body)}
        self._audit_events.append(event)
        return event

    # ------------------------------- accounts -------------------------------
    @staticmethod
    def _account_id(ref_digest: str) -> str:
        return "acct_" + ref_digest[:24]

    def _ensure_account(self, account_ref: Any) -> Tuple[Account, Optional[str]]:
        ref = _require_text(account_ref, "account_ref")
        ref_digest = hashlib.sha256(ref.encode("utf-8")).hexdigest()
        existing_id = self._account_by_ref.get(ref_digest)
        if existing_id:
            return self._accounts[existing_id], None
        raw_key = _require_text(self.config.key_factory(), "generated_account_key",
                                maximum=256)
        if len(raw_key) < 32:
            raise RuntimeError("account key generator returned insufficient entropy")
        key_digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        if key_digest in self._account_by_key:
            raise RuntimeError("account key collision")
        account_id = self._account_id(ref_digest)
        if account_id in self._accounts:
            raise RuntimeError("account id collision")
        account = Account(account_id=account_id,
                          account_ref_sha256=ref_digest,
                          account_key_sha256=key_digest,
                          account_key_last4=raw_key[-4:],
                          created_at=_iso(self._now()))
        self._accounts[account_id] = account
        self._account_by_ref[ref_digest] = account_id
        self._account_by_key[key_digest] = account_id
        self._audit("account_created", {"account_id": account_id})
        return account, raw_key

    def create_account(self, account_ref: Any) -> dict:
        with self.config.transaction_lock:
            account, raw_key = self._ensure_account(account_ref)
            result = {**account.public(), "created": raw_key is not None,
                      "account_key_issued_once": raw_key is not None}
            if raw_key is not None:  # only plaintext-key return in the system
                result["account_key"] = raw_key
            return result

    def resolve_account_key(self, account_key: Any) -> Optional[str]:
        """Internal gateway helper.  Never expose the digest or raw key."""
        if not isinstance(account_key, str) or not account_key:
            return None
        digest = hashlib.sha256(account_key.encode("utf-8")).hexdigest()
        account_id = self._account_by_key.get(digest)
        if account_id is None:
            return None
        stored = self._accounts[account_id].account_key_sha256
        return account_id if hmac.compare_digest(digest, stored) else None

    def _authorize(self, account_id: Any, account_key: Any) -> Account:
        ident = _require_text(account_id, "account_id", maximum=80)
        resolved = self.resolve_account_key(account_key)
        if resolved is None or not hmac.compare_digest(resolved, ident):
            raise ValidationError("bearer account key does not own account",
                                  "authorization", "[redacted]",
                                  "valid bearer for account_id")
        account = self._accounts.get(ident)
        if account is None:
            raise ValidationError("unknown account", "account_id", ident,
                                  "existing account")
        return account

    # ----------------------------- plan actions -----------------------------
    def _checkout_configuration_error(self, plan: dict) -> Optional[str]:
        """Return the first fail-closed readiness reason, without side effects.

        This is the single source of truth used both by public catalog
        annotations and by the state-changing Checkout path.  It deliberately
        exposes no provider object, configuration detail, or credential.
        """
        if plan.get("approval_status") != "approved":
            return "plan is draft and awaits owner price/quota approval"
        if plan.get("checkout_enabled") is not True:
            return "checkout is disabled for this plan"
        if plan.get("coverage_ready") is not True:
            return "plan coverage includes an unavailable agent"
        if not plan.get("stripe_price_id"):
            return "Stripe recurring Price is not configured"
        if self.config.stripe_provider is None:
            return "Stripe subscription link provider is unavailable"
        return None

    def _annotated_plan(self, plan: dict) -> dict:
        result = deepcopy(plan)
        configuration_required = (
            self._checkout_configuration_error(plan) is not None)
        result.update({
            "checkout_status": (
                "configuration_required" if configuration_required else "ready"),
            "configuration_required": configuration_required,
        })
        return result

    def list_plans(self) -> dict:
        return {
            "schema_version": self.catalog["schema_version"],
            "pack_version": self.catalog["pack_version"],
            "plan_catalog_sha256": self.catalog_sha256,
            "currency": self.catalog["currency"],
            "plans": [self._annotated_plan(self.plans[key])
                      for key in sorted(self.plans)],
            "configuration_notice": self.catalog["configuration_notice"],
        }

    def get_plan(self, plan_id: Any) -> dict:
        return {"plan": self._annotated_plan(self._get_plan(plan_id)),
                "pack_version": self.catalog["pack_version"],
                "plan_catalog_sha256": self.catalog_sha256,
                "configuration_notice": self.catalog["configuration_notice"]}

    # ------------------------- seat front-door funnel ----------------------
    def _normalize_frontdoor_schema(self) -> None:
        """Migrate older durable snapshots without losing their counters."""
        if not isinstance(self._frontdoor_metrics, dict):
            return
        defaults = {
            "page_views": 0,
            "checkouts_started": 0,
            "snapshot_page_views": 0,
            "snapshot_checkouts_started": 0,
            "snapshot_paid": 0,
            "landing_page_views": 0,
        }
        for name, value in defaults.items():
            self._frontdoor_metrics.setdefault(name, value)
        if not hasattr(self, "_snapshot_paid_sessions"):
            self._snapshot_paid_sessions = set()
        if not hasattr(self, "_acquisition_surface_views"):
            self._acquisition_surface_views = {
                "agents": 0,
                "quickstart": 0,
            }
        if not hasattr(self, "_acquisition_source_views"):
            self._acquisition_source_views = {
                source: 0
                for source in SEAT_ACQUISITION_SOURCES
                if source != "unattributed"
            }
        elif isinstance(self._acquisition_source_views, dict):
            for source in SEAT_ACQUISITION_SOURCES:
                if source != "unattributed":
                    self._acquisition_source_views.setdefault(source, 0)
        if not hasattr(self, "_seat_source_views"):
            self._seat_source_views = {
                source: 0
                for source in SEAT_ACQUISITION_SOURCES
                if source != "unattributed"
            }
        elif isinstance(self._seat_source_views, dict):
            for source in SEAT_ACQUISITION_SOURCES:
                if source != "unattributed":
                    self._seat_source_views.setdefault(source, 0)
        if not hasattr(self, "_seat_funnel_by_source"):
            self._seat_funnel_by_source = {
                source: {
                    "checkout_starts": 0,
                    "paid": 0,
                    "activated": 0,
                    "renewed": 0,
                }
                for source in SEAT_ACQUISITION_SOURCES
            }
            self._seat_funnel_by_source["unattributed"][
                "checkout_starts"] = self._frontdoor_metrics[
                    "checkouts_started"]
            for _subscription_id in self._subscriptions:
                self._seat_funnel_by_source["unattributed"]["paid"] += 1
                self._seat_funnel_by_source["unattributed"]["activated"] += 1
            renewal_count = max(
                len(self._periods) - len(self._subscriptions), 0)
            self._seat_funnel_by_source["unattributed"][
                "renewed"] = renewal_count
        else:
            for source in SEAT_ACQUISITION_SOURCES:
                self._seat_funnel_by_source.setdefault(source, {
                    "checkout_starts": 0,
                    "paid": 0,
                    "activated": 0,
                    "renewed": 0,
                })
        if not hasattr(self, "_subscription_acquisition_source"):
            self._subscription_acquisition_source = {
                subscription_id: "unattributed"
                for subscription_id in self._subscriptions
            }

    def _assert_frontdoor_conservation(self) -> None:
        self._normalize_frontdoor_schema()
        metrics = self._frontdoor_metrics
        expected = {
            "page_views",
            "checkouts_started",
            "snapshot_page_views",
            "snapshot_checkouts_started",
            "snapshot_paid",
            "landing_page_views",
        }
        if not isinstance(metrics, dict) or set(metrics) != expected:
            raise ConservationError("front-door metric schema drift")
        for name in sorted(expected):
            value = metrics[name]
            if type(value) is not int or value < 0:
                raise ConservationError(
                    f"front-door metric {name} must be a non-negative integer")
        view_events = sum(
            1 for event in self._audit_events
            if event.get("event_type") == "frontdoor_page_view_recorded")
        checkout_events = sum(
            1 for event in self._audit_events
            if event.get("event_type") == "frontdoor_checkout_started")
        snapshot_view_events = sum(
            1 for event in self._audit_events
            if event.get("event_type") == "snapshot_page_view_recorded")
        snapshot_checkout_events = sum(
            1 for event in self._audit_events
            if event.get("event_type") == "snapshot_checkout_started")
        snapshot_paid_events = sum(
            1 for event in self._audit_events
            if event.get("event_type") == "snapshot_payment_verified")
        acquisition_events = [
            event for event in self._audit_events
            if event.get("event_type") == "acquisition_page_view_recorded"]
        seat_source_events = [
            event for event in self._audit_events
            if event.get("event_type") == "seat_source_view_recorded"]
        if view_events != metrics["page_views"]:
            raise ConservationError("front-door page-view event drift")
        if checkout_events != metrics["checkouts_started"]:
            raise ConservationError("front-door checkout event drift")
        if snapshot_view_events != metrics["snapshot_page_views"]:
            raise ConservationError("snapshot page-view event drift")
        if snapshot_checkout_events != metrics["snapshot_checkouts_started"]:
            raise ConservationError("snapshot checkout event drift")
        if snapshot_paid_events != metrics["snapshot_paid"]:
            raise ConservationError("snapshot paid event drift")
        expected_surfaces = {"agents", "quickstart"}
        expected_sources = {
            source
            for source in SEAT_ACQUISITION_SOURCES
            if source != "unattributed"
        }
        for values, expected_names, label in (
                (self._acquisition_surface_views, expected_surfaces, "surface"),
                (self._acquisition_source_views, expected_sources, "source")):
            if not isinstance(values, dict) or set(values) != expected_names:
                raise ConservationError(
                    f"acquisition {label} metric schema drift")
            if any(type(value) is not int or value < 0
                   for value in values.values()):
                raise ConservationError(
                    f"acquisition {label} metrics must be non-negative integers")
        if (not isinstance(self._seat_source_views, dict)
                or set(self._seat_source_views) != expected_sources
                or any(type(value) is not int or value < 0
                       for value in self._seat_source_views.values())):
            raise ConservationError(
                "seat acquisition source metrics must be finite non-negative "
                "integers")
        if len(acquisition_events) != metrics["landing_page_views"]:
            raise ConservationError("acquisition landing-view event drift")
        if sum(self._acquisition_surface_views.values()) != len(
                acquisition_events):
            raise ConservationError("acquisition surface count drift")
        if sum(self._acquisition_source_views.values()) != len(
                acquisition_events):
            raise ConservationError("acquisition source count drift")
        event_surfaces = {
            name: sum(
                1 for event in acquisition_events
                if event.get("detail", {}).get("surface") == name)
            for name in expected_surfaces
        }
        event_sources = {
            name: sum(
                1 for event in acquisition_events
                if event.get("detail", {}).get("source") == name)
            for name in expected_sources
        }
        if event_surfaces != self._acquisition_surface_views:
            raise ConservationError("acquisition surface event drift")
        if event_sources != self._acquisition_source_views:
            raise ConservationError("acquisition source event drift")
        if sum(self._seat_source_views.values()) != len(seat_source_events):
            raise ConservationError("seat acquisition source count drift")
        if len(seat_source_events) > metrics["page_views"]:
            raise ConservationError(
                "attributed seat views exceed total seat page views")
        event_seat_sources = {
            name: sum(
                1 for event in seat_source_events
                if event.get("detail", {}).get("source") == name)
            for name in expected_sources
        }
        if event_seat_sources != self._seat_source_views:
            raise ConservationError("seat acquisition source event drift")
        stages = {"checkout_starts", "paid", "activated", "renewed"}
        if (not isinstance(self._seat_funnel_by_source, dict)
                or set(self._seat_funnel_by_source)
                != set(SEAT_ACQUISITION_SOURCES)):
            raise ConservationError("seat source funnel schema drift")
        for source, values in self._seat_funnel_by_source.items():
            if (not isinstance(values, dict) or set(values) != stages
                    or any(type(value) is not int or value < 0
                           for value in values.values())):
                raise ConservationError(
                    f"seat source funnel values invalid for {source}")
        stage_totals = {
            stage: sum(
                values[stage]
                for values in self._seat_funnel_by_source.values()
            )
            for stage in stages
        }
        if stage_totals["checkout_starts"] != metrics["checkouts_started"]:
            raise ConservationError("seat source checkout count drift")
        if stage_totals["paid"] != len(self._subscriptions):
            raise ConservationError("seat source paid count drift")
        if stage_totals["activated"] != len(self._subscriptions):
            raise ConservationError("seat source activation count drift")
        if stage_totals["renewed"] != max(
                len(self._periods) - len(self._subscriptions), 0):
            raise ConservationError("seat source renewal count drift")
        if (not isinstance(self._subscription_acquisition_source, dict)
                or set(self._subscription_acquisition_source)
                != set(self._subscriptions)
                or any(source not in SEAT_ACQUISITION_SOURCES
                       for source
                       in self._subscription_acquisition_source.values())):
            raise ConservationError(
                "subscription acquisition source binding drift")
        if (not isinstance(self._snapshot_paid_sessions, set)
                or len(self._snapshot_paid_sessions) != metrics["snapshot_paid"]
                or any(not isinstance(value, str) or len(value) != 64
                       for value in self._snapshot_paid_sessions)):
            raise ConservationError("snapshot paid-session digest drift")

    def record_frontdoor_view(self, source: Any = None) -> dict:
        """Record one public /seats render with optional finite attribution."""
        source_name = None
        if source is not None:
            source_name = _require_text(source, "source", maximum=32)
            expected_sources = set(self._seat_source_views)
            if source_name not in expected_sources:
                raise ValidationError(
                    "unknown seat acquisition source", "source", source_name,
                    "one of: " + ", ".join(sorted(expected_sources)))
        with self.config.transaction_lock:
            self._assert_frontdoor_conservation()
            self._frontdoor_metrics["page_views"] += 1
            self._audit("frontdoor_page_view_recorded", {
                "page_views": self._frontdoor_metrics["page_views"],
            })
            if source_name is not None:
                self._seat_source_views[source_name] += 1
                self._audit("seat_source_view_recorded", {
                    "source": source_name,
                    "seat_attributed_views":
                        sum(self._seat_source_views.values()),
                    "classification":
                        "seller_reported_aggregate_telemetry",
                })
            self._assert_frontdoor_conservation()
            return {"recorded": True,
                    "page_views": self._frontdoor_metrics["page_views"],
                    "checkouts_started":
                        self._frontdoor_metrics["checkouts_started"],
                    "source": source_name}

    @staticmethod
    def _seat_funnel_source(value: Any) -> str:
        if value is None:
            return "unattributed"
        source = _require_text(value, "acquisition_source", maximum=32)
        if source not in SEAT_ACQUISITION_SOURCES:
            raise ValidationError(
                "unknown seat acquisition source",
                "acquisition_source",
                source,
                "one of: " + ", ".join(SEAT_ACQUISITION_SOURCES),
            )
        return source

    def _record_checkout_started(self, plan_id: str, source: str) -> None:
        """Increment only after a hosted Checkout URL passes verification."""
        with self.config.transaction_lock:
            self._assert_frontdoor_conservation()
            self._frontdoor_metrics["checkouts_started"] += 1
            self._seat_funnel_by_source[source]["checkout_starts"] += 1
            self._audit("frontdoor_checkout_started", {
                "plan_id": plan_id,
                "acquisition_source": source,
                "checkouts_started":
                    self._frontdoor_metrics["checkouts_started"],
                "catalog": self._catalog_ref(),
            })
            self._assert_frontdoor_conservation()

    def record_snapshot_view(self) -> dict:
        """Record one public Compliance Snapshot page render without PII."""
        with self.config.transaction_lock:
            self._assert_frontdoor_conservation()
            self._frontdoor_metrics["snapshot_page_views"] += 1
            self._audit("snapshot_page_view_recorded", {
                "snapshot_page_views":
                    self._frontdoor_metrics["snapshot_page_views"],
            })
            self._assert_frontdoor_conservation()
            return {
                "recorded": True,
                "snapshot_page_views":
                    self._frontdoor_metrics["snapshot_page_views"],
            }

    def record_snapshot_checkout_started(self) -> dict:
        """Record only after Stripe returns a verified hosted Checkout URL."""
        with self.config.transaction_lock:
            self._assert_frontdoor_conservation()
            self._frontdoor_metrics["snapshot_checkouts_started"] += 1
            self._audit("snapshot_checkout_started", {
                "snapshot_checkouts_started":
                    self._frontdoor_metrics["snapshot_checkouts_started"],
            })
            self._assert_frontdoor_conservation()
            return {
                "recorded": True,
                "snapshot_checkouts_started":
                    self._frontdoor_metrics["snapshot_checkouts_started"],
            }

    def record_snapshot_paid(self, stripe_reference: Any) -> dict:
        """Record a pull-verified live $49 payment once, using only a digest."""
        reference = _require_text(
            stripe_reference, "stripe_reference", maximum=255)
        digest = hashlib.sha256(reference.encode("utf-8")).hexdigest()
        with self.config.transaction_lock:
            self._assert_frontdoor_conservation()
            if digest in self._snapshot_paid_sessions:
                return {
                    "recorded": False,
                    "idempotent_replay": True,
                    "snapshot_paid": self._frontdoor_metrics["snapshot_paid"],
                }
            self._snapshot_paid_sessions.add(digest)
            self._frontdoor_metrics["snapshot_paid"] += 1
            self._audit("snapshot_payment_verified", {
                "stripe_reference_sha256": digest,
                "snapshot_paid": self._frontdoor_metrics["snapshot_paid"],
            })
            self._assert_frontdoor_conservation()
            return {
                "recorded": True,
                "idempotent_replay": False,
                "snapshot_paid": self._frontdoor_metrics["snapshot_paid"],
            }

    def record_acquisition_view(self, surface: Any, source: Any) -> dict:
        """Record one aggregate landing render from finite non-PII labels."""
        surface_name = _require_text(surface, "surface", maximum=32)
        source_name = _require_text(source, "source", maximum=32)
        with self.config.transaction_lock:
            self._assert_frontdoor_conservation()
            if surface_name not in self._acquisition_surface_views:
                raise ValidationError(
                    "unknown acquisition surface", "surface", surface_name,
                    "one of: " + ", ".join(
                        sorted(self._acquisition_surface_views)))
            if source_name not in self._acquisition_source_views:
                raise ValidationError(
                    "unknown acquisition source", "source", source_name,
                    "one of: " + ", ".join(
                        sorted(self._acquisition_source_views)))
            self._frontdoor_metrics["landing_page_views"] += 1
            self._acquisition_surface_views[surface_name] += 1
            self._acquisition_source_views[source_name] += 1
            self._audit("acquisition_page_view_recorded", {
                "surface": surface_name,
                "source": source_name,
                "landing_page_views":
                    self._frontdoor_metrics["landing_page_views"],
                "classification": "seller_reported_aggregate_telemetry",
            })
            self._assert_frontdoor_conservation()
            return {
                "recorded": True,
                "landing_page_views":
                    self._frontdoor_metrics["landing_page_views"],
                "surface": surface_name,
                "source": source_name,
            }

    def frontdoor_summary(self) -> dict:
        """Return only aggregate funnel and live capital metrics."""
        with self.config.transaction_lock:
            self._assert_frontdoor_conservation()
            mrr = self.mrr_summary()
            seat_attributed = sum(self._seat_source_views.values())
            return {
                "page_views": self._frontdoor_metrics["page_views"],
                "checkouts_started":
                    self._frontdoor_metrics["checkouts_started"],
                "snapshot_page_views":
                    self._frontdoor_metrics["snapshot_page_views"],
                "snapshot_checkouts_started":
                    self._frontdoor_metrics["snapshot_checkouts_started"],
                "snapshot_paid":
                    self._frontdoor_metrics["snapshot_paid"],
                "landing_page_views":
                    self._frontdoor_metrics["landing_page_views"],
                "acquisition_surface_views":
                    deepcopy(self._acquisition_surface_views),
                "acquisition_source_views":
                    deepcopy(self._acquisition_source_views),
                "acquisition_classification": (
                    "seller_reported_aggregate_telemetry_not_revenue"),
                "seat_source_views": deepcopy(self._seat_source_views),
                "seat_attributed_views": seat_attributed,
                "seat_unattributed_views":
                    self._frontdoor_metrics["page_views"] - seat_attributed,
                "seat_acquisition_classification": (
                    "seller_reported_aggregate_telemetry_not_unique_buyers_"
                    "and_not_revenue"),
                "seat_funnel_by_source":
                    deepcopy(self._seat_funnel_by_source),
                "seat_funnel_source_classification": (
                    "provider_verified_aggregate_lifecycle_with_finite_"
                    "seller_attribution"),
                "active_subscriptions": mrr["active_subscriptions"],
                "mrr_minor": mrr["mrr_minor"],
                "currency": mrr["currency"],
                "plan_mix": mrr["plan_mix"],
                "catalog": mrr["catalog"],
            }

    @staticmethod
    def _hosted_url(value: Any, hostname: str, field_name: str) -> str:
        url = _require_text(value, field_name, maximum=2048)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != hostname:
            raise VerificationError(f"provider returned a non-{hostname} URL")
        return url

    def _checkout_ready(self, plan: dict) -> None:
        reason = self._checkout_configuration_error(plan)
        if reason is not None:
            raise ConfigurationError(reason)

    def create_checkout_link(
        self,
        plan_id: Any,
        account_ref: Any,
        acquisition_source: Any = None,
    ) -> dict:
        plan = self._get_plan(plan_id)
        ref = _require_text(account_ref, "account_ref")
        source = self._seat_funnel_source(acquisition_source)
        self._checkout_ready(plan)  # fail before creating any account state
        try:
            response = self.config.stripe_provider.create_subscription_checkout(
                plan_id=plan["id"], price_id=plan["stripe_price_id"],
                account_ref=ref, client_reference_id=ref,
                acquisition_source=source,
                catalog_version=self.catalog["pack_version"],
                catalog_sha256=self.catalog_sha256)
        except Exception as exc:
            self.logger.warning("Stripe-hosted checkout link creation failed (%s)",
                                type(exc).__name__)
            raise VerificationError("Stripe-hosted checkout link is unavailable")
        if not isinstance(response, dict):
            raise VerificationError("checkout provider returned an invalid response")
        if response.get("status") != "ok":
            raise VerificationError("Stripe-hosted checkout link is unavailable")
        if (not isinstance(response.get("livemode"), bool) or
                response.get("livemode") is not self.config.stripe_livemode_expected):
            raise VerificationError("Stripe Checkout live/test mode mismatch")
        url = self._hosted_url(response.get("url"), "checkout.stripe.com", "url")
        # The funnel records only a successfully created and fully validated
        # hosted Checkout.  No account_ref, session id, or URL is retained.
        self._record_checkout_started(plan["id"], source)
        return {"plan_id": plan["id"], "checkout_url": url,
                "mode": "subscription", "client_reference_id": ref,
                "acquisition_source": source,
                "money_movement": "human_completed_on_stripe",
                "catalog": self._catalog_ref()}

    # ------------------------- Stripe verification --------------------------
    def _verify_with_provider(self, reference: Any) -> dict:
        ref = _require_text(reference, "stripe_reference", maximum=255)
        provider = self.config.stripe_provider
        if provider is None:
            raise VerificationError("Stripe subscription verifier is unavailable")
        try:
            payload = provider.verify_subscription(ref)
        except Exception as exc:
            self.logger.warning("Stripe subscription verification failed (%s)",
                                type(exc).__name__)
            raise VerificationError("Stripe subscription verification failed")
        if (not isinstance(payload, dict) or payload.get("status") != "ok" or
                payload.get("verified") is not True):
            raise VerificationError("Stripe subscription was not verified")
        if payload.get("mode") != "subscription":
            raise VerificationError("verified Stripe object is not subscription mode")
        if (type(payload.get("line_item_count")) is not int or
                payload.get("line_item_count") != 1):
            raise VerificationError("subscription must contain exactly one recurring Price")
        return payload

    def _normalize_verified(self, payload: dict,
                            known_subscription_id: Optional[str] = None) -> dict:
        subscription_id = _require_text(payload.get("subscription_id"),
                                        "subscription_id", maximum=255)
        if known_subscription_id and not hmac.compare_digest(subscription_id,
                                                              known_subscription_id):
            raise VerificationError("Stripe verifier returned a different subscription")
        price_id = _require_text(payload.get("price_id"), "price_id", maximum=255)
        matching_plans = [plan for plan in self.plans.values()
                          if plan.get("stripe_price_id") == price_id]
        if len(matching_plans) != 1:
            raise VerificationError("verified recurring Price does not uniquely resolve a plan")
        plan = matching_plans[0]
        # Plan is derived solely from the unique verified price_id. Metadata is
        # then checked as a binding assertion, never trusted as the resolver.
        asserted_plan_id = _require_text(payload.get("plan_id"), "plan_id",
                                         maximum=80)
        if not hmac.compare_digest(asserted_plan_id, plan["id"]):
            raise VerificationError("Stripe plan metadata does not match Price")
        self._checkout_ready(plan)
        if type(payload.get("quantity")) is not int or payload.get("quantity") != 1:
            raise VerificationError("subscription item quantity must equal one")
        if (payload.get("interval") != "month" or
                type(payload.get("interval_count")) is not int or
                payload.get("interval_count") != 1):
            raise VerificationError("verified Price must recur every one month")
        if payload.get("currency") != self.catalog["currency"]:
            raise VerificationError("verified Price currency does not match catalog")
        if (type(payload.get("unit_amount")) is not int or
                payload.get("unit_amount") != plan["price_minor"]):
            raise VerificationError("verified Price amount does not match catalog")
        asserted_catalog_sha = _require_text(payload.get("catalog_sha256"),
                                             "catalog_sha256", maximum=64)
        if not hmac.compare_digest(asserted_catalog_sha, self.catalog_sha256):
            raise VerificationError("Stripe catalog binding is stale or mismatched")
        asserted_catalog_version = _require_text(
            payload.get("catalog_version"), "catalog_version", maximum=32)
        if not hmac.compare_digest(asserted_catalog_version,
                                   self.catalog["pack_version"]):
            raise VerificationError("Stripe catalog version binding is mismatched")
        livemode = payload.get("livemode")
        if not isinstance(livemode, bool) or livemode is not self.config.stripe_livemode_expected:
            raise VerificationError("Stripe live/test mode does not match deployment")
        if payload.get("price_active") is not True:
            raise VerificationError("verified recurring Price is not active")
        stripe_status = _require_text(payload.get("subscription_status"),
                                      "subscription_status", maximum=32)
        status = _STRIPE_LIFECYCLE.get(stripe_status)
        if status is None:
            raise VerificationError("unsupported subscription lifecycle status")
        start = _instant(payload.get("current_period_start"),
                         "current_period_start")
        end = _instant(payload.get("current_period_end"), "current_period_end")
        if start >= end:
            raise VerificationError("verified subscription period is empty or reversed")
        customer_id = _require_text(payload.get("customer_id"), "customer_id",
                                    maximum=255)
        account_ref = _require_text(
            payload.get("account_ref") or payload.get("client_reference_id"),
            "account_ref")
        existing = self._subscriptions.get(subscription_id)
        if existing is None:
            account_id = None
            acquisition_source = self._seat_funnel_source(
                payload.get("acquisition_source"))
        else:
            account_id = existing.account_id
            ref_sha = hashlib.sha256(account_ref.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(
                    ref_sha, self._accounts[account_id].account_ref_sha256):
                raise VerificationError("Stripe account binding does not match account")
            acquisition_source = self._subscription_acquisition_source.get(
                subscription_id, "unattributed")
            asserted_source = payload.get("acquisition_source")
            if asserted_source is not None:
                normalized_source = self._seat_funnel_source(asserted_source)
                if (acquisition_source != "unattributed"
                        and not hmac.compare_digest(
                            normalized_source, acquisition_source)):
                    raise VerificationError(
                        "Stripe acquisition source changed after activation")
        return {"subscription_id": subscription_id, "plan": plan,
                "status": status, "stripe_status": stripe_status,
                "start": start, "end": end,
                "customer_id": customer_id, "account_ref": account_ref,
                "account_id": account_id, "livemode": livemode,
                "acquisition_source": acquisition_source}

    @staticmethod
    def _period_key(subscription_id: str, start: datetime, end: datetime) -> str:
        return f"{subscription_id}|{_iso(start)}|{_iso(end)}"

    def _apply_verified(self, normalized: dict) -> Tuple[Subscription, bool,
                                                         Optional[str], bool]:
        """Apply a verified Stripe snapshot.

        Returns (subscription, activation_created, one_time_account_key,
        state_changed).  Activation idempotency and lifecycle refresh are
        deliberately separate (ST5).
        """
        sub_id = normalized["subscription_id"]
        plan = normalized["plan"]
        start, end = normalized["start"], normalized["end"]
        period_key = self._period_key(sub_id, start, end)
        now_iso = _iso(self._now())
        existing = self._subscriptions.get(sub_id)
        one_time_key: Optional[str] = None
        state_changed = False

        if existing is None:
            account, one_time_key = self._ensure_account(normalized["account_ref"])
            account_id = account.account_id
        else:
            account_id = existing.account_id
            account = self._accounts[account_id]

        customer_id = normalized["customer_id"]
        if account.stripe_customer_id and not hmac.compare_digest(
                account.stripe_customer_id, customer_id):
            raise VerificationError("Stripe customer does not match account")
        if not account.stripe_customer_id:
            account.stripe_customer_id = customer_id
            state_changed = True

        activation_created = period_key not in self._activation_keys
        if existing is not None:
            current = self._periods[existing.current_period_key]
            current_start = _instant(current.current_period_start,
                                     "stored_current_period_start")
            current_end = _instant(current.current_period_end,
                                   "stored_current_period_end")
            if period_key != existing.current_period_key:
                if end <= current_end:
                    # An old verified replay cannot rewind the current period.
                    if period_key in self._activation_keys:
                        return existing, False, None, state_changed
                    raise VerificationError("unseen stale subscription period")
                if start < current_end:
                    raise VerificationError("verified subscription periods overlap")
                if not activation_created:
                    raise ConservationError("activation key/current period drift")
            elif plan["id"] != existing.plan_id:
                raise VerificationError("plan cannot change inside a billing period")

        if activation_created:
            source = normalized["acquisition_source"]
            period = SubscriptionPeriod(
                period_key=period_key, subscription_id=sub_id,
                account_id=account_id, plan_id=plan["id"],
                status=normalized["status"],
                stripe_status=normalized["stripe_status"],
                current_period_start=_iso(start), current_period_end=_iso(end),
                included_calls=plan["included_calls_per_month"],
                plan_price_minor=plan["price_minor"],
                covered_agents=list(plan["covered_agents"]),
                catalog_version=self.catalog["pack_version"],
                catalog_sha256=self.catalog_sha256,
                livemode=normalized["livemode"],
                activated_at=now_iso, updated_at=now_iso)
            self._periods[period_key] = period
            self._activation_keys.add(period_key)
            self._usage[period_key] = UsageCounter(
                period_key=period_key, subscription_id=sub_id,
                account_id=account_id, plan_id=plan["id"],
                included_limit=plan["included_calls_per_month"])
            self._subscriptions[sub_id] = Subscription(
                subscription_id=sub_id, account_id=account_id,
                plan_id=plan["id"], status=normalized["status"],
                current_period_key=period_key, stripe_customer_id=customer_id,
                created_at=now_iso if existing is None else existing.created_at,
                updated_at=now_iso)
            if existing is None:
                self._subscription_acquisition_source[sub_id] = source
                self._seat_funnel_by_source[source]["paid"] += 1
                self._seat_funnel_by_source[source]["activated"] += 1
                lifecycle_stage = "activated"
            else:
                source = self._subscription_acquisition_source.get(
                    sub_id, "unattributed")
                self._seat_funnel_by_source[source]["renewed"] += 1
                lifecycle_stage = "renewed"
            state_changed = True
            self._audit("subscription_period_activated", {
                "subscription_id": sub_id, "account_id": account_id,
                "plan_id": plan["id"], "period_key": period_key,
                "status": normalized["status"],
                "acquisition_source": source,
                "lifecycle_stage": lifecycle_stage,
                "catalog": self._catalog_ref(),
            })
        else:
            # Mutable lifecycle refresh inside an immutable activation period.
            current_sub = self._subscriptions[sub_id]
            period = self._periods[current_sub.current_period_key]
            if (period.status != normalized["status"] or
                    period.stripe_status != normalized["stripe_status"] or
                    current_sub.status != normalized["status"]):
                period.status = normalized["status"]
                period.stripe_status = normalized["stripe_status"]
                period.updated_at = now_iso
                current_sub.status = normalized["status"]
                current_sub.updated_at = now_iso
                state_changed = True
                self._audit("subscription_lifecycle_refreshed", {
                    "subscription_id": sub_id, "account_id": account_id,
                    "period_key": period.period_key,
                    "status": normalized["status"],
                })

        self._assert_usage_conservation(period_key)
        self._assert_frontdoor_conservation()
        return self._subscriptions[sub_id], activation_created, one_time_key, state_changed

    def record_subscription(self, stripe_reference: Any) -> dict:
        with self.config.transaction_lock:
            self._normalize_frontdoor_schema()
            self._assert_frontdoor_conservation()
            payload = self._verify_with_provider(stripe_reference)
            normalized = self._normalize_verified(payload)
            # Verification above is read-only.  From this point onward every
            # mutable collection that activation can touch is snapshotted so
            # the acknowledgement (especially a one-time key) is atomic with
            # the production durability hook.
            before = self._transaction_snapshot()
            try:
                sub, created, one_time_key, state_changed = self._apply_verified(
                    normalized)
                # Build and validate the public shape before persistence.  No
                # operation that can fail remains after a successful commit
                # except attaching the already-generated one-time key.
                data = self._subscription_public(sub, self._now())
                data.update({"activation_created": created,
                             "idempotent_replay": not created,
                             "account_key_issued_once":
                                 one_time_key is not None})
            except Exception:
                self._restore_transaction_snapshot(before)
                raise

            commit = self.config.durable_activation_commit
            if state_changed and commit is not None:
                try:
                    committed = commit()
                except Exception as exc:
                    self._restore_transaction_snapshot(before)
                    # Only the exception class is logged.  Provider payloads,
                    # account refs, ids, and generated keys remain private.
                    self.logger.warning(
                        "durable subscription activation commit failed (%s)",
                        type(exc).__name__)
                    raise DurabilityError(
                        "subscription activation was not durably committed"
                    ) from None
                if committed is not True:
                    self._restore_transaction_snapshot(before)
                    self.logger.warning(
                        "durable subscription activation commit was rejected")
                    raise DurabilityError(
                        "subscription activation was not durably committed")

            if one_time_key is not None:  # only on first account activation
                data["account_key"] = one_time_key
            return data

    # ------------------------ entitlement transaction -----------------------
    def _effective_status(self, period: SubscriptionPeriod,
                          now: datetime) -> str:
        start = _instant(period.current_period_start, "current_period_start")
        end = _instant(period.current_period_end, "current_period_end")
        if period.status != "active":
            return period.status
        return "active" if start <= now < end else "expired"

    def _renewal_state(self, period: SubscriptionPeriod,
                       now: datetime) -> str:
        status = self._effective_status(period, now)
        if status == "past_due":
            return "failed"
        if status in {"canceled", "expired"}:
            return status
        end = _instant(period.current_period_end, "current_period_end")
        return "due_within_7d" if (end - now).total_seconds() <= 604800 \
            else "healthy"

    def _local_candidates(self, account_id: str, agent_id: str) -> List[Subscription]:
        matches = []
        for sub in self._subscriptions.values():
            if sub.account_id != account_id:
                continue
            period = self._periods.get(sub.current_period_key)
            if period is None:
                raise ConservationError("subscription references missing period")
            if agent_id in period.covered_agents:
                matches.append(sub)
        return sorted(matches, key=lambda item: item.subscription_id)

    def _refresh_candidates(self, candidates: List[Subscription]) -> None:
        # ST2/ST4: every potentially entitled call pull-verifies current Stripe
        # state.  Local 'active' can never survive a remote cancel/past_due.
        for sub in candidates:
            payload = self._verify_with_provider(sub.subscription_id)
            normalized = self._normalize_verified(payload, sub.subscription_id)
            if normalized["account_id"] != sub.account_id:
                raise VerificationError("verified account changed")
            self._apply_verified(normalized)

    def _active_matches(self, account_id: str, agent_id: str,
                        now: datetime) -> List[Tuple[Subscription, SubscriptionPeriod]]:
        result = []
        for sub in self._local_candidates(account_id, agent_id):
            period = self._periods[sub.current_period_key]
            if (agent_id in period.covered_agents and
                    self._effective_status(period, now) == "active"):
                result.append((sub, period))
        return result

    @staticmethod
    def _request_key(account_id: str, agent_id: str, request_id: str) -> str:
        return _digest({"account_id": account_id, "agent_id": agent_id,
                        "request_id": request_id})

    def _fallback(self, *, account_id: str, agent_id: str, request_id: str,
                  reason: str, lookup_error: bool = False) -> dict:
        return {
            "request_id": request_id, "account_id": account_id,
            "agent_id": agent_id, "path": "per_call_fallback",
            "entitled": False, "waive_per_call_charge": False,
            "should_run_per_call_gate": True,
            "bypass_anonymous_freemium": False,
            "requires_direct_overage_charge": False,
            "reason": reason, "lookup_error": lookup_error,
            "reservation_token": None, "durability_required": False,
            "catalog": self._catalog_ref(),
        }

    def _transaction_snapshot(self) -> dict:
        return {
            "accounts": deepcopy(self._accounts),
            "account_by_ref": deepcopy(self._account_by_ref),
            "account_by_key": deepcopy(self._account_by_key),
            "subscriptions": deepcopy(self._subscriptions),
            "periods": deepcopy(self._periods),
            "activation_keys": deepcopy(self._activation_keys),
            "usage": deepcopy(self._usage),
            "request_decisions": deepcopy(self._request_decisions),
            "audit_events": deepcopy(self._audit_events),
            "frontdoor_metrics": deepcopy(self._frontdoor_metrics),
            "snapshot_paid_sessions": deepcopy(self._snapshot_paid_sessions),
            "acquisition_surface_views":
                deepcopy(self._acquisition_surface_views),
            "acquisition_source_views":
                deepcopy(self._acquisition_source_views),
            "seat_source_views": deepcopy(self._seat_source_views),
            "seat_funnel_by_source":
                deepcopy(self._seat_funnel_by_source),
            "subscription_acquisition_source":
                deepcopy(self._subscription_acquisition_source),
        }

    def _restore_transaction_snapshot(self, snapshot: dict) -> None:
        self._accounts = snapshot["accounts"]
        self._account_by_ref = snapshot["account_by_ref"]
        self._account_by_key = snapshot["account_by_key"]
        self._subscriptions = snapshot["subscriptions"]
        self._periods = snapshot["periods"]
        self._activation_keys = snapshot["activation_keys"]
        self._usage = snapshot["usage"]
        self._request_decisions = snapshot["request_decisions"]
        self._audit_events = snapshot["audit_events"]
        self._frontdoor_metrics = snapshot["frontdoor_metrics"]
        self._snapshot_paid_sessions = snapshot["snapshot_paid_sessions"]
        self._acquisition_surface_views = snapshot.get(
            "acquisition_surface_views", {
                "agents": 0, "quickstart": 0})
        self._acquisition_source_views = snapshot.get(
            "acquisition_source_views", {
                "awesome_x402": 0, "meshmcp": 0, "x402_success": 0,
                "github": 0, "internal": 0, "search": 0, "direct": 0,
                "other": 0})
        self._seat_source_views = snapshot.get(
            "seat_source_views", {
                "awesome_x402": 0, "meshmcp": 0, "x402_success": 0,
                "github": 0, "internal": 0, "search": 0, "direct": 0,
                "other": 0})
        self._seat_funnel_by_source = snapshot.get(
            "seat_funnel_by_source", {
                source: {
                    "checkout_starts": 0,
                    "paid": 0,
                    "activated": 0,
                    "renewed": 0,
                }
                for source in SEAT_ACQUISITION_SOURCES
            })
        self._subscription_acquisition_source = snapshot.get(
            "subscription_acquisition_source", {})

    def reserve_entitlement(self, account_id: Any, agent_id: Any,
                            request_id: Any, per_call_price_minor: Any) -> dict:
        """Reserve exactly one quota/overage decision under the core lock.

        The caller MUST immediately call StateStore.save('subscriptions', core)
        and then commit_reservation(token) on success or
        rollback_reservation(token) on failure.  A non-null token means this
        method intentionally returns with the transaction lock held.
        """
        ident = _require_text(account_id, "account_id", maximum=80)
        agent = _require_text(agent_id, "agent_id", maximum=100)
        request = _require_text(request_id, "request_id", maximum=255)
        price = _minor(per_call_price_minor, "per_call_price_minor", positive=True)
        request_key = self._request_key(ident, agent, request)

        self.config.transaction_lock.acquire()
        release_lock = True
        before = self._transaction_snapshot()
        try:
            prior = self._request_decisions.get(request_key)
            if prior is not None:
                replay = deepcopy(prior)
                replay["idempotent_replay"] = True
                # Its original mutation is already the durable exactly-once
                # decision. A replay must never ask the gate to save/commit it
                # again or consume a second quota unit.
                replay["reservation_token"] = None
                replay["durability_required"] = False
                return replay
            account = self._accounts.get(ident)
            if account is None:
                return self._fallback(account_id=ident, agent_id=agent,
                                      request_id=request, reason="unknown_account")
            candidates = self._local_candidates(ident, agent)
            if not candidates:
                return self._fallback(account_id=ident, agent_id=agent,
                                      request_id=request,
                                      reason="no_covering_subscription")
            try:
                self._refresh_candidates(candidates)
            except Exception as exc:
                self._restore_transaction_snapshot(before)
                self.logger.warning("entitlement pull-verification failed (%s)",
                                    type(exc).__name__)
                return self._fallback(account_id=ident, agent_id=agent,
                                      request_id=request,
                                      reason="entitlement_lookup_error",
                                      lookup_error=True)

            now = self._now()
            active = self._active_matches(ident, agent, now)
            if len(active) != 1:
                # Lifecycle refresh may have changed durable state even though
                # the access decision falls through.  Reserve that state so the
                # gate can save or roll it back atomically.
                reason = ("ambiguous_active_entitlement" if len(active) > 1
                          else "no_active_covering_subscription")
                decision = self._fallback(account_id=ident, agent_id=agent,
                                          request_id=request, reason=reason)
            else:
                sub, period = active[0]
                counter = self._usage[period.period_key]
                self._assert_usage_conservation(period.period_key)
                if counter.included_used < counter.included_limit:
                    counter.included_used += 1
                    path = "included_quota_waiver"
                    overage_minor = 0
                    waive, direct_overage = True, False
                else:
                    counter.overage_calls += 1
                    counter.overage_minor += price
                    path = "overage_meter"
                    overage_minor = price
                    waive, direct_overage = False, True
                counter.last_used_at = _iso(now)
                decision = {
                    "request_id": request, "account_id": ident,
                    "agent_id": agent, "path": path, "entitled": True,
                    "waive_per_call_charge": waive,
                    "should_run_per_call_gate": direct_overage,
                    "bypass_anonymous_freemium": direct_overage,
                    "requires_direct_overage_charge": direct_overage,
                    "overage_minor": overage_minor,
                    "subscription_id": sub.subscription_id,
                    "plan_id": period.plan_id,
                    "period_key": period.period_key,
                    "usage": counter.public(),
                    "reason": "active_verified_subscription",
                    "lookup_error": False,
                    "catalog": self._catalog_ref(
                        version=period.catalog_version,
                        sha256=period.catalog_sha256),
                }
                self._request_decisions[request_key] = deepcopy(decision)
                self._audit("entitlement_reserved", {
                    "request_key": request_key,
                    "subscription_id": sub.subscription_id,
                    "account_id": ident, "agent_id": agent,
                    "path": path, "period_key": period.period_key,
                    "overage_minor": overage_minor,
                    "catalog": decision["catalog"],
                })
                self._assert_usage_conservation(period.period_key)

            changed = before != self._transaction_snapshot()
            if not changed:
                return decision
            token = _digest({"request_key": request_key,
                             "before_sha256": _digest(before),
                             "decision_path": decision["path"]})
            self.config.rollback_journal[token] = before
            decision["reservation_token"] = token
            decision["durability_required"] = True
            if request_key in self._request_decisions:
                self._request_decisions[request_key]["reservation_token"] = token
                self._request_decisions[request_key]["durability_required"] = True
            release_lock = False
            return decision
        except Exception:
            self._restore_transaction_snapshot(before)
            raise
        finally:
            if release_lock:
                self.config.transaction_lock.release()

    def commit_reservation(self, reservation_token: Any) -> bool:
        token = _require_text(reservation_token, "reservation_token", maximum=128)
        if token not in self.config.rollback_journal:
            return False
        self.config.rollback_journal.pop(token, None)
        self.config.transaction_lock.release()
        return True

    def rollback_reservation(self, reservation_token: Any) -> bool:
        token = _require_text(reservation_token, "reservation_token", maximum=128)
        snapshot = self.config.rollback_journal.pop(token, None)
        if snapshot is None:
            return False
        try:
            self._restore_transaction_snapshot(snapshot)
            return True
        finally:
            self.config.transaction_lock.release()

    # Backward-friendly alias for an integration that names the operation as a
    # decision.  It still returns a reservation that MUST be finalized.
    entitlement_decision = reserve_entitlement

    # ------------------------------- status --------------------------------
    def _subscription_public(self, sub: Subscription, now: datetime) -> dict:
        period = self._periods[sub.current_period_key]
        usage = self._usage[sub.current_period_key]
        self._assert_usage_conservation(period.period_key)
        return {
            "subscription_id": sub.subscription_id,
            "account_id": sub.account_id,
            "plan_id": period.plan_id,
            "status": self._effective_status(period, now),
            "stripe_status": period.stripe_status,
            "current_period_start": period.current_period_start,
            "current_period_end": period.current_period_end,
            "included_calls": period.included_calls,
            "used_calls": usage.included_used + usage.overage_calls,
            "included_used": usage.included_used,
            "overage_calls": usage.overage_calls,
            "overage_minor": usage.overage_minor,
            "activation_state": (
                "used" if usage.included_used + usage.overage_calls > 0
                else "unused"),
            "last_value_at": getattr(usage, "last_used_at", None),
            "renewal_state": self._renewal_state(period, now),
            "covered_agents": list(period.covered_agents),
            "catalog": self._catalog_ref(version=period.catalog_version,
                                           sha256=period.catalog_sha256),
            "livemode": period.livemode,
        }

    def retention_summary(self) -> dict:
        """Return aggregate seat activation and renewal risk without IDs."""
        with self.config.transaction_lock:
            now = self._now()
            activation = {"active_used": 0, "active_unused": 0,
                          "active_unused_over_7d": 0,
                          "active_used_last_value_unknown": 0}
            renewal = {
                "healthy": 0,
                "due_within_7d": 0,
                "failed": 0,
                "canceled": 0,
                "expired": 0,
            }
            last_values: List[str] = []
            for sub in self._subscriptions.values():
                period = self._periods.get(sub.current_period_key)
                usage = self._usage.get(sub.current_period_key)
                if period is None or usage is None:
                    raise ConservationError(
                        "subscription retention state is incomplete")
                self._assert_usage_conservation(period.period_key)
                effective = self._effective_status(period, now)
                renewal_state = self._renewal_state(period, now)
                renewal[renewal_state] += 1
                used = usage.included_used + usage.overage_calls
                last_value = getattr(usage, "last_used_at", None)
                if last_value is not None:
                    _instant(last_value, "last_used_at")
                    last_values.append(last_value)
                if effective == "active":
                    bucket = "active_used" if used > 0 else "active_unused"
                    activation[bucket] += 1
                    if used > 0 and last_value is None:
                        activation["active_used_last_value_unknown"] += 1
                    if used == 0:
                        activated_at = _instant(
                            period.activated_at, "activated_at")
                        if (now - activated_at).total_seconds() >= 604800:
                            activation["active_unused_over_7d"] += 1
            active_total = activation["active_used"] + activation[
                "active_unused"]
            mrr = self.mrr_summary()
            if active_total != mrr["active_subscriptions"]:
                raise ConservationError(
                    "retention active count disagrees with MRR")
            if sum(renewal.values()) != len(self._subscriptions):
                raise ConservationError(
                    "retention renewal count does not conserve subscriptions")
            return {
                "schema": "seat-retention-v1",
                "subscriptions": len(self._subscriptions),
                "active_subscriptions": active_total,
                "activation": activation,
                "renewal": renewal,
                "last_value_at": max(last_values) if last_values else None,
                "last_value_status": (
                    "historical_gaps_present"
                    if activation["active_used_last_value_unknown"] > 0
                    else "complete_for_observed_usage"),
                "paid_not_activated": 0,
                "paid_not_activated_status":
                    "unavailable_without_provider_checkout_reconciliation",
                "classification":
                    "aggregate_subscription_ledger_not_customer_outreach",
            }

    def provider_activation_reconciliation(
        self,
        evidence: Any,
        *,
        observed_at: Any,
        created_after_epoch: Any,
        pages: Any,
    ) -> dict:
        """Join read-only Stripe Checkout evidence to the local ledger.

        Session and subscription identifiers are consumed only for the join
        and are never returned. This method has no state mutation path.
        """
        require_evidence = isinstance(evidence, list)
        if not require_evidence:
            raise ValidationError(
                "provider evidence must be a list",
                "evidence", type(evidence).__name__, "list",
            )
        observed = _instant(observed_at, "observed_at")
        if (not isinstance(created_after_epoch, int)
                or isinstance(created_after_epoch, bool)
                or created_after_epoch < 0):
            raise ValidationError(
                "created_after_epoch must be a unix timestamp",
                "created_after_epoch", created_after_epoch,
                "non-negative integer",
            )
        if (not isinstance(pages, int) or isinstance(pages, bool)
                or pages <= 0):
            raise ValidationError(
                "pages must be a positive integer",
                "pages", pages, "positive integer",
            )
        window_start = datetime.fromtimestamp(
            created_after_epoch, tz=timezone.utc)
        if window_start > observed:
            raise ValidationError(
                "reconciliation window starts after observation",
                "created_after_epoch", created_after_epoch,
                "at or before observed_at",
            )
        seen_sessions = set()
        provider_subscription_ids = set()
        counts = {
            "provider_sessions": 0,
            "live_sessions": 0,
            "test_sessions_excluded": 0,
            "complete_paid": 0,
            "activated": 0,
            "paid_not_activated": 0,
            "open_unpaid": 0,
            "expired_unpaid": 0,
            "payment_pending": 0,
            "provider_anomalies": 0,
        }
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                raise ValidationError(
                    "provider evidence item must be an object",
                    f"evidence[{index}]", type(item).__name__, "object",
                )
            session_id = _require_text(
                item.get("session_id"), f"evidence[{index}].session_id",
                maximum=255)
            if (not session_id.startswith("cs_")
                    or session_id in seen_sessions):
                raise VerificationError(
                    "provider evidence has invalid or duplicate Session")
            seen_sessions.add(session_id)
            subscription_id = item.get("subscription_id")
            if subscription_id is not None:
                subscription_id = _require_text(
                    subscription_id,
                    f"evidence[{index}].subscription_id",
                    maximum=255,
                )
                if not _SUBSCRIPTION_ID_RE.fullmatch(subscription_id):
                    raise VerificationError(
                        "provider evidence has invalid subscription id")
                provider_subscription_ids.add(subscription_id)
            checkout_status = item.get("checkout_status")
            payment_status = item.get("payment_status")
            if checkout_status not in {"open", "complete", "expired"}:
                raise VerificationError(
                    "provider evidence has invalid Checkout status")
            if payment_status not in {
                    "paid", "unpaid", "no_payment_required"}:
                raise VerificationError(
                    "provider evidence has invalid payment status")
            created = item.get("created")
            if (not isinstance(created, int) or isinstance(created, bool)
                    or created < created_after_epoch
                    or created > int(observed.timestamp()) + 60):
                raise VerificationError(
                    "provider evidence timestamp is outside the window")
            if not isinstance(item.get("livemode"), bool):
                raise VerificationError(
                    "provider evidence is missing livemode")
            counts["provider_sessions"] += 1
            if item["livemode"] is not True:
                counts["test_sessions_excluded"] += 1
                continue
            counts["live_sessions"] += 1
            if checkout_status == "complete" and payment_status == "paid":
                if subscription_id is None:
                    raise VerificationError(
                        "paid Checkout has no subscription id")
                counts["complete_paid"] += 1
                if subscription_id in self._subscriptions:
                    counts["activated"] += 1
                else:
                    counts["paid_not_activated"] += 1
            elif checkout_status == "open" and payment_status == "unpaid":
                counts["open_unpaid"] += 1
            elif checkout_status == "expired" and payment_status == "unpaid":
                counts["expired_unpaid"] += 1
            elif checkout_status == "complete" and payment_status == "unpaid":
                counts["payment_pending"] += 1
            else:
                counts["provider_anomalies"] += 1
        if (counts["activated"] + counts["paid_not_activated"]
                != counts["complete_paid"]):
            raise ConservationError(
                "provider paid activation reconciliation does not conserve")
        return {
            "schema": "seat-provider-activation-reconciliation-v1",
            **counts,
            "ledger_subscriptions": len(self._subscriptions),
            "ledger_subscriptions_observed_in_window":
                len(set(self._subscriptions) & provider_subscription_ids),
            "ledger_subscriptions_without_window_session":
                len(set(self._subscriptions) - provider_subscription_ids),
            "observed_at": _iso(observed),
            "created_after_epoch": created_after_epoch,
            "pages": pages,
            "coverage": "bounded_complete",
            "paid_not_activated_status": "available_provider_reconciled",
            "provider_mutation": False,
            "customer_action_authorized": False,
            "identifiers_returned": 0,
        }

    def subscription_status(self, account_id: Any, account_key: Any) -> dict:
        with self.config.transaction_lock:
            account = self._authorize(account_id, account_key)
            now = self._now()
            subscriptions = [self._subscription_public(sub, now)
                             for sub in self._subscriptions.values()
                             if sub.account_id == account.account_id]
            subscriptions.sort(key=lambda item: item["subscription_id"])
            return {**account.public(), "count": len(subscriptions),
                    "subscriptions": subscriptions,
                    "past_due_grace": "none"}

    def usage_summary(self, account_id: Any, account_key: Any) -> dict:
        with self.config.transaction_lock:
            account = self._authorize(account_id, account_key)
            periods = []
            for key in sorted(self._usage):
                counter = self._usage[key]
                if counter.account_id != account.account_id:
                    continue
                self._assert_usage_conservation(key)
                period = self._periods[key]
                periods.append({**counter.public(),
                                "current_period_start": period.current_period_start,
                                "current_period_end": period.current_period_end,
                                "catalog": self._catalog_ref(
                                    version=period.catalog_version,
                                    sha256=period.catalog_sha256)})
            totals = {
                "included_used": sum(item["included_used"] for item in periods),
                "overage_calls": sum(item["overage_calls"] for item in periods),
                "overage_minor": sum(item["overage_minor"] for item in periods),
                "used_calls": sum(item["used_calls"] for item in periods),
            }
            if totals["used_calls"] != (totals["included_used"] +
                                         totals["overage_calls"]):
                raise ConservationError("account usage conservation failed")
            self._assert_audit_chain()
            auditable = {"account_id": account.account_id, "periods": periods,
                         "totals": totals}
            return {**auditable, "audit_sha256": _digest(auditable),
                    "audit_event_count": len(self._audit_events)}

    def customer_portal_link(self, account_id: Any, account_key: Any) -> dict:
        with self.config.transaction_lock:
            account = self._authorize(account_id, account_key)
            if self.config.stripe_provider is None:
                raise ConfigurationError("Stripe billing portal provider is unavailable")
            customer_id = account.stripe_customer_id
            if not customer_id:
                raise ConfigurationError("account has no verified Stripe customer")
            try:
                response = self.config.stripe_provider.create_customer_portal(
                    customer_id=customer_id, account_id=account.account_id)
            except Exception as exc:
                self.logger.warning("Stripe-hosted portal link creation failed (%s)",
                                    type(exc).__name__)
                raise VerificationError("Stripe-hosted billing portal is unavailable")
            if not isinstance(response, dict):
                raise VerificationError("portal provider returned an invalid response")
            if response.get("status") != "ok":
                raise VerificationError("Stripe-hosted billing portal is unavailable")
            if (not isinstance(response.get("livemode"), bool) or
                    response.get("livemode") is not self.config.stripe_livemode_expected):
                raise VerificationError("Stripe Portal live/test mode mismatch")
            url = self._hosted_url(response.get("url"), "billing.stripe.com", "url")
            return {"account_id": account.account_id, "portal_url": url,
                    "money_movement": "human_managed_on_stripe"}

    def mrr_summary(self) -> dict:
        """Aggregate-only capital KPI; never exposes account/Stripe ids."""
        with self.config.transaction_lock:
            now = self._now()
            active_periods = []
            for sub in self._subscriptions.values():
                period = self._periods[sub.current_period_key]
                if self._effective_status(period, now) == "active":
                    if period.livemode:
                        active_periods.append(period)
            plan_mix: Dict[str, dict] = {}
            for period in active_periods:
                item = plan_mix.setdefault(period.plan_id,
                                           {"active_subscriptions": 0,
                                            "mrr_minor": 0})
                item["active_subscriptions"] += 1
                item["mrr_minor"] += period.plan_price_minor
            return {"active_subscriptions": len(active_periods),
                    "mrr_minor": sum(p.plan_price_minor for p in active_periods),
                    "currency": self.catalog["currency"],
                    "plan_mix": {key: plan_mix[key] for key in sorted(plan_mix)},
                    "catalog": self._catalog_ref()}

    # ------------------------------ invariants ------------------------------
    def _assert_usage_conservation(self, period_key: str) -> None:
        counter = self._usage.get(period_key)
        if counter is None:
            raise ConservationError("period has no usage counter")
        if min(counter.included_limit, counter.included_used,
               counter.overage_calls, counter.overage_minor) < 0:
            raise ConservationError("usage counters cannot be negative")
        if counter.included_used > counter.included_limit:
            raise ConservationError("included usage exceeds included quota")
        decisions = [value for value in self._request_decisions.values()
                     if value.get("period_key") == period_key]
        included = sum(1 for d in decisions
                       if d.get("path") == "included_quota_waiver")
        overage = [d for d in decisions if d.get("path") == "overage_meter"]
        if included != counter.included_used:
            raise ConservationError("included usage/decision drift")
        if len(overage) != counter.overage_calls:
            raise ConservationError("overage call/decision drift")
        if sum(_minor(d.get("overage_minor"), "overage_minor")
               for d in overage) != counter.overage_minor:
            raise ConservationError("overage amount/decision drift")

    def _assert_audit_chain(self) -> None:
        previous = "0" * 64
        for sequence, event in enumerate(self._audit_events, 1):
            body = {key: deepcopy(value) for key, value in event.items()
                    if key != "event_sha256"}
            if body.get("sequence") != sequence:
                raise ConservationError("audit sequence drift")
            if body.get("previous_event_sha256") != previous:
                raise ConservationError("audit predecessor drift")
            if not hmac.compare_digest(str(event.get("event_sha256", "")),
                                       _digest(body)):
                raise ConservationError("audit digest drift")
            previous = event["event_sha256"]

    # ---------------------------- fleet contract ----------------------------
    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                raise ValidationError("input must be an object", "input",
                                      type(input_data).__name__, "object")
            action = input_data.get("action")
            handlers = {
                "list_plans": lambda: self.list_plans(),
                "get_plan": lambda: self.get_plan(input_data.get("plan_id")),
                "create_account": lambda: self.create_account(
                    input_data.get("account_ref")),
                "create_checkout_link": lambda: self.create_checkout_link(
                    input_data.get("plan_id"), input_data.get("account_ref"),
                    input_data.get("acquisition_source")),
                "record_subscription": lambda: self.record_subscription(
                    input_data.get("stripe_reference")),
                "subscription_status": lambda: self.subscription_status(
                    input_data.get("account_id"), input_data.get("account_key")),
                "usage_summary": lambda: self.usage_summary(
                    input_data.get("account_id"), input_data.get("account_key")),
                "customer_portal_link": lambda: self.customer_portal_link(
                    input_data.get("account_id"), input_data.get("account_key")),
                "mrr_summary": lambda: self.mrr_summary(),
                "retention_summary": lambda: self.retention_summary(),
                # Gateway-internal funnel actions.  They are deliberately not
                # registered as public MCP tools by the thin adapter.
                "record_frontdoor_view": lambda: self.record_frontdoor_view(
                    input_data.get("source")),
                "record_snapshot_view": lambda: self.record_snapshot_view(),
                "record_snapshot_checkout_started":
                    lambda: self.record_snapshot_checkout_started(),
                "record_snapshot_paid": lambda: self.record_snapshot_paid(
                    input_data.get("stripe_reference")),
                "record_acquisition_view":
                    lambda: self.record_acquisition_view(
                        input_data.get("surface"), input_data.get("source")),
                "frontdoor_summary": lambda: self.frontdoor_summary(),
            }
            handler = handlers.get(action)
            if handler is None:
                raise ValidationError("unknown action", "action", action,
                                      "one of: " + ", ".join(sorted(handlers)))
            return self._ok(handler())
        except ValidationError as exc:
            return self._err(str(exc), error_type="ValidationError",
                             field=exc.field, value=exc.value,
                             constraint=exc.constraint)
        except ConfigurationError as exc:
            return self._err(str(exc), error_type="configuration_required")
        except VerificationError as exc:
            return self._err(str(exc), error_type="VerificationError")
        except DurabilityError as exc:
            result = self._err(str(exc), error_type="DurabilityError")
            result.update({"entitled": False,
                           "account_key_issued_once": False})
            return result
        except ConservationError as exc:
            self.logger.critical("subscriptions conservation failure")
            return self._err(str(exc), error_type="ConservationError")
        except Exception as exc:
            self.logger.exception("subscriptions process failed")
            return self._err(f"internal error: {type(exc).__name__}",
                             error_type="RuntimeError")

    def describe(self) -> dict:
        return {
            "name": self.config.name, "version": self.config.version,
            "description": ("Deterministic account, verified monthly-seat, "
                            "quota, overage, and MRR infrastructure."),
            "capabilities": ["list_plans", "get_plan", "create_account",
                             "create_checkout_link", "record_subscription",
                             "subscription_status", "customer_portal_link",
                             "usage_summary", "mrr_summary",
                             "retention_summary"],
            "security": {"account_auth": "bearer account_key",
                         "stored_key": "sha256 + last4 only",
                         "stripe_secret_handling": "none",
                         "money_movement": "Stripe-hosted human action only"},
            "entitlement": {"past_due_grace": "none",
                            "period": "[current_period_start,current_period_end)",
                            "error_path": "existing per-call freemium"},
            "plan_catalog": {"version": self.catalog["pack_version"],
                             "sha256": self.catalog_sha256},
            "a2a_role": "subscription-entitlement-infrastructure",
        }

    async def health(self) -> dict:
        mrr = self.mrr_summary()
        frontdoor = self.frontdoor_summary()
        retention = self.retention_summary()
        configured = sum(1 for plan in self.plans.values()
                         if self._checkout_configuration_error(plan) is None)
        return {"status": "ok", "agent": self.config.name,
                "version": self.config.version, "timestamp": _iso(self._now()),
                "retention_summary": retention,
                "checks": {
                    "accounts": len(self._accounts),
                    "subscriptions": len(self._subscriptions),
                    "active_subscriptions": mrr["active_subscriptions"],
                    "mrr_minor": mrr["mrr_minor"],
                    "plan_mix": mrr["plan_mix"],
                    "page_views": frontdoor["page_views"],
                    "checkouts_started": frontdoor["checkouts_started"],
                    "snapshot_page_views":
                        frontdoor["snapshot_page_views"],
                    "snapshot_checkouts_started":
                        frontdoor["snapshot_checkouts_started"],
                    "snapshot_paid": frontdoor["snapshot_paid"],
                    "landing_page_views": frontdoor["landing_page_views"],
                    "acquisition_surface_views":
                        frontdoor["acquisition_surface_views"],
                    "acquisition_source_views":
                        frontdoor["acquisition_source_views"],
                    "acquisition_classification":
                        frontdoor["acquisition_classification"],
                    "seat_source_views": frontdoor["seat_source_views"],
                    "seat_attributed_views":
                        frontdoor["seat_attributed_views"],
                    "seat_unattributed_views":
                        frontdoor["seat_unattributed_views"],
                    "seat_acquisition_classification":
                        frontdoor["seat_acquisition_classification"],
                    "plan_catalog_version": self.catalog["pack_version"],
                    "plan_catalog_sha256": self.catalog_sha256,
                    "checkout_ready_plans": configured,
                    "stripe_provider_attached": self.config.stripe_provider is not None,
                    "durable_activation_commit_attached":
                        self.config.durable_activation_commit is not None,
                }}


def build(config: Optional[AgentConfig] = None) -> SubscriptionsCore:
    return SubscriptionsCore(config)
