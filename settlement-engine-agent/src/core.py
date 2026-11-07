"""
settlement-engine-agent — Core business logic.

THE SETTLEMENT LAYER OF THE CIRCULAR ECONOMY, AS A PRODUCT.
Sixty days of preregistered prediction-market research (Viridis count lane,
ENERGY-1, DECIDE-1/US-1, MAKER-1, DATA-1) established one mechanism that
pays and one that never does: forecasting loses to the price; reading the
official, progressively published number before anyone has done the
arithmetic wins. Any contract, grant, offset or pay-for-success agreement
that settles on an officially published series — ISO electricity prices,
election counts, restoration survival counts, canopy cover, soil carbon,
grid intensity — has a growing ALREADY-KNOWN component. This agent is that
arithmetic, served: what is published, what is still open, what the
remainder must do for an outcome to settle, and a recomputable settlement
when the series closes. Capital that only pays on verified outcomes is
circular capital; whoever runs the settlement earns on every dollar of it.
Thermodynamically: settlement converts published information (already paid
for in energy, dI/dt <= P*D/(kB*T*ln2)) into work — capital moved — with no
new information generated. We do not forecast; we count.

    register_series      (FREE)  — declare a series: unit, period, aggregate
                                   (mean | sum | last | share), source,
                                   expected observation count, strikes
    ingest               (FREE)  — append observations with a source hash;
                                   a re-posted slot replaces (revision kept)
    period_status        (FREE)  — published share, published aggregate,
                                   remaining, and per strike: required
                                   remainder, decided flag, labelled model p
    required_remainder   (FREE)  — the one number a buyer needs: what must
                                   the rest of the period average (or sum)
                                   for the strike to settle YES
    decided_strikes      (FREE)  — every strike across series that is
                                   decided by the published part alone
    explain              (FREE)  — deterministic plain-language reading of
                                   a series (no LLM in the serving path)
    compile_contract     (PAID)  — a Verified Outcome Contract v0: a series,
                                   a strike, a settlement rule and a closing
                                   time, content-addressed (digest)
    settle_contract      (PAID)  — evaluate a contract against the ledger:
                                   YES / NO / UNDECIDED with the evidence
                                   hashes and the exact arithmetic
    verify_settlement    (FREE)  — recompute a settlement from its stored
                                   evidence; any third party can check it

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input.

--- INVARIANTS (spec-invariance contract) ---
S1  FACTS AND MODELS ARE SEPARATE: everything derived from observations
    alone (published share, published aggregate, required remainder,
    decided) is returned under "facts" with the observation hashes behind
    it; anything from a remainder model is under "model" with a version
    tag and is never used to decide a strike. "decided" is arithmetic on
    the published part plus the declared physical bounds of the series
    (S5), nothing else.
S2  DETERMINISM: identical ledger + identical request -> identical result,
    byte for byte (sorted-key JSON, Decimal arithmetic, no clocks in the
    arithmetic; "now" is an explicit input where a time matters).
S3  NO TRADING, NO KEYS, NO NETWORK: the serving path reads and writes its
    own ledger only. Ingestion from a source is a separate adapter; the
    core receives observations as data with a source hash.
S4  EVERY OBSERVATION IS EVIDENCE: an observation carries (series_id, slot,
    value, source_url, source_sha256, observed_at). The ledger stores the
    sha256 of its canonical form; a settlement lists exactly the
    observation hashes it used, so verify_settlement can recompute it.
S5  DECIDED MEANS DECIDED: a strike is decided YES only if the aggregate
    would clear the strike even if every remaining slot took the series'
    declared minimum (value_min); decided NO only if it would miss even if
    every remaining slot took the declared maximum (value_max). With no
    declared bounds nothing is decided until the period is complete.
S6  NEVER RAISES on bad input — structured error envelopes (fleet C1);
    every error teaches the fix.
S7  REVISIONS ARE VISIBLE: a re-posted slot replaces the value and appends
    the superseded observation to the series' revision log; the status
    reports revision counts; a settlement records the ledger head hash it
    saw.
S8  SETTLEMENT IS RECOMPUTABLE AND IMMUTABLE: a settlement stores the
    observations it used (hashes and values), the rule, the arithmetic and
    the result; verify_settlement recomputes from that stored evidence and
    reports match/mismatch; settlements are never edited.
S9  BOUNDED: at most MAX_SERIES series, MAX_SLOTS observations per series,
    MAX_STRIKES strikes per series, MAX_CONTRACTS contracts; string fields
    are length-capped; over-cap requests get a structured error.
S10 PERIOD CLOSURE IS DECLARED, NOT INFERRED: a contract settles only after
    its closes_at (an explicit "now" >= closes_at) or when the strike is
    decided under S5 before then; an incomplete, undecided series at
    closure settles UNDECIDED, never a guess.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28
log = logging.getLogger("settlement-engine-agent")

AGENT_NAME = "settlement-engine-agent"
AGENT_VERSION = "0.1.0"
MODEL_VERSION = "remainder-v0-trailing-normal"

MAX_SERIES = 2_000
MAX_SLOTS = 50_000
MAX_STRIKES = 64
MAX_CONTRACTS = 20_000
MAX_STR = 400
AGGREGATES = ("mean", "sum", "last", "share")
SETTLEMENT_RULES = ("above", "at_or_above", "below", "at_or_below")

FREE_ACTIONS = ("register_series", "ingest", "period_status", "required_remainder", "decided_strikes", "explain",
                "verify_settlement", "list_series", "get_contract", "describe")
PAID_ACTIONS = ("compile_contract", "settle_contract")


# ----------------------------------------------------------------------------- helpers
def canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def D(x: Any) -> Optional[Decimal]:
    try:
        if isinstance(x, bool) or x is None:
            return None
        d = Decimal(str(x))
        if not d.is_finite():
            return None
        return d
    except (InvalidOperation, ValueError, TypeError):
        return None


def q(x: Optional[Decimal], places: int = 6) -> Optional[str]:
    if x is None:
        return None
    return str(x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN))


def err(code: str, message: str, fix: str, **extra) -> Dict[str, Any]:
    e = {"ok": False, "status": "error", "error_type": code, "message": message,          # fleet error envelope (isError)
         "error": {"code": code, "message": message, "fix": fix}}
    e.update(extra)
    return e


def is_hex64(s: Any) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def parse_t(s: Any) -> Optional[datetime]:
    if not isinstance(s, str) or not (10 <= len(s) <= 40):
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)


def _str(v: Any, name: str, required: bool = True, maxlen: int = MAX_STR) -> Tuple[Optional[str], Optional[Dict]]:
    if v is None or v == "":
        if required:
            return None, err("missing_field", f"{name} is required", f"pass a non-empty string for {name}")
        return None, None
    if not isinstance(v, str):
        return None, err("bad_type", f"{name} must be a string", f"pass {name} as a string")
    if len(v) > maxlen:
        return None, err("too_long", f"{name} is longer than {maxlen} characters", f"shorten {name}")
    return v, None


def _ncdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ----------------------------------------------------------------------------- state
@dataclass
class Series:
    series_id: str
    name: str
    unit: str
    aggregate: str
    n_expected: int
    value_min: Optional[Decimal]
    value_max: Optional[Decimal]
    source: str
    period_start: str
    period_end: str
    strikes: List[Decimal]
    meta: Dict[str, Any] = field(default_factory=dict)
    # slot -> observation record
    obs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    revisions: List[Dict[str, Any]] = field(default_factory=list)
    head: str = ""                                       # hash chain head over ingests

    def values(self) -> List[Decimal]:
        return [Decimal(self.obs[k]["value"]) for k in sorted(self.obs)]


@dataclass
class StateStore:
    series: Dict[str, Series] = field(default_factory=dict)
    contracts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    settlements: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ----------------------------------------------------------------------------- arithmetic (pure)
def published_aggregate(agg: str, vals: List[Decimal]) -> Optional[Decimal]:
    if not vals:
        return None
    if agg == "sum":
        return sum(vals, Decimal(0))
    if agg == "last":
        return vals[-1]
    if agg == "share":                                   # share of slots with value > 0 (e.g. survived = 1)
        return Decimal(sum(1 for v in vals if v > 0)) / Decimal(len(vals))
    return sum(vals, Decimal(0)) / Decimal(len(vals))


def required_remainder(agg: str, strike: Decimal, vals: List[Decimal], n_expected: int) -> Optional[Decimal]:
    """What the remaining slots must average (mean/share), sum to (sum) or be (last) for the aggregate to reach the
    strike exactly. None when nothing remains."""
    n_pub, n_rem = len(vals), n_expected - len(vals)
    if n_rem <= 0:
        return None
    s = sum(vals, Decimal(0))
    if agg == "mean":
        return (strike * Decimal(n_expected) - s) / Decimal(n_rem)
    if agg == "sum":
        return strike - s
    if agg == "last":
        return strike
    if agg == "share":
        hits = Decimal(sum(1 for v in vals if v > 0))
        return (strike * Decimal(n_expected) - hits) / Decimal(n_rem)   # share of remaining slots that must hit
    return None


def bounds_aggregate(agg: str, vals: List[Decimal], n_expected: int, fill: Decimal) -> Decimal:
    """The final aggregate if every remaining slot took `fill`."""
    n_rem = n_expected - len(vals)
    if agg == "sum":
        return sum(vals, Decimal(0)) + fill * Decimal(n_rem)
    if agg == "last":
        return fill if n_rem > 0 else vals[-1]
    if agg == "share":
        hits = Decimal(sum(1 for v in vals if v > 0)) + (Decimal(n_rem) if fill > 0 else Decimal(0))
        return hits / Decimal(n_expected)
    return (sum(vals, Decimal(0)) + fill * Decimal(n_rem)) / Decimal(n_expected)


def decided(agg: str, strike: Decimal, vals: List[Decimal], n_expected: int,
            vmin: Optional[Decimal], vmax: Optional[Decimal]) -> Tuple[Optional[str], str]:
    """S5. Returns ('YES'|'NO'|None, why). 'above' semantics: aggregate > strike settles YES."""
    n_rem = n_expected - len(vals)
    if n_rem <= 0 and vals:
        a = published_aggregate(agg, vals)
        return ("YES" if a > strike else "NO"), "period complete: aggregate %s strike" % (">" if a > strike else "<=")
    if not vals:
        return None, "nothing published"
    lo = vmin if agg != "share" else Decimal(0)
    hi = vmax if agg != "share" else Decimal(1)
    if lo is None or hi is None:
        return None, "no declared value bounds: undecided until the period is complete"
    worst = bounds_aggregate(agg, vals, n_expected, lo)
    best = bounds_aggregate(agg, vals, n_expected, hi)
    if worst > strike:
        return "YES", "clears the strike even if every remaining slot is at the declared minimum"
    if best <= strike:
        return "NO", "misses the strike even if every remaining slot is at the declared maximum"
    return None, "undecided: the remainder can still go either way"


def model_p(agg: str, strike: Decimal, vals: List[Decimal], n_expected: int, trail: int = 192) -> Dict[str, Any]:
    """Labelled model (S1): P(final aggregate > strike) under a Normal remainder with trailing mean and a widened
    trailing sd. Used for display only; never for 'decided'."""
    n_rem = n_expected - len(vals)
    if n_rem <= 0 or len(vals) < 2 or agg not in ("mean", "sum"):
        return {"version": MODEL_VERSION, "p": None, "why": "model not applicable (complete, <2 observations, or aggregate not mean/sum)"}
    w = [float(v) for v in vals[-trail:]]
    mu = sum(w) / len(w)
    var = sum((x - mu) ** 2 for x in w) / max(1, len(w) - 1)
    sd_slot = max(math.sqrt(var), 1e-9)
    sd_rem_mean = 2.0 * sd_slot / math.sqrt(n_rem)          # doubled: deliberately conservative (ENERGY-1 v0)
    need = required_remainder(agg, strike, vals, n_expected)
    need_mean = float(need) / (n_rem if agg == "sum" else 1)
    z = (mu - need_mean) / sd_rem_mean
    return {"version": MODEL_VERSION, "p": round(max(0.0, min(1.0, _ncdf(z))), 4),
            "remainder_mean_est": round(mu, 6), "remainder_sd_est": round(sd_rem_mean, 6), "why": "trailing-window Normal, sd doubled"}


# ----------------------------------------------------------------------------- the agent
class SettlementEngineAgent:
    # Fleet payment gate contract (payment_gate.attach): reads are free and bypass the gate; everything else is gated.
    KNOWN_ACTIONS = frozenset(FREE_ACTIONS + PAID_ACTIONS)
    READ_ACTIONS = frozenset(FREE_ACTIONS)

    def __init__(self, store: Optional[StateStore] = None):
        self.store = store or StateStore()

    # ---- fleet interface
    def describe(self) -> Dict[str, Any]:
        return {"name": AGENT_NAME, "version": AGENT_VERSION, "model_version": MODEL_VERSION,
                "actions": {"free": list(FREE_ACTIONS), "paid": list(PAID_ACTIONS)},
                "capabilities": list(FREE_ACTIONS) + list(PAID_ACTIONS),  # gateway directory (GET /) contract C7
                "invariants": ["S1 facts/model separate", "S2 deterministic", "S3 no trading/keys/network", "S4 observations are evidence",
                               "S5 decided means decided", "S6 never raises", "S7 revisions visible", "S8 settlement recomputable",
                               "S9 bounded", "S10 closure declared"],
                "limits": {"max_series": MAX_SERIES, "max_slots": MAX_SLOTS, "max_strikes": MAX_STRIKES, "max_contracts": MAX_CONTRACTS}}

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok", "ok": True, "agent": AGENT_NAME, "version": AGENT_VERSION, "series": len(self.store.series),   # gateway /healthz needs status
                "contracts": len(self.store.contracts), "settlements": len(self.store.settlements)}

    async def process(self, payload: Any) -> Dict[str, Any]:
        try:
            if not isinstance(payload, dict):
                return err("bad_payload", "payload must be an object", 'send {"action": "...", ...}')
            action = payload.get("action")
            fn = getattr(self, f"_a_{action}", None) if isinstance(action, str) and not action.startswith("_") else None
            if fn is None:
                return err("unknown_action", f"unknown action {action!r}", f"use one of {list(FREE_ACTIONS + PAID_ACTIONS)}")
            return fn(payload)
        except Exception as e:                            # S6: never raises
            log.exception("process failed")
            return err("internal", f"{type(e).__name__}: {e}"[:MAX_STR], "report this with the payload; the agent never raises by contract")

    # ---- actions
    def _a_describe(self, p):                             # noqa
        return {"ok": True, **self.describe()}

    def _a_list_series(self, p):
        return {"ok": True, "series": [self._series_card(s) for _, s in sorted(self.store.series.items())]}

    def _a_register_series(self, p):
        if len(self.store.series) >= MAX_SERIES:
            return err("over_cap", f"{MAX_SERIES} series already registered", "retire or reuse a series")
        name, e = _str(p.get("name"), "name");                                   # noqa
        if e: return e
        unit, e = _str(p.get("unit"), "unit")
        if e: return e
        source, e = _str(p.get("source"), "source")
        if e: return e
        agg = p.get("aggregate", "mean")
        if agg not in AGGREGATES:
            return err("bad_aggregate", f"aggregate must be one of {AGGREGATES}", "mean for averages (prices), sum for totals, share for survival/success rates, last for a closing value")
        n = p.get("n_expected")
        if not isinstance(n, int) or isinstance(n, bool) or not (1 <= n <= MAX_SLOTS):
            return err("bad_n_expected", f"n_expected must be an integer 1..{MAX_SLOTS}", "the number of observation slots in the period (e.g. 672 fifteen-minute intervals in a week)")
        ps, pe = parse_t(p.get("period_start")), parse_t(p.get("period_end"))
        if ps is None or pe is None or pe <= ps:
            return err("bad_period", "period_start and period_end must be ISO-8601 times with end after start", "e.g. 2026-11-03T00:00:00-06:00")
        vmin, vmax = D(p.get("value_min")), D(p.get("value_max"))
        if (p.get("value_min") is not None and vmin is None) or (p.get("value_max") is not None and vmax is None):
            return err("bad_bounds", "value_min/value_max must be numbers", "declare the physical bounds of one observation (ERCOT SPP: -251 to 5000 $/MWh; survival: 0 to 1)")
        if vmin is not None and vmax is not None and vmax < vmin:
            return err("bad_bounds", "value_max is below value_min", "swap them")
        strikes_in = p.get("strikes", [])
        if not isinstance(strikes_in, list) or len(strikes_in) > MAX_STRIKES:
            return err("bad_strikes", f"strikes must be a list of at most {MAX_STRIKES} numbers", "e.g. [30, 35, 40]")
        strikes = []
        for s in strikes_in:
            d = D(s)
            if d is None:
                return err("bad_strikes", f"strike {s!r} is not a number", "pass numeric strikes")
            strikes.append(d)
        strikes = sorted(set(strikes))
        meta = p.get("meta") if isinstance(p.get("meta"), dict) else {}
        if len(canon(meta)) > 4000:
            return err("too_long", "meta is larger than 4000 bytes", "keep meta small; put documents behind a URL")
        sid = sha256_hex(canon({"name": name, "unit": unit, "aggregate": agg, "n_expected": n, "source": source,
                                "period_start": ps.isoformat(), "period_end": pe.isoformat()}))[:24]
        if sid in self.store.series:
            return {"ok": True, "series_id": sid, "existing": True, "series": self._series_card(self.store.series[sid])}
        self.store.series[sid] = Series(sid, name, unit, agg, n, vmin, vmax, source, ps.isoformat(), pe.isoformat(), strikes, meta)
        return {"ok": True, "series_id": sid, "existing": False, "series": self._series_card(self.store.series[sid])}

    def _a_ingest(self, p):
        s = self._get_series(p.get("series_id"))
        if isinstance(s, dict):
            return s
        obs_in = p.get("observations")
        if not isinstance(obs_in, list) or not obs_in or len(obs_in) > 5000:
            return err("bad_observations", "observations must be a non-empty list of at most 5000 items",
                       '[{"slot": "2026-11-03T00:00-06:00", "value": 31.2, "source_url": "...", "source_sha256": "<64 hex>", "observed_at": "..."}]')
        if len(s.obs) + len(obs_in) > MAX_SLOTS:
            return err("over_cap", f"series would exceed {MAX_SLOTS} observations", "split the period into more series")
        added, replaced, rejected = 0, 0, []
        for i, o in enumerate(obs_in):
            if not isinstance(o, dict):
                rejected.append({"i": i, "why": "not an object"}); continue
            slot, e = _str(o.get("slot"), "slot", maxlen=64)
            if e: rejected.append({"i": i, "why": e["error"]["message"]}); continue
            v = D(o.get("value"))
            if v is None:
                rejected.append({"i": i, "why": "value is not a finite number"}); continue
            if (s.value_min is not None and v < s.value_min) or (s.value_max is not None and v > s.value_max):
                rejected.append({"i": i, "why": f"value {v} outside declared bounds [{s.value_min}, {s.value_max}]"}); continue
            if s.aggregate == "share" and v not in (Decimal(0), Decimal(1)):
                rejected.append({"i": i, "why": "share series take 0 or 1 per slot"}); continue
            url, e = _str(o.get("source_url"), "source_url")
            if e: rejected.append({"i": i, "why": e["error"]["message"]}); continue
            if not is_hex64(o.get("source_sha256")):
                rejected.append({"i": i, "why": "source_sha256 must be the 64-hex sha256 of the source document"}); continue
            at = parse_t(o.get("observed_at"))
            if at is None:
                rejected.append({"i": i, "why": "observed_at must be ISO-8601"}); continue
            rec = {"slot": slot, "value": str(v), "source_url": url, "source_sha256": o["source_sha256"], "observed_at": at.isoformat()}
            rec["obs_sha256"] = sha256_hex(canon(rec))
            prev = s.obs.get(slot)
            if prev is not None:
                if prev["obs_sha256"] == rec["obs_sha256"]:
                    continue                                  # identical re-post: nothing to do
                s.revisions.append({"slot": slot, "superseded": prev, "by": rec["obs_sha256"]})   # S7
                replaced += 1
            else:
                added += 1
            s.obs[slot] = rec
            s.head = sha256_hex(s.head + rec["obs_sha256"])
        return {"ok": True, "series_id": s.series_id, "added": added, "replaced": replaced, "rejected": rejected,
                "published": len(s.obs), "n_expected": s.n_expected, "ledger_head": s.head}

    def _a_period_status(self, p):
        s = self._get_series(p.get("series_id"))
        if isinstance(s, dict):
            return s
        return {"ok": True, **self._status(s)}

    def _a_required_remainder(self, p):
        s = self._get_series(p.get("series_id"))
        if isinstance(s, dict):
            return s
        k = D(p.get("strike"))
        if k is None:
            return err("bad_strike", "strike must be a number", "e.g. 30")
        vals = s.values()
        need = required_remainder(s.aggregate, k, vals, s.n_expected)
        dec, why = decided(s.aggregate, k, vals, s.n_expected, s.value_min, s.value_max)
        return {"ok": True, "series_id": s.series_id, "strike": str(k), "facts": {
            "published": len(vals), "remaining": s.n_expected - len(vals), "published_aggregate": q(published_aggregate(s.aggregate, vals)),
            "required_remainder": q(need), "required_meaning": self._need_meaning(s.aggregate), "decided": dec, "decided_why": why,
            "ledger_head": s.head}, "model": model_p(s.aggregate, k, vals, s.n_expected)}

    def _a_decided_strikes(self, p):
        out = []
        for sid, s in sorted(self.store.series.items()):
            vals = s.values()
            for k in s.strikes:
                dec, why = decided(s.aggregate, k, vals, s.n_expected, s.value_min, s.value_max)
                if dec:
                    out.append({"series_id": sid, "name": s.name, "strike": str(k), "decided": dec, "why": why,
                                "published_share": q(Decimal(len(vals)) / Decimal(s.n_expected), 4)})
        return {"ok": True, "decided": out, "count": len(out)}

    def _a_explain(self, p):
        s = self._get_series(p.get("series_id"))
        if isinstance(s, dict):
            return s
        st = self._status(s)
        f = st["facts"]
        lines = [f"{s.name}: {f['published']} of {s.n_expected} slots published ({f['published_share']} of the period), "
                 f"published {s.aggregate} so far {f['published_aggregate']} {s.unit}."]
        for row in st["strikes"]:
            if row["decided"]:
                lines.append(f"Strike {row['strike']}: DECIDED {row['decided']} — {row['decided_why']}.")
            elif row["required_remainder"] is not None:
                lines.append(f"Strike {row['strike']}: undecided; the remaining {f['remaining']} slots must {self._need_meaning(s.aggregate)} "
                             f"{row['required_remainder']} {s.unit} for it to settle YES"
                             + (f" (model {row['model']['version']}: p={row['model']['p']})" if row["model"].get("p") is not None else "") + ".")
        if f["revisions"]:
            lines.append(f"{f['revisions']} slot(s) were revised by the source after first publication; the latest value is used.")
        lines.append("Facts are arithmetic on the published source documents (hashes in period_status); model figures are estimates and never decide a strike.")
        return {"ok": True, "series_id": s.series_id, "explanation": " ".join(lines)}

    def _a_compile_contract(self, p):
        if len(self.store.contracts) >= MAX_CONTRACTS:
            return err("over_cap", f"{MAX_CONTRACTS} contracts already compiled", "settle or archive contracts")
        s = self._get_series(p.get("series_id"))
        if isinstance(s, dict):
            return s
        k = D(p.get("strike"))
        if k is None:
            return err("bad_strike", "strike must be a number", "the threshold the aggregate is compared with")
        rule = p.get("rule", "above")
        if rule not in SETTLEMENT_RULES:
            return err("bad_rule", f"rule must be one of {SETTLEMENT_RULES}", "above: aggregate > strike settles YES")
        closes = parse_t(p.get("closes_at"))
        if closes is None:
            return err("bad_closes_at", "closes_at must be ISO-8601", "the time after which the contract may settle on a complete series")
        parties = p.get("parties") if isinstance(p.get("parties"), dict) else {}
        terms, e = _str(p.get("terms"), "terms", required=False, maxlen=2000)
        if e: return e
        c = {"v": "verified-outcome-contract-v0", "series_id": s.series_id, "series_name": s.name, "unit": s.unit, "aggregate": s.aggregate,
             "n_expected": s.n_expected, "strike": str(k), "rule": rule, "closes_at": closes.isoformat(), "parties": parties,
             "terms": terms or "", "source": s.source, "value_min": q(s.value_min), "value_max": q(s.value_max)}
        cid = sha256_hex(canon(c))
        c["contract_id"] = cid
        if cid in self.store.contracts:
            return {"ok": True, "contract_id": cid, "existing": True, "contract": c}
        self.store.contracts[cid] = c
        return {"ok": True, "contract_id": cid, "existing": False, "contract": c}

    def _a_get_contract(self, p):
        cid = p.get("contract_id")
        c = self.store.contracts.get(cid) if is_hex64(cid) else None
        if c is None:
            return err("unknown_contract", "no contract with that id", "compile_contract first and use the returned contract_id")
        st = [sid for sid, x in self.store.settlements.items() if x["contract_id"] == cid]
        return {"ok": True, "contract": c, "settlements": st}

    def _a_settle_contract(self, p):
        cid = p.get("contract_id")
        c = self.store.contracts.get(cid) if is_hex64(cid) else None
        if c is None:
            return err("unknown_contract", "no contract with that id", "compile_contract first")
        now = parse_t(p.get("now"))
        if now is None:
            return err("bad_now", "now must be an explicit ISO-8601 time (S2: no clocks in the arithmetic)", "pass the settlement time you are asserting")
        s = self.store.series.get(c["series_id"])
        if s is None:
            return err("unknown_series", "the contract's series is gone", "re-register the series with the same definition")
        vals = s.values()
        k = Decimal(c["strike"])
        dec, why = decided(s.aggregate, k, vals, s.n_expected, s.value_min, s.value_max)   # 'above' semantics
        complete = len(vals) >= s.n_expected
        closed = now >= parse_t(c["closes_at"])
        agg_now = published_aggregate(s.aggregate, vals)
        result, basis = "UNDECIDED", ""
        if dec is not None:                                     # S10: a decided strike settles before or after closure
            yes_above = dec == "YES"
            # translate 'above' decision into the contract's rule
            if c["rule"] == "above":
                result, basis = ("YES" if yes_above else "NO"), why
            elif c["rule"] == "at_or_below":
                result, basis = ("NO" if yes_above else "YES"), why
            elif c["rule"] in ("at_or_above", "below"):
                # equality case differs from 'above' only when the final aggregate equals the strike exactly
                if complete:
                    eq = agg_now == k
                    hit = (agg_now >= k) if c["rule"] == "at_or_above" else (agg_now < k)
                    result, basis = ("YES" if hit else "NO"), ("period complete" + (" (aggregate equals strike)" if eq else ""))
                else:
                    # decided by bounds strictly: S5 bounds are strict for 'above'; for at_or_above a worst == strike is still YES
                    lo = s.value_min if s.aggregate != "share" else Decimal(0)
                    hi = s.value_max if s.aggregate != "share" else Decimal(1)
                    worst, best = bounds_aggregate(s.aggregate, vals, s.n_expected, lo), bounds_aggregate(s.aggregate, vals, s.n_expected, hi)
                    if c["rule"] == "at_or_above":
                        result = "YES" if worst >= k else ("NO" if best < k else "UNDECIDED")
                    else:
                        result = "YES" if best < k else ("NO" if worst >= k else "UNDECIDED")
                    basis = why
        elif not closed and not complete:
            basis = f"not closed (closes_at {c['closes_at']}) and undecided"
        else:
            basis = "closed but the series is incomplete and undecided: UNDECIDED by S10 (never a guess)"
        evidence = [{"slot": s.obs[k2]["slot"], "value": s.obs[k2]["value"], "obs_sha256": s.obs[k2]["obs_sha256"], "source_sha256": s.obs[k2]["source_sha256"]}
                    for k2 in sorted(s.obs)]
        rec = {"v": "verified-outcome-settlement-v0", "contract_id": cid, "series_id": s.series_id, "now": now.isoformat(), "result": result,
               "basis": basis, "aggregate": s.aggregate, "n_expected": s.n_expected, "published": len(vals), "published_aggregate": q(agg_now),
               "strike": c["strike"], "rule": c["rule"], "value_min": q(s.value_min), "value_max": q(s.value_max), "ledger_head": s.head,
               "revisions": len(s.revisions), "evidence": evidence, "model_version_note": "no model figure is used in settlement (S1)"}
        rec["settlement_sha256"] = sha256_hex(canon(rec))
        sid = rec["settlement_sha256"]
        if sid not in self.store.settlements:                                   # S8: immutable, idempotent by content
            self.store.settlements[sid] = rec
        return {"ok": True, "settlement_id": sid, "result": result, "basis": basis, "settlement": rec}

    def _a_verify_settlement(self, p):
        sid = p.get("settlement_id")
        rec = self.store.settlements.get(sid) if is_hex64(sid) else (p.get("settlement") if isinstance(p.get("settlement"), dict) else None)
        if rec is None:
            return err("unknown_settlement", "pass settlement_id (stored) or the full settlement record", "settle_contract returns both")
        return {"ok": True, **verify_settlement_record(rec)}

    # ---- internals
    def _get_series(self, sid):
        s = self.store.series.get(sid) if isinstance(sid, str) else None
        return s if s is not None else err("unknown_series", "no series with that id", "register_series first, or list_series")

    def _series_card(self, s: Series) -> Dict[str, Any]:
        return {"series_id": s.series_id, "name": s.name, "unit": s.unit, "aggregate": s.aggregate, "n_expected": s.n_expected,
                "published": len(s.obs), "value_min": q(s.value_min), "value_max": q(s.value_max), "source": s.source,
                "period_start": s.period_start, "period_end": s.period_end, "strikes": [str(k) for k in s.strikes], "meta": s.meta}

    @staticmethod
    def _need_meaning(agg: str) -> str:
        return {"mean": "average", "sum": "sum to", "last": "end at", "share": "hit at a share of"}.get(agg, "reach")

    def _status(self, s: Series) -> Dict[str, Any]:
        vals = s.values()
        rows = []
        for k in s.strikes:
            dec, why = decided(s.aggregate, k, vals, s.n_expected, s.value_min, s.value_max)
            rows.append({"strike": str(k), "required_remainder": q(required_remainder(s.aggregate, k, vals, s.n_expected)),
                         "decided": dec, "decided_why": why, "model": model_p(s.aggregate, k, vals, s.n_expected)})
        return {"series_id": s.series_id, "name": s.name, "unit": s.unit, "aggregate": s.aggregate,
                "facts": {"published": len(vals), "n_expected": s.n_expected, "remaining": s.n_expected - len(vals),
                          "published_share": q(Decimal(len(vals)) / Decimal(s.n_expected), 4), "published_aggregate": q(published_aggregate(s.aggregate, vals)),
                          "min_observed": q(min(vals)) if vals else None, "max_observed": q(max(vals)) if vals else None,
                          "revisions": len(s.revisions), "ledger_head": s.head, "last_slot": max(s.obs) if s.obs else None,
                          "sources": sorted({o["source_sha256"] for o in s.obs.values()})[:50]},
                "strikes": rows}


def verify_settlement_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """S8: recompute a settlement from its own stored evidence. Pure."""
    try:
        body = {k: v for k, v in rec.items() if k != "settlement_sha256"}
        hash_ok = sha256_hex(canon(body)) == rec.get("settlement_sha256")
        vals, ev_ok = [], True
        for e in rec.get("evidence", []):
            v = D(e.get("value"))
            if v is None or not is_hex64(e.get("obs_sha256")):
                ev_ok = False
            else:
                vals.append(v)
        agg, n, k = rec.get("aggregate"), rec.get("n_expected"), D(rec.get("strike"))
        vmin, vmax = D(rec.get("value_min")), D(rec.get("value_max"))
        a = published_aggregate(agg, vals)
        agg_ok = q(a) == rec.get("published_aggregate")
        dec, _ = decided(agg, k, vals, n, vmin, vmax)
        complete = len(vals) >= n
        rule = rec.get("rule")
        if rule == "above":
            expect = dec or "UNDECIDED"
        elif rule == "at_or_below":
            expect = {"YES": "NO", "NO": "YES", None: "UNDECIDED"}[dec]
        elif complete:
            hit = (a >= k) if rule == "at_or_above" else (a < k)
            expect = "YES" if hit else "NO"
        else:
            expect = rec.get("result")                       # bounds case for the two inclusive rules: recomputed inline below
            lo = vmin if agg != "share" else Decimal(0); hi = vmax if agg != "share" else Decimal(1)
            if lo is not None and hi is not None and vals:
                worst, best = bounds_aggregate(agg, vals, n, lo), bounds_aggregate(agg, vals, n, hi)
                expect = ("YES" if worst >= k else ("NO" if best < k else "UNDECIDED")) if rule == "at_or_above" else \
                         ("YES" if best < k else ("NO" if worst >= k else "UNDECIDED"))
        result_ok = expect == rec.get("result")
        return {"settlement_id": rec.get("settlement_sha256"), "hash_ok": hash_ok, "evidence_ok": ev_ok, "aggregate_ok": agg_ok,
                "result_ok": result_ok, "match": bool(hash_ok and ev_ok and agg_ok and result_ok),
                "recomputed": {"published_aggregate": q(a), "result": expect, "published": len(vals)}}
    except Exception as e:                                   # S6
        return {"match": False, "why": f"unverifiable record: {type(e).__name__}: {e}"[:MAX_STR]}


def build(store: Optional[StateStore] = None) -> SettlementEngineAgent:
    return SettlementEngineAgent(store)
