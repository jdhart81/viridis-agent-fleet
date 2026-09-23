"""
agent-metering-agent — Core business logic.

Usage metering + SLA accounting for agent services: the "meter" behind the
x402 / HTTP-402 micropayment idiom proven in Energy AI. When agents hire
agents, someone must count the work honestly. This agent meters usage events,
freezes deterministic invoices, and reports SLA compliance — the layer that
tells agent-escrow-agent *how much* to settle and agent-trust-oracle-agent
*whether the provider kept its promises*.

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input — it returns a
structured error envelope.

--- INVARIANTS (spec-invariance contract) ---
M1  The meter is append-only: recorded usage events are immutable — no edit or
    delete action exists; event count is monotone non-decreasing.
M2  Every usage event requires a positive, finite numeric quantity; the unit
    is fixed per meter at creation and a mismatched unit is rejected.
M3  Deterministic billing: amount_minor = ceil(total_quantity *
    price_minor_per_unit). Integer minor units only; the same events always
    produce the same invoice.
M4  Idempotency on event_id (the x402 toolCallId idiom): re-recording a seen
    event_id is a no-op that returns the original event — never double-billed.
M5  Tamper-evident event chain: each event commits to the previous event's
    hash; verify_chain detects any mutation.
M6  SLA accounting is pure: sla_report computes success_rate = ok_events /
    total_events, flags breach iff success_rate < sla_target, and never
    mutates state.
M7  close_period is exactly-once per billing period: it freezes all open
    events into an immutable invoice; closing again with no new events
    returns the existing invoice (idempotent, no empty invoices).
M8  Unknown meter_id / event_id -> error envelope, never a crash.

--- GRANULARITY INVARIANTS (usage-statistics contract, v0.2.0) ---
G1  Aggregate identity: for every meter that existed before v0.2.0,
    usage_summary output (event_count, total_quantity, ok/error counts,
    accrued_minor) is bit-identical before and after the upgrade.
G2  Chain preservation: no historical event is ever mutated; every meter
    with a valid hash chain before the upgrade remains valid after, and a
    chain may contain pre-v0.2.0 events followed by enriched events.
G3  Idempotency preserved: M4 dedup on event_id is unaffected by the new
    fields; a duplicate with different consumer_class/metadata still
    returns the original event.
G4  Signature compatibility: every pre-existing action keeps its exact
    semantics; all new inputs are optional with defaults that reproduce
    pre-v0.2.0 behavior.
G5  Snapshot forward-compat: a Meter restored from a pre-v0.2.0 pickle
    snapshot (gateway StateStore) materializes the new attributes with
    safe defaults (origin="legacy", is_test=False) via __setstate__ and
    serves every tool correctly.
G6  Trusted classification: consumer_class in {internal, external,
    unknown} plus channel/caller are event-level fields supplied by a
    trusted writer (the gateway, via the reserved "_origin" input key).
    The public MCP adapter never exposes these inputs, so a public caller
    cannot spoof internal traffic. Meters with origin="gateway" are
    write-protected: record_usage without _origin="gateway" is refused
    (meters with origin legacy/public remain writable as before).
G7  Test-flag hygiene: events flagged is_test (or on meters flagged
    is_test) are excluded from list_events/usage_timeseries by default and
    included only with include_test=true. Billing aggregates
    (usage_summary, close_period) NEVER change because of the flag.
G8  Event readability: list_events is read-only, cursor-paginated with a
    stable order (meter_id, event index), and filterable by meter,
    provider, date range, consumer_class, channel, outcome, and test flag.
G9  Real time-series: usage_timeseries buckets on each event's
    recorded_at (UTC; bucket=day|hour), never on meter created_at, and
    aggregates across the daily-meter fragmentation by grouping on
    provider. Monetary values in the series are labelled estimates
    (est_accrued_minor); authoritative money remains usage_summary /
    close_period (M3).
G10 flag_meter is the only post-hoc annotation and touches meter-level
    metadata only (is_test, flag_note) — never events, never the chain,
    never accrual. It requires the VIRIDIS_ADMIN_TOKEN env secret;
    unset token => flagging refused.
"""

import hashlib
import hmac
import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Fleet-standard base (self-contained; each agent runs in its own PYTHONPATH)
# --------------------------------------------------------------------------- #
@dataclass
class AgentConfig:
    name: str
    version: str = "0.2.0"
    debug: bool = False


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentCore:
    """Minimal fleet-standard base. Subclasses override process()/describe()."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(config.name)
        self.logger.setLevel(logging.DEBUG if config.debug else logging.INFO)

    async def process(self, input_data: dict) -> dict:
        raise NotImplementedError

    async def health(self) -> dict:
        return {
            "status": "ok",
            "agent": self.config.name,
            "version": self.config.version,
            "timestamp": _utcnow(),
            "checks": {},
        }

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "override me",
            "capabilities": [],
            "inputs": {},
            "outputs": {},
        }

    # -- helpers -----------------------------------------------------------
    def _err(self, message: str, *, error_type: str = "Error",
             field: str = "", value: Any = None, constraint: str = "") -> dict:
        return {
            "status": "error",
            "error_type": error_type,
            "field": field,
            "value": value,
            "constraint": constraint,
            "message": message,
            "timestamp": _utcnow(),
        }

    def _ok(self, data: Any = None) -> dict:
        return {"status": "ok", "data": data, "error": None, "timestamp": _utcnow()}


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


# --------------------------------------------------------------------------- #
# Domain
# --------------------------------------------------------------------------- #
_GENESIS = "0" * 64

# G6 vocabulary. consumer_class is a closed set; channel is open-vocabulary
# (derived at the gateway from transport evidence) but always a short string.
CONSUMER_CLASSES = frozenset({"internal", "external", "unknown"})
# Meter origins: "gateway" = created by the fleet's own payment gate
# (billing-critical, write-protected per G6); "public" = created through the
# public create_meter tool; "legacy" = existed before v0.2.0 (unknown origin,
# stays writable for compatibility).
METER_ORIGINS = frozenset({"gateway", "public", "legacy"})

# G5: attributes added after v0.1.x, with the defaults a restored pre-v0.2.0
# pickle must materialize. Single source of truth for Meter.__setstate__.
_METER_COMPAT_DEFAULTS = {
    "origin": "legacy",
    "is_test": False,
    "flag_note": "",
}


def _hash(payload: dict, prev: str) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + body).encode()).hexdigest()


@dataclass
class Meter:
    meter_id: str
    provider: str
    consumer: str
    unit: str
    price_minor_per_unit: float
    currency: str = "USD"
    sla_target: float = 0.99
    created_at: str = field(default_factory=_utcnow)
    events: List[dict] = field(default_factory=list)
    event_ids: Dict[str, int] = field(default_factory=dict)
    invoices: List[dict] = field(default_factory=list)
    closed_upto: int = 0  # events[:closed_upto] are invoiced (M7)
    # --- v0.2.0 (keep _METER_COMPAT_DEFAULTS in sync) ---
    origin: str = "public"          # G6: "gateway" set only via _origin key
    is_test: bool = False           # G7/G10: stats-exclusion flag
    flag_note: str = ""             # G10: audit note for the flag

    def __setstate__(self, state: dict) -> None:
        """G5: restore pre-v0.2.0 pickles — missing attributes get safe
        defaults, so a StateStore snapshot written by v0.1.x keeps working."""
        merged = dict(_METER_COMPAT_DEFAULTS)
        merged.update(state)
        self.__dict__.update(merged)

    def public(self) -> dict:
        return {
            "meter_id": self.meter_id, "provider": self.provider,
            "consumer": self.consumer, "unit": self.unit,
            "price_minor_per_unit": self.price_minor_per_unit,
            "currency": self.currency, "sla_target": self.sla_target,
            "created_at": self.created_at, "event_count": len(self.events),
            "invoice_count": len(self.invoices),
            "origin": self.origin, "is_test": self.is_test,
        }


class MeteringAgentCore(AgentCore):
    """Usage metering + SLA accounting for A2A services."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-metering-agent"))
        self._meters: Dict[str, Meter] = {}
        self._seq = 0

    # ------------------------------------------------------------------ #
    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object", error_type="ValidationError",
                                 field="input", value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "create_meter": self._create_meter,
                "record_usage": self._record_usage,
                "usage_summary": self._usage_summary,
                "sla_report": self._sla_report,
                "close_period": self._close_period,
                "verify_chain": self._verify_chain,
                "list_meters": self._list_meters,
                "list_events": self._list_events,
                "usage_timeseries": self._usage_timeseries,
                "flag_meter": self._flag_meter,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'", error_type="ValidationError",
                                 field="action", value=action,
                                 constraint="one of: create_meter, record_usage, usage_summary, "
                                            "sla_report, close_period, verify_chain, list_meters, "
                                            "list_events, usage_timeseries, flag_meter")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError", field=e.field,
                             value=e.value, constraint=e.constraint)
        except Exception as e:  # noqa: BLE001
            self.logger.exception("metering process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ------------------------------------------------------------------ #
    def _get_meter(self, data: dict) -> Meter:
        mid = data.get("meter_id")
        meter = self._meters.get(mid)
        if meter is None:  # M8
            raise ValidationError("unknown meter", field="meter_id", value=mid,
                                  constraint="must exist")
        return meter

    def _create_meter(self, data: dict) -> dict:
        for f in ("provider", "consumer", "unit"):
            if not data.get(f) or not isinstance(data.get(f), str):
                raise ValidationError(f"missing '{f}'", field=f, constraint="non-empty str")
        price = data.get("price_minor_per_unit")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0 or not math.isfinite(price):
            raise ValidationError("price_minor_per_unit must be a non-negative finite number",
                                  field="price_minor_per_unit", value=price, constraint=">= 0, finite")
        sla = float(data.get("sla_target", 0.99))
        if not 0.0 <= sla <= 1.0:
            raise ValidationError("sla_target must be in [0,1]", field="sla_target",
                                  value=sla, constraint="0 <= sla <= 1")
        # G6: origin is trust-derived, never caller-chosen. Only the reserved
        # "_origin" key (which the public MCP adapter does not expose) can mark
        # a meter as gateway-owned; everything else is "public".
        origin = "gateway" if data.get("_origin") == "gateway" else "public"
        self._seq += 1
        mid = f"mtr-{self._seq:06d}"
        meter = Meter(meter_id=mid, provider=data["provider"], consumer=data["consumer"],
                      unit=data["unit"], price_minor_per_unit=float(price),
                      currency=data.get("currency", "USD"), sla_target=sla,
                      origin=origin, is_test=bool(data.get("is_test", False)))
        self._meters[mid] = meter
        return self._ok(meter.public())

    def _record_usage(self, data: dict) -> dict:
        meter = self._get_meter(data)
        # G6: gateway-owned billing meters are write-protected. Meter IDs are
        # public (list_meters), so without this any caller could inflate
        # accrued totals on a real billing meter. Legacy/public meters keep
        # their pre-v0.2.0 behavior (G4).
        if meter.origin == "gateway" and data.get("_origin") != "gateway":
            raise ValidationError(
                "meter is gateway-owned and write-protected; create your own "
                "meter with create_meter to record usage",
                field="meter_id", value=meter.meter_id,
                constraint="origin must not be 'gateway' for public writes")
        event_id = data.get("event_id")
        if not event_id or not isinstance(event_id, str):
            raise ValidationError("missing 'event_id'", field="event_id", constraint="non-empty str")
        if event_id in meter.event_ids:  # M4 idempotent (G3: fields ignored)
            return self._ok({**meter.events[meter.event_ids[event_id]], "duplicate": True})
        qty = data.get("quantity")
        if not isinstance(qty, (int, float)) or isinstance(qty, bool) or qty <= 0 or not math.isfinite(qty):
            raise ValidationError("quantity must be a positive finite number",  # M2
                                  field="quantity", value=qty, constraint="> 0, finite")
        unit = data.get("unit", meter.unit)
        if unit != meter.unit:  # M2 unit fixed per meter
            raise ValidationError("unit mismatch with meter", field="unit", value=unit,
                                  constraint=f"must be '{meter.unit}'")
        outcome = data.get("outcome", "ok")
        if outcome not in ("ok", "error"):
            raise ValidationError("outcome must be 'ok' or 'error'", field="outcome",
                                  value=outcome, constraint="ok|error")
        # G6: trusted classification fields. The public adapter never exposes
        # these inputs; the gateway supplies them from transport evidence.
        consumer_class = data.get("consumer_class", "unknown")
        if consumer_class not in CONSUMER_CLASSES:
            raise ValidationError("invalid consumer_class", field="consumer_class",
                                  value=consumer_class,
                                  constraint="internal|external|unknown")
        channel = data.get("channel", "unknown")
        if not isinstance(channel, str) or not channel or len(channel) > 64:
            raise ValidationError("channel must be a short non-empty string",
                                  field="channel", value=channel,
                                  constraint="str, 1..64 chars")
        caller = data.get("caller")
        if caller is not None and (not isinstance(caller, str) or len(caller) > 128):
            raise ValidationError("caller must be a string (<=128 chars) or absent",
                                  field="caller", value=caller,
                                  constraint="str <= 128 chars | null")
        prev = meter.events[-1]["entry_hash"] if meter.events else _GENESIS
        body = {
            "event_id": event_id, "meter_id": meter.meter_id, "quantity": float(qty),
            "unit": meter.unit, "outcome": outcome,
            "metadata": data.get("metadata", {}), "recorded_at": _utcnow(),
            "prev_hash": prev,
            # v0.2.0 enrichment (absent on pre-upgrade events; readers use
            # .get() with unknown/False defaults — G2 chains stay valid).
            "consumer_class": consumer_class,
            "channel": channel,
            "caller": caller,
            "is_test": bool(data.get("is_test", False)),
        }
        event = {**body, "entry_hash": _hash(body, prev)}  # M5
        meter.events.append(event)  # M1 append-only
        meter.event_ids[event_id] = len(meter.events) - 1
        return self._ok({**event, "duplicate": False})

    def _usage_summary(self, data: dict) -> dict:
        meter = self._get_meter(data)
        total_qty = sum(e["quantity"] for e in meter.events)
        ok_events = sum(1 for e in meter.events if e["outcome"] == "ok")
        return self._ok({
            "meter_id": meter.meter_id, "unit": meter.unit,
            "event_count": len(meter.events), "total_quantity": total_qty,
            "ok_events": ok_events, "error_events": len(meter.events) - ok_events,
            "open_events": len(meter.events) - meter.closed_upto,
            "accrued_minor": math.ceil(total_qty * meter.price_minor_per_unit),  # M3
            "currency": meter.currency,
        })

    def _sla_report(self, data: dict) -> dict:  # M6 pure
        meter = self._get_meter(data)
        total = len(meter.events)
        ok_events = sum(1 for e in meter.events if e["outcome"] == "ok")
        success_rate = (ok_events / total) if total else 1.0
        return self._ok({
            "meter_id": meter.meter_id, "sla_target": meter.sla_target,
            "total_events": total, "ok_events": ok_events,
            "success_rate": success_rate,
            "breach": success_rate < meter.sla_target,
        })

    def _close_period(self, data: dict) -> dict:  # M7 exactly-once
        meter = self._get_meter(data)
        if meter.origin == "gateway" and data.get("_origin") != "gateway":  # G6
            raise ValidationError(
                "meter is gateway-owned; its billing periods are closed by "
                "the gateway's daily rollover, not by public callers",
                field="meter_id", value=meter.meter_id,
                constraint="origin must not be 'gateway' for public close")
        open_events = meter.events[meter.closed_upto:]
        if not open_events:
            if meter.invoices:
                return self._ok({**meter.invoices[-1], "duplicate": True})
            raise ValidationError("nothing to invoice: no usage recorded", field="meter_id",
                                  value=meter.meter_id, constraint="at least one open event")
        qty = sum(e["quantity"] for e in open_events)
        body = {
            "meter_id": meter.meter_id, "period_index": len(meter.invoices),
            "event_count": len(open_events),
            "first_event": open_events[0]["event_id"],
            "last_event": open_events[-1]["event_id"],
            "total_quantity": qty, "unit": meter.unit,
            "price_minor_per_unit": meter.price_minor_per_unit,
            "amount_minor": math.ceil(qty * meter.price_minor_per_unit),  # M3
            "currency": meter.currency, "closed_at": _utcnow(),
        }
        invoice_id = hashlib.sha256(json.dumps(
            {k: body[k] for k in ("meter_id", "period_index", "first_event", "last_event",
                                  "total_quantity", "amount_minor")},
            sort_keys=True).encode()).hexdigest()[:16]
        invoice = {"invoice_id": f"inv-{invoice_id}", **body, "duplicate": False}
        meter.invoices.append(invoice)
        meter.closed_upto = len(meter.events)
        return self._ok(invoice)

    def _verify_chain(self, data: dict) -> dict:  # M5
        meter = self._get_meter(data)
        prev = _GENESIS
        for i, e in enumerate(meter.events):
            body = {k: v for k, v in e.items() if k != "entry_hash"}
            if e["prev_hash"] != prev or _hash(body, prev) != e["entry_hash"]:
                return self._ok({"meter_id": meter.meter_id, "valid": False,
                                 "broken_at_index": i})
            prev = e["entry_hash"]
        return self._ok({"meter_id": meter.meter_id, "valid": True,
                         "event_count": len(meter.events)})

    def _list_meters(self, data: dict) -> dict:
        items = [m.public() for m in self._meters.values()]
        return self._ok({"count": len(items), "meters": items})

    # ------------------------------------------------------------------ #
    # v0.2.0 read surface (G7/G8/G9) + admin flagging (G10)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_ts(value: Any, fieldname: str) -> Optional[datetime]:
        if value is None:
            return None
        try:
            dt = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            raise ValidationError(f"'{fieldname}' must be ISO-8601",
                                  field=fieldname, value=value,
                                  constraint="ISO-8601 datetime or date")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _iter_filtered(self, data: dict):
        """Shared filter pipeline for list_events / usage_timeseries (G7/G8).

        Yields (meter, event, event_index) in stable order: meters sorted by
        meter_id, events in chain order. Pre-v0.2.0 events read via .get()
        with unknown/False defaults (G2/G4)."""
        meter_id = data.get("meter_id")
        provider = data.get("provider")
        consumer_class = data.get("consumer_class")
        if consumer_class is not None and consumer_class not in CONSUMER_CLASSES:
            raise ValidationError("invalid consumer_class filter",
                                  field="consumer_class", value=consumer_class,
                                  constraint="internal|external|unknown")
        channel = data.get("channel")
        outcome = data.get("outcome")
        if outcome not in (None, "ok", "error"):
            raise ValidationError("invalid outcome filter", field="outcome",
                                  value=outcome, constraint="ok|error")
        include_test = bool(data.get("include_test", False))
        since = self._parse_ts(data.get("since"), "since")
        until = self._parse_ts(data.get("until"), "until")
        if meter_id is not None and meter_id not in self._meters:  # M8
            raise ValidationError("unknown meter", field="meter_id",
                                  value=meter_id, constraint="must exist")
        meters = ([self._meters[meter_id]] if meter_id
                  else sorted(self._meters.values(), key=lambda m: m.meter_id))
        for meter in meters:
            if provider and meter.provider != provider:
                continue
            if not include_test and meter.is_test:  # G7 meter-level flag
                continue
            for idx, e in enumerate(meter.events):
                if not include_test and e.get("is_test", False):  # G7
                    continue
                if consumer_class and e.get("consumer_class", "unknown") != consumer_class:
                    continue
                if channel and e.get("channel", "unknown") != channel:
                    continue
                if outcome and e["outcome"] != outcome:
                    continue
                if since or until:
                    ts = self._parse_ts(e["recorded_at"], "recorded_at")
                    if since and ts < since:
                        continue
                    if until and ts >= until:
                        continue
                yield meter, e, idx

    @staticmethod
    def _event_view(meter: Meter, e: dict) -> dict:
        """Read-model of an event: raw fields plus normalized defaults for
        pre-v0.2.0 events. Never mutates the stored event (G2)."""
        return {
            **e,
            "provider": meter.provider,
            "consumer_class": e.get("consumer_class", "unknown"),
            "channel": e.get("channel", "unknown"),
            "caller": e.get("caller"),
            "is_test": e.get("is_test", False),
            "pre_v020": "consumer_class" not in e,
        }

    def _list_events(self, data: dict) -> dict:  # G8
        limit = data.get("limit", 100)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValidationError("limit must be an int in [1, 500]",
                                  field="limit", value=limit, constraint="1..500")
        cursor = data.get("cursor")
        cursor_key = None
        if cursor is not None:
            try:
                c_mid, c_idx = str(cursor).rsplit(":", 1)
                cursor_key = (c_mid, int(c_idx))
            except (ValueError, TypeError):
                raise ValidationError("malformed cursor", field="cursor",
                                      value=cursor, constraint="'<meter_id>:<index>'")
        out, next_cursor = [], None
        for meter, e, idx in self._iter_filtered(data):
            key = (meter.meter_id, idx)
            if cursor_key is not None and key <= cursor_key:
                continue
            if len(out) == limit:
                next_cursor = f"{out[-1]['meter_id']}:{out[-1]['_index']}"
                break
            out.append({**self._event_view(meter, e), "_index": idx})
        return self._ok({
            "count": len(out),
            "events": out,
            "next_cursor": next_cursor,
            "filters_applied": {k: data.get(k) for k in
                                ("meter_id", "provider", "consumer_class",
                                 "channel", "outcome", "since", "until")
                                if data.get(k) is not None},
            "include_test": bool(data.get("include_test", False)),
        })

    def _usage_timeseries(self, data: dict) -> dict:  # G9
        bucket = data.get("bucket", "day")
        if bucket not in ("day", "hour"):
            raise ValidationError("bucket must be 'day' or 'hour'",
                                  field="bucket", value=bucket, constraint="day|hour")
        fmt = "%Y-%m-%d" if bucket == "day" else "%Y-%m-%dT%H:00"
        series: Dict[str, dict] = {}
        for meter, e, _idx in self._iter_filtered(data):
            ts = self._parse_ts(e["recorded_at"], "recorded_at")
            key = ts.strftime(fmt)
            b = series.setdefault(key, {
                "bucket_start": key, "events": 0, "ok": 0, "error": 0,
                "quantity": 0.0, "est_accrued_minor": 0.0,
                "by_consumer_class": {}, "by_channel": {}, "by_provider": {}})
            b["events"] += 1
            b["ok" if e["outcome"] == "ok" else "error"] += 1
            b["quantity"] += e["quantity"]
            # Estimate only: authoritative money is per-meter ceil (M3/G9).
            b["est_accrued_minor"] += e["quantity"] * meter.price_minor_per_unit
            for dim, val in (("by_consumer_class", e.get("consumer_class", "unknown")),
                             ("by_channel", e.get("channel", "unknown")),
                             ("by_provider", meter.provider)):
                b[dim][val] = b[dim].get(val, 0) + 1
        ordered = [series[k] for k in sorted(series)]
        for b in ordered:
            b["est_accrued_minor"] = round(b["est_accrued_minor"], 4)
        return self._ok({
            "bucket": bucket, "bucket_count": len(ordered),
            "timezone": "UTC", "series": ordered,
            "include_test": bool(data.get("include_test", False)),
            "note": "est_accrued_minor is an estimate; authoritative billing "
                    "is usage_summary/close_period (per-meter ceil, M3).",
        })

    def _flag_meter(self, data: dict) -> dict:  # G10
        expected = os.environ.get("VIRIDIS_ADMIN_TOKEN", "")
        supplied = data.get("admin_token", "")
        if not expected:
            raise ValidationError(
                "flagging disabled: VIRIDIS_ADMIN_TOKEN is not configured",
                field="admin_token", constraint="server env must set token")
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
            raise ValidationError("invalid admin token", field="admin_token",
                                  constraint="must match VIRIDIS_ADMIN_TOKEN")
        meter = self._get_meter(data)
        is_test = data.get("is_test")
        if not isinstance(is_test, bool):
            raise ValidationError("is_test must be a boolean", field="is_test",
                                  value=is_test, constraint="true|false")
        meter.is_test = is_test
        note = data.get("note", "")
        if note:
            meter.flag_note = str(note)[:256]
        return self._ok({**meter.public(), "flag_note": meter.flag_note})

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"meters": len(self._meters),
                       "events": sum(len(m.events) for m in self._meters.values())}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Usage metering + SLA accounting for agent services "
                           "(the meter behind x402 micropayments).",
            "capabilities": ["create_meter", "record_usage", "usage_summary",
                             "sla_report", "close_period", "verify_chain",
                             "list_meters", "list_events", "usage_timeseries",
                             "flag_meter"],
            "inputs": {"action": "str", "meter_id": "str", "event_id": "str",
                       "quantity": "number", "outcome": "ok|error",
                       "provider": "str", "consumer": "str", "unit": "str",
                       "price_minor_per_unit": "number",
                       "consumer_class": "internal|external|unknown (trusted writer only)",
                       "channel": "str (trusted writer only)",
                       "is_test": "bool", "include_test": "bool",
                       "bucket": "day|hour", "cursor": "str", "limit": "int"},
            "outputs": {"status": "str (ok|error)", "data": "dict"},
            "a2a_role": "metering",
        }


def build(config: Optional[AgentConfig] = None) -> MeteringAgentCore:
    return MeteringAgentCore(config)
