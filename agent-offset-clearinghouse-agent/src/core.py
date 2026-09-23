"""
agent-offset-clearinghouse-agent — Core business logic.

The first economy born carbon-accountable. agent-compute-ledger-agent prices
agent cognition in gCO2e; this clearinghouse closes the loop: verified
conservation credits (D-Score / land-verification references required) are
listed, matched to agent emissions cheapest-first, retired exactly-once, and
certified with content-addressed offset certificates. Mass is conserved to
the gram — no credit is ever created, destroyed, or retired twice.

This is the Viridis flywheel made structural: every ton the agent economy
emits becomes demand for verified conservation. Payment settles over
agent-escrow-agent; this core owns matching + retirement invariants only —
no money moves here.

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input.

--- INVARIANTS (spec-invariance contract) ---
O1  Conservation of mass: for every credit and for the whole book,
    available_g + retired_g == listed_g at all times.
O2  No double-retirement: retirement is idempotent on purchase_id (a retry
    returns the original fills) and a credit's retired mass never exceeds
    its listed mass.
O3  Deterministic matching: cheapest price first, then listing order. The
    same book and the same order always produce the same fills.
O4  Offset certificates are content-addressed; verify_certificate recomputes
    the hash and checks it against the ledger.
O5  Net-position arithmetic is exact: net_g == emitted_g - retired_g, where
    retired_g is the exact sum of the buyer's retirements.
O6  Price integrity: each fill costs ceil(fill_kg * price_minor_per_kg),
    integer minor units; total cost is the exact sum of fill costs.
O7  Only VERIFIED supply exists: listing a credit requires a non-empty
    D-Score verification_ref plus a minimum listing price. Unverifiable or
    sub-floor credits cannot enter the fill path.
O8  Unknown credit/purchase/buyer -> error envelope, never a crash.
O9  Budget purchases never overspend: buy_offset_budget retires the maximum
    cheapest-first mass whose exact O6 cost is <= budget_minor; the returned
    total_cost_minor is always <= budget_minor.
O10 dry_run mutates nothing: a dry_run purchase (mass- or budget-denominated)
    returns the exact fills/cost a real purchase would produce, but the book,
    the purchase ledger, and buyer retirement totals are unchanged — and a
    dry_run is never recorded against purchase_id idempotency.
O11 settlement_batch is read-only and exact: its totals (purchases, mass_g,
    cost_minor) equal the exact sums over the buyer's matching non-dry
    purchases; calling it never changes any state.
O12 A budget too small to retire a single gram is rejected with an error
    envelope (never a zero-mass certificate).
O13 verify_retirement is the x402-C C4 check: given a purchase_id (an
    offset_ref) and a required emission mass, it reports whether the
    retirement covers it (retired_g >= required_g), with the shortfall and
    the backing credits. Read-only — it never mutates the book.
O14 delist_credit removes an active listing from matching without deleting its
    immutable history. Delisted available mass is excluded from every fill,
    while prior retirements and certificates remain verifiable.

--- RESTORATION-PROJECT FUNDING INVARIANTS (P1-P6, the supply side) ---
P1  register_project records a verified restoration project; verification_ref
    is required (only verified conservation can be funded, mirroring O7).
    project_id is immutable once registered: identical re-registration is
    idempotent, conflicting re-registration is rejected.
P2  Funding attribution is exact: a project's gross_proceeds_minor equals the
    exact sum of cost_minor over every non-dry-run fill of its credits, and
    retired_g equals the exact sum of those fills' mass_g (ties to O6/O10).
P3  register_project mutates ONLY the project registry (never credits,
    purchases, or the book); project_funding and list_projects mutate nothing.
P4  Backward compatible: projects are optional metadata. Retirements against
    an unregistered project_id are still attributed (by the string), just
    without enriched metadata; existing credits/purchases are unaffected.
P5  A registered-but-unfunded project, or an unknown project_id, reports zero
    funding — never an error.
P6  Conservation of proceeds: the sum of gross_proceeds_minor across all
    projects equals the exact sum of every non-dry-run purchase's fill costs
    — no proceeds are created or lost in attribution.

--- CERTIFIED DISBURSEMENT INVARIANTS (D1-D7; automated split + certification) ---
D1  Split conservation: for every line, viridis_withhold_minor +
    project_payout_minor == the amount being disbursed. No money is created
    or lost in the split.
D2  Deterministic split: withhold = amount * withhold_bps // 10000 (integer
    floor); payout = amount - withhold. Same inputs -> same split.
D3  Withhold is bounded and configurable: withhold_bps in [0, 10000], read
    from VIRIDIS_CONSERVATION_WITHHOLD_BPS (default 1500 = 15% to seed-fund
    Viridis Conservation); an out-of-range/invalid env value falls back to
    the default and never crashes. disbursement_schedule is read-only.
D4  Exactly-once, delta-accrual: certify_disbursement is idempotent on
    batch_id (a replay returns the original certificate) and each project's
    cumulative certified amount only ever increases by newly-accrued
    proceeds — funding is never disbursed twice.
D5  Certificates are content-addressed and hash-chained: each disbursement
    certificate commits to the previous one's hash; verify_disbursement
    recomputes the whole chain.
D6  Only verified restoration is paid: a project must be registered (P1,
    verification_ref present) to appear as a "ready" certifiable payout line;
    funded-but-unregistered projects are surfaced as pending_registration and
    never certified — you cannot disburse to an unverified project.
D7  Whole-book conservation: the sum of every certificate's total_disbursed
    equals the sum of cumulative per-project certified amounts.

--- VERRA REGISTRY / TRADING INVARIANTS (VR1-VR5; trade on the Verra network) ---
VR1 A credit listed with registry="verra" REQUIRES vcs_project_id +
    serial_number + vintage — a credit can only trade as Verra if it carries
    genuine, cross-referenceable Verra VCS provenance. An unsupported
    registry value is rejected.
VR2 Verra provenance (registry, vcs_project_id, vintage, serial_number) is
    carried immutably into every fill and therefore into the content-addressed
    retirement certificate — a retirement of Verra supply references the exact
    VCS project + serial, cross-referenceable on registry.verra.org.
VR3 The 15% Viridis take (the D-series disbursement withhold) applies to Verra
    trade proceeds exactly as to any proceeds: a Verra sale nets the project
    85% and Viridis 15% — the marketplace take that seeds the business.
VR4 Backward compatible: credits without registry fields behave exactly as
    before (registry defaults to "", treated as generic verified supply); all
    O/P/D invariants are unchanged.
VR5 verra_supply surfaces the tradeable Verra book (read-only), and every
    retirement certificate exposes the Verra serial/project for external
    cross-reference.
VR6 verra_retirement_record is read-only and produces the complete,
    Verra-portal-ready retirement record(s) for a retirement's Verra fills
    (grouped by VCS project + serial + vintage), with total quantity conserved
    (sum of record quantity_g == sum of the retirement's Verra fill masses).
    Non-Verra fills are excluded; a retirement with no Verra fills is an error.
    The actual on-registry post stays the operator's Verra-account action
    (portal now; API adapter when Verra's 2026 transaction API is live).
"""

import hashlib
import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Share of each project's gross proceeds withheld to seed-fund the Viridis
# Conservation software/business (the flywheel's operator). Default 15% =
# 1500 bps; projects keep the remaining 85%. Env-overridable without a code
# change; an out-of-range value falls back to the default (never crashes).
DEFAULT_VIRIDIS_WITHHOLD_BPS = 1500
DEFAULT_MIN_PRICE_MINOR_PER_KG = 100
_DISBURSE_GENESIS = "0" * 64


def _viridis_withhold_bps() -> int:  # D3
    raw = os.environ.get("VIRIDIS_CONSERVATION_WITHHOLD_BPS")
    if raw is None:
        return DEFAULT_VIRIDIS_WITHHOLD_BPS
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_VIRIDIS_WITHHOLD_BPS
    return v if 0 <= v <= 10_000 else DEFAULT_VIRIDIS_WITHHOLD_BPS


def _min_listing_price_minor_per_kg() -> int:
    """Production-safe listing floor. Invalid configuration fails closed to
    the built-in floor rather than reopening penny test supply."""
    raw = os.environ.get("OFFSET_MIN_PRICE_MINOR_PER_KG")
    if raw is None:
        return DEFAULT_MIN_PRICE_MINOR_PER_KG
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MIN_PRICE_MINOR_PER_KG
    return value if value >= DEFAULT_MIN_PRICE_MINOR_PER_KG \
        else DEFAULT_MIN_PRICE_MINOR_PER_KG

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    name: str
    version: str = "0.6.0"
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
        return {"status": "ok", "agent": self.config.name,
                "version": self.config.version, "timestamp": _utcnow(), "checks": {}}

    def describe(self) -> dict:
        return {"name": self.config.name, "version": self.config.version,
                "description": "override me", "capabilities": [],
                "inputs": {}, "outputs": {}}

    def _err(self, message: str, *, error_type: str = "Error",
             field: str = "", value: Any = None, constraint: str = "") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _utcnow()}

    def _ok(self, data: Any = None) -> dict:
        return {"status": "ok", "data": data, "error": None, "timestamp": _utcnow()}


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


# --------------------------------------------------------------------------- #
# Domain
# --------------------------------------------------------------------------- #
def _content_hash(content: dict) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _pos_int(data: dict, f: str) -> int:
    v = data.get(f)
    if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
        raise ValidationError(f"'{f}' must be a positive integer", field=f,
                              value=v, constraint="int > 0")
    return v


@dataclass
class Credit:
    credit_id: str
    issuer: str
    project_id: str
    listed_g: int
    retired_g: int
    price_minor_per_kg: int
    verification_ref: str
    listed_at: str
    # --- registry provenance (VR-series; e.g. Verra VCS) ---
    registry: str = ""          # "" = generic verified; "verra" = Verra VCS
    vcs_project_id: str = ""     # Verra project id (e.g. "VCS1477")
    vintage: str = ""           # crediting vintage year
    serial_number: str = ""     # VCU serial block, cross-referenceable on Verra
    methodology: str = ""       # e.g. "VM0007"
    delisted_at: str = ""
    delist_reason: str = ""

    def __setstate__(self, state: dict) -> None:
        for k, d in (("registry", ""), ("vcs_project_id", ""), ("vintage", ""),
                     ("serial_number", ""), ("methodology", ""),
                     ("delisted_at", ""), ("delist_reason", "")):
            state.setdefault(k, d)
        self.__dict__.update(state)

    @property
    def available_g(self) -> int:
        return self.listed_g - self.retired_g

    def public(self) -> dict:
        delisted_at = getattr(self, "delisted_at", "")
        return {"credit_id": self.credit_id, "issuer": self.issuer,
                "project_id": self.project_id, "listed_g": self.listed_g,
                "retired_g": self.retired_g, "available_g": self.available_g,
                "price_minor_per_kg": self.price_minor_per_kg,
                "verification_ref": self.verification_ref,
                "listed_at": self.listed_at,
                "registry": self.registry, "vcs_project_id": self.vcs_project_id,
                "vintage": self.vintage, "serial_number": self.serial_number,
                "methodology": self.methodology,
                "listing_status": "delisted" if delisted_at else "active",
                "delisted_at": delisted_at,
                "delist_reason": getattr(self, "delist_reason", "")}


class OffsetClearinghouseAgentCore(AgentCore):
    """Verified conservation credits matched to agent emissions. Mass-conserving."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="agent-offset-clearinghouse-agent"))
        self._credits: Dict[str, Credit] = {}
        self._order: List[str] = []
        self._purchases: Dict[str, dict] = {}
        self._retired_by_buyer: Dict[str, int] = {}
        self._projects: Dict[str, dict] = {}   # P1: restoration project registry
        self._disbursed_by_project: Dict[str, int] = {}  # D4: cumulative certified
        self._disbursements: List[dict] = []   # D5: hash-chained certificates
        self._seq = 0

    def __setstate__(self, state: dict) -> None:
        """Forward-compat: snapshots written before the project registry
        (v<0.2.0) or disbursement layer (v<0.3.0) restore with empty
        structures rather than crashing."""
        state.setdefault("_projects", {})
        state.setdefault("_disbursed_by_project", {})
        state.setdefault("_disbursements", [])
        self.__dict__.update(state)

    async def process(self, input_data: dict) -> dict:
        try:
            if not isinstance(input_data, dict):
                return self._err("input must be an object", error_type="ValidationError",
                                 field="input", value=type(input_data).__name__, constraint="dict")
            action = input_data.get("action")
            handler = {
                "list_credit": self._list_credit,
                "delist_credit": self._delist_credit,
                "buy_offset": self._buy_offset,
                "buy_offset_budget": self._buy_offset_budget,
                "net_position": self._net_position,
                "verify_certificate": self._verify_certificate,
                "book": self._book,
                "get_purchase": self._get_purchase,
                "settlement_batch": self._settlement_batch,
                "verify_retirement": self._verify_retirement,
                "register_project": self._register_project,
                "project_funding": self._project_funding,
                "list_projects": self._list_projects,
                "disbursement_schedule": self._disbursement_schedule,
                "certify_disbursement": self._certify_disbursement,
                "verify_disbursement": self._verify_disbursement,
                "verra_supply": self._verra_supply,
                "verra_retirement_record": self._verra_retirement_record,
            }.get(action)
            if handler is None:
                return self._err(f"unknown action '{action}'", error_type="ValidationError",
                                 field="action", value=action,
                                 constraint="one of: list_credit, delist_credit, "
                                            "buy_offset, buy_offset_budget, "
                                            "net_position, verify_certificate, book, "
                                            "get_purchase, settlement_batch, verify_retirement, "
                                            "register_project, project_funding, list_projects, "
                                            "disbursement_schedule, certify_disbursement, "
                                            "verify_disbursement, verra_supply, "
                                            "verra_retirement_record")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError", field=e.field,
                             value=e.value, constraint=e.constraint)
        except Exception as e:  # noqa: BLE001
            self.logger.exception("offset-clearinghouse process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ------------------------------------------------------------------ #
    def _list_credit(self, data: dict) -> dict:
        for f in ("issuer", "project_id"):
            if not data.get(f) or not isinstance(data.get(f), str):
                raise ValidationError(f"missing '{f}'", field=f, constraint="non-empty str")
        vref = data.get("verification_ref")
        if (not isinstance(vref, str)
                or not vref.startswith("dscore:")
                or len(vref) <= len("dscore:")):  # O7 verified supply only
            raise ValidationError(
                "a D-Score verification_ref is required: unverified credits "
                "cannot enter the book",
                field="verification_ref", value=vref,
                constraint="non-empty dscore:<attestation> reference")
        mass_g = _pos_int(data, "mass_g")
        price = data.get("price_minor_per_kg")
        floor = _min_listing_price_minor_per_kg()
        if (not isinstance(price, int) or isinstance(price, bool)
                or price < floor):
            raise ValidationError(
                f"price_minor_per_kg is below the verified-supply floor ({floor})",
                field="price_minor_per_kg", value=price,
                constraint=f"int >= {floor}")
        # VR1: registry provenance. If this is Verra supply, require the fields
        # that make a retirement cross-referenceable on registry.verra.org —
        # a credit can only TRADE AS Verra if it carries genuine Verra
        # provenance (project id + serial + vintage).
        registry = str(data.get("registry", "")).lower()
        vcs_project_id = str(data.get("vcs_project_id", ""))
        vintage = str(data.get("vintage", ""))
        serial_number = str(data.get("serial_number", ""))
        methodology = str(data.get("methodology", ""))
        if registry == "verra":
            for f, val in (("vcs_project_id", vcs_project_id),
                           ("serial_number", serial_number),
                           ("vintage", vintage)):
                if not val:
                    raise ValidationError(
                        f"Verra supply requires '{f}' (cross-reference on "
                        "registry.verra.org)", field=f, value=val,
                        constraint="non-empty for registry=verra")
        elif registry and registry not in ("", "viridis"):
            raise ValidationError("unsupported registry", field="registry",
                                  value=registry, constraint="verra | viridis | (empty)")
        self._seq += 1
        cid = f"crd-{self._seq:06d}"
        credit = Credit(credit_id=cid, issuer=data["issuer"],
                        project_id=data["project_id"], listed_g=mass_g, retired_g=0,
                        price_minor_per_kg=price, verification_ref=vref,
                        listed_at=_utcnow(), registry=registry,
                        vcs_project_id=vcs_project_id, vintage=vintage,
                        serial_number=serial_number, methodology=methodology)
        self._credits[cid] = credit
        self._order.append(cid)
        return self._ok(credit.public())

    def _delist_credit(self, data: dict) -> dict:
        """O14: remove active supply from matching without erasing history."""
        credit_id = data.get("credit_id")
        if not isinstance(credit_id, str) or not credit_id:
            raise ValidationError("missing 'credit_id'", field="credit_id",
                                  value=credit_id, constraint="non-empty str")
        reason = data.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("missing delist reason", field="reason",
                                  value=reason, constraint="non-empty str")
        credit = self._credits.get(credit_id)
        if credit is None:
            raise ValidationError("unknown credit", field="credit_id",
                                  value=credit_id, constraint="must exist")
        if getattr(credit, "delisted_at", ""):
            return self._ok({**credit.public(), "duplicate": True})
        credit.delisted_at = _utcnow()
        credit.delist_reason = reason.strip()
        return self._ok({**credit.public(), "duplicate": False})

    # -- shared purchase machinery (O3/O6 math in ONE place) ------------- #
    def _sorted_book(self) -> List[Credit]:
        """O3 deterministic matching order: cheapest first, then listing order."""
        return sorted((self._credits[c] for c in self._order
                       if self._credits[c].available_g > 0
                       and not getattr(self._credits[c], "delisted_at", "")),
                      key=lambda cr: (cr.price_minor_per_kg,
                                      self._order.index(cr.credit_id)))

    @staticmethod
    def _fill_cost(take_g: int, price_minor_per_kg: int) -> int:
        return math.ceil((take_g / 1000.0) * price_minor_per_kg)  # O6

    def _require_buyer_purchase(self, data: dict) -> tuple:
        buyer = data.get("buyer")
        if not buyer or not isinstance(buyer, str):
            raise ValidationError("missing 'buyer'", field="buyer", constraint="non-empty str")
        purchase_id = data.get("purchase_id")
        if not purchase_id or not isinstance(purchase_id, str):
            raise ValidationError("missing 'purchase_id'", field="purchase_id",
                                  constraint="non-empty str")
        return buyer, purchase_id

    def _commit_purchase(self, *, purchase_id: str, buyer: str, mass_g: int,
                         fills: List[dict], total_cost: int, dry_run: bool,
                         budget_minor: Optional[int] = None) -> dict:
        content = {"purchase_id": purchase_id, "buyer": buyer, "mass_g": mass_g,
                   "fills": fills, "total_cost_minor": total_cost,
                   "retired_at": _utcnow()}
        certificate = {**content, "certificate_hash": _content_hash(content)}  # O4
        record = {**certificate, "duplicate": False, "dry_run": dry_run}
        if budget_minor is not None:
            record["budget_minor"] = budget_minor
        if dry_run:  # O10: nothing mutates, nothing is recorded
            return self._ok(record)
        for f in fills:  # O1/O2: bounded by listed_g via available_g
            self._credits[f["credit_id"]].retired_g += f["mass_g"]
        self._purchases[purchase_id] = record
        self._retired_by_buyer[buyer] = self._retired_by_buyer.get(buyer, 0) + mass_g
        return self._ok(record)

    def _buy_offset(self, data: dict) -> dict:
        buyer, purchase_id = self._require_buyer_purchase(data)
        dry_run = bool(data.get("dry_run", False))
        if not dry_run and purchase_id in self._purchases:  # O2 idempotent
            return self._ok({**self._purchases[purchase_id], "duplicate": True})
        mass_g = _pos_int(data, "mass_g")

        book = self._sorted_book()  # O3
        available = sum(cr.available_g for cr in book)
        if available < mass_g:
            raise ValidationError(
                f"insufficient verified supply: need {mass_g} g, book has {available} g",
                field="mass_g", value=mass_g, constraint=f"<= {available}")
        fills, remaining, total_cost = [], mass_g, 0
        for cr in book:
            if remaining == 0:
                break
            take = min(cr.available_g, remaining)
            cost = self._fill_cost(take, cr.price_minor_per_kg)  # O6
            fills.append({"credit_id": cr.credit_id, "project_id": cr.project_id,
                          "mass_g": take, "cost_minor": cost,
                          "verification_ref": cr.verification_ref,
                          # VR2: Verra provenance rides into the certificate so
                          # the retirement is cross-referenceable on Verra.
                          "registry": cr.registry,
                          "vcs_project_id": cr.vcs_project_id,
                          "vintage": cr.vintage,
                          "serial_number": cr.serial_number})
            total_cost += cost
            remaining -= take
        return self._commit_purchase(purchase_id=purchase_id, buyer=buyer,
                                     mass_g=mass_g, fills=fills,
                                     total_cost=total_cost, dry_run=dry_run)

    def _buy_offset_budget(self, data: dict) -> dict:
        """Money-denominated purchase (O9): retire the maximum cheapest-first
        mass whose exact O6 cost fits inside budget_minor. Built for callers
        whose restoration obligation is a currency amount (e.g. EnergyAI's
        RestorationLedger share), not a mass."""
        buyer, purchase_id = self._require_buyer_purchase(data)
        dry_run = bool(data.get("dry_run", False))
        if not dry_run and purchase_id in self._purchases:  # O2 idempotent
            return self._ok({**self._purchases[purchase_id], "duplicate": True})
        budget = _pos_int(data, "budget_minor")

        fills, total_cost, total_mass = [], 0, 0
        for cr in self._sorted_book():  # O3 order
            remaining_budget = budget - total_cost
            if remaining_budget <= 0:
                break
            if cr.price_minor_per_kg == 0:
                take = cr.available_g  # free verified supply: retire it all
            else:
                take = min(cr.available_g,
                           (remaining_budget * 1000) // cr.price_minor_per_kg)
                # O6 uses ceil; step down if rounding tipped us over budget
                while take > 0 and self._fill_cost(take, cr.price_minor_per_kg) > remaining_budget:
                    take -= 1
            if take <= 0:
                continue
            cost = self._fill_cost(take, cr.price_minor_per_kg)
            fills.append({"credit_id": cr.credit_id, "project_id": cr.project_id,
                          "mass_g": take, "cost_minor": cost,
                          "verification_ref": cr.verification_ref,
                          # VR2: Verra provenance rides into the certificate so
                          # the retirement is cross-referenceable on Verra.
                          "registry": cr.registry,
                          "vcs_project_id": cr.vcs_project_id,
                          "vintage": cr.vintage,
                          "serial_number": cr.serial_number})
            total_cost += cost
            total_mass += take
        if total_mass <= 0:  # O12
            cheapest = min((c.price_minor_per_kg for c in self._sorted_book()),
                           default=None)
            raise ValidationError(
                "budget_minor too small to retire a single gram of verified supply"
                + (f" (cheapest credit: {cheapest} minor/kg)" if cheapest is not None
                   else " (book is empty)"),
                field="budget_minor", value=budget, constraint="must afford >= 1 g")
        assert total_cost <= budget  # O9
        return self._commit_purchase(purchase_id=purchase_id, buyer=buyer,
                                     mass_g=total_mass, fills=fills,
                                     total_cost=total_cost, dry_run=dry_run,
                                     budget_minor=budget)

    def _settlement_batch(self, data: dict) -> dict:
        """O11: read-only cash-settlement summary for a buyer — the exact list
        + sums of retirements a human (Justin) settles in one bank transfer."""
        buyer = data.get("buyer")
        if not buyer or not isinstance(buyer, str):
            raise ValidationError("missing 'buyer'", field="buyer", constraint="non-empty str")
        since = data.get("since")
        if since is not None and not isinstance(since, str):
            raise ValidationError("'since' must be an ISO-8601 string", field="since",
                                  value=since, constraint="ISO-8601 str or absent")
        matches = [p for p in self._purchases.values()
                   if p["buyer"] == buyer
                   and (since is None or p["retired_at"] >= since)]
        matches.sort(key=lambda p: p["retired_at"])
        return self._ok({
            "buyer": buyer,
            "since": since,
            "purchases": [{"purchase_id": p["purchase_id"], "mass_g": p["mass_g"],
                           "total_cost_minor": p["total_cost_minor"],
                           "certificate_hash": p["certificate_hash"],
                           "retired_at": p["retired_at"]} for p in matches],
            "totals": {"purchases": len(matches),
                       "mass_g": sum(p["mass_g"] for p in matches),
                       "cost_minor": sum(p["total_cost_minor"] for p in matches)},
        })

    def _net_position(self, data: dict) -> dict:  # O5
        buyer = data.get("buyer")
        if not buyer or not isinstance(buyer, str):
            raise ValidationError("missing 'buyer'", field="buyer", constraint="non-empty str")
        emitted = data.get("emitted_g", 0)
        if not isinstance(emitted, (int, float)) or isinstance(emitted, bool) or emitted < 0:
            raise ValidationError("emitted_g must be >= 0 (from agent-compute-ledger)",
                                  field="emitted_g", value=emitted, constraint=">= 0")
        retired = self._retired_by_buyer.get(buyer, 0)
        return self._ok({"buyer": buyer, "emitted_g": emitted, "retired_g": retired,
                         "net_g": emitted - retired,
                         "carbon_accountable": retired >= emitted})

    def _verify_certificate(self, data: dict) -> dict:  # O4
        cert = data.get("certificate")
        if not isinstance(cert, dict) or "certificate_hash" not in cert \
                or "purchase_id" not in cert:
            raise ValidationError("certificate must be a dict with purchase_id + "
                                  "certificate_hash", field="certificate",
                                  value=cert, constraint="dict")
        content = {k: cert.get(k) for k in ("purchase_id", "buyer", "mass_g",
                                            "fills", "total_cost_minor", "retired_at")}
        hash_ok = _content_hash(content) == cert["certificate_hash"]
        ledger = self._purchases.get(cert["purchase_id"])
        on_ledger = bool(ledger and ledger["certificate_hash"] == cert["certificate_hash"])
        return self._ok({"valid": hash_ok and on_ledger,
                         "hash_ok": hash_ok, "on_ledger": on_ledger})

    def _book(self, data: dict) -> dict:
        items = [self._credits[c].public() for c in self._order]
        listed = sum(c["listed_g"] for c in items)
        retired = sum(c["retired_g"] for c in items)
        active_available = sum(
            c["available_g"] for c in items if c["listing_status"] == "active")
        delisted_available = sum(
            c["available_g"] for c in items if c["listing_status"] == "delisted")
        return self._ok({"count": len(items), "credits": items,
                         "totals": {"listed_g": listed, "retired_g": retired,
                                    "available_g": active_available,
                                    "delisted_available_g": delisted_available,
                                    "active_count": sum(
                                        c["listing_status"] == "active"
                                        for c in items),
                                    "delisted_count": sum(
                                        c["listing_status"] == "delisted"
                                        for c in items)}})  # O1/O14

    def _get_purchase(self, data: dict) -> dict:
        pid = data.get("purchase_id")
        rec = self._purchases.get(pid)
        if rec is None:  # O8
            raise ValidationError("unknown purchase", field="purchase_id", value=pid,
                                  constraint="must exist")
        return self._ok(rec)

    def _verify_retirement(self, data: dict) -> dict:  # O13 (x402-C C4)
        """Confirm a retirement (offset_ref) covers a required emission mass.

        This is the C4 check an x402-C validator calls to honor a carbon
        receipt's neutrality claim: does the referenced retirement actually
        retire at least `required_g` grams? Read-only; never mutates the book.
        """
        pid = data.get("purchase_id")
        rec = self._purchases.get(pid)
        if rec is None:  # O8
            raise ValidationError("unknown purchase", field="purchase_id",
                                  value=pid, constraint="must exist")
        required = data.get("required_g", 0)
        if isinstance(required, bool) or not isinstance(required, int) or required < 0:
            raise ValidationError("required_g must be a non-negative integer",
                                  field="required_g", value=required,
                                  constraint="int >= 0")
        retired = int(rec.get("mass_g", 0))
        covered = retired >= required
        return self._ok({
            "purchase_id": pid,
            "buyer": rec.get("buyer"),
            "retired_g": retired,
            "required_g": required,
            "covered": covered,                            # C4 verdict
            "shortfall_g": max(0, required - retired),
            "certificate_hash": rec.get("certificate_hash"),
            "credits": [{"credit_id": f["credit_id"],
                         "project_id": f.get("project_id"),
                         "mass_g": f["mass_g"]} for f in rec.get("fills", [])],
        })

    # ------------------------------------------------------------------ #
    # Restoration-project funding (P1-P6) — the supply side. The mission:
    # every ton the agent economy retires is revenue owed to a real,
    # verified restoration project. This layer names the projects and
    # attributes the proceeds; the CEO disburses the cash (no money moves
    # here, mirroring the buyer-side settlement_batch).
    # ------------------------------------------------------------------ #
    def _register_project(self, data: dict) -> dict:  # P1
        """Register a verified restoration project so retirements against its
        credits can be funded. verification_ref is required — only verified
        conservation can be funded, mirroring O7 on the supply side."""
        pid = data.get("project_id")
        if not pid or not isinstance(pid, str):
            raise ValidationError("missing 'project_id'", field="project_id",
                                  constraint="non-empty str")
        vref = data.get("verification_ref")
        if not vref or not isinstance(vref, str):
            raise ValidationError("verification_ref is required (verified "
                                  "restoration only)", field="verification_ref",
                                  value=vref, constraint="non-empty str")
        record = {
            "project_id": pid,
            "name": str(data.get("name", pid))[:200],
            "location": str(data.get("location", ""))[:200],
            "methodology": str(data.get("methodology", ""))[:120],
            "beneficiary": str(data.get("beneficiary", ""))[:200],
            "registry_ref": str(data.get("registry_ref", ""))[:120],
            "verification_ref": vref,
            "registered_at": _utcnow(),
        }
        existing = self._projects.get(pid)
        if existing is not None:  # P1 idempotent / conflict
            comparable = {k: existing[k] for k in record if k != "registered_at"}
            incoming = {k: record[k] for k in record if k != "registered_at"}
            if comparable == incoming:
                return self._ok({**existing, "duplicate": True})
            raise ValidationError("project_id already registered with different "
                                  "details", field="project_id", value=pid,
                                  constraint="immutable once registered")
        self._projects[pid] = record
        return self._ok({**record, "duplicate": False})

    def _attribute_by_project(self) -> Dict[str, dict]:
        """P2: exact per-project retired mass + gross proceeds, summed over
        every non-dry-run purchase fill. Pure."""
        agg: Dict[str, dict] = {}
        for rec in self._purchases.values():
            if rec.get("dry_run"):
                continue
            for f in rec.get("fills", []):
                proj = f.get("project_id")
                a = agg.setdefault(proj, {"retired_g": 0, "gross_proceeds_minor": 0,
                                          "retirements": 0, "credit_ids": set()})
                a["retired_g"] += int(f["mass_g"])
                a["gross_proceeds_minor"] += int(f.get("cost_minor", 0))
                a["retirements"] += 1
                a["credit_ids"].add(f["credit_id"])
        return agg

    def _project_view(self, proj: str, a: dict) -> dict:
        meta = self._projects.get(proj)
        return {
            "project_id": proj,
            "registered": meta is not None,
            "name": (meta or {}).get("name", proj),
            "beneficiary": (meta or {}).get("beneficiary", ""),
            "verification_ref": (meta or {}).get("verification_ref", ""),
            "retired_g": a["retired_g"],
            "gross_proceeds_minor": a["gross_proceeds_minor"],   # owed to project
            "retirements": a["retirements"],
            "credits": sorted(a["credit_ids"]),
        }

    def _project_funding(self, data: dict) -> dict:  # P2/P3/P5
        """Supply-side disbursement ledger: how much each restoration project
        has earned from retirements and is owed. Read-only — the CEO settles
        the actual payout. Pass project_id for one project, else all."""
        agg = self._attribute_by_project()
        one = data.get("project_id")
        if one is not None:
            a = agg.get(one, {"retired_g": 0, "gross_proceeds_minor": 0,
                              "retirements": 0, "credit_ids": set()})
            # P5: a registered-but-unfunded (or unknown) project -> zeros, no error
            return self._ok(self._project_view(one, a))
        projects = [self._project_view(p, agg[p]) for p in sorted(agg)]
        # Include registered projects that have no retirements yet (visibility).
        for p in sorted(self._projects):
            if p not in agg:
                projects.append(self._project_view(
                    p, {"retired_g": 0, "gross_proceeds_minor": 0,
                        "retirements": 0, "credit_ids": set()}))
        total_owed = sum(p["gross_proceeds_minor"] for p in projects)
        return self._ok({
            "count": len(projects),
            "total_owed_to_projects_minor": total_owed,   # P6 == sum purchases
            "currency": "USD",
            "projects": projects,
            "note": "gross_proceeds_minor is what each verified project has "
                    "earned from retirements and is owed; the CEO disburses.",
        })

    def _list_projects(self, data: dict) -> dict:  # P3 read-only
        return self._ok({"count": len(self._projects),
                         "projects": list(self._projects.values())})

    # ------------------------------------------------------------------ #
    # Automated, certified disbursement (D1-D7). Each project's accrued
    # proceeds are split — a configurable share withheld to seed-fund Viridis
    # Conservation, the remainder owed to the restoration project — and frozen
    # into a tamper-evident, content-addressed, hash-chained certificate. No
    # cash moves here (the CEO executes the Stripe transfers against the
    # certified batch); the automation is the deterministic split + certified
    # audit trail that removes the manual step.
    # ------------------------------------------------------------------ #
    @staticmethod
    def _split(gross: int, withhold_bps: int) -> tuple:  # D1/D2
        withhold = gross * withhold_bps // 10_000        # integer floor
        return withhold, gross - withhold                # payout = remainder

    def _schedule_lines(self, withhold_bps: int, only: Optional[str] = None):
        """The disbursement each ready project is owed NOW = accrued proceeds
        minus what has already been certified (delta accrual, D4)."""
        agg = self._attribute_by_project()
        pids = [only] if only else sorted(
            set(agg) | set(self._projects) | set(self._disbursed_by_project))
        lines, pending = [], []
        for proj in pids:
            gross = agg.get(proj, {}).get("gross_proceeds_minor", 0)
            already = self._disbursed_by_project.get(proj, 0)
            owed_now = gross - already
            meta = self._projects.get(proj)
            row = {"project_id": proj,
                   "registered": meta is not None,
                   "beneficiary": (meta or {}).get("beneficiary", ""),
                   "verification_ref": (meta or {}).get("verification_ref", ""),
                   "gross_accrued_minor": gross,
                   "already_certified_minor": already,
                   "owed_now_minor": owed_now}
            if meta is None:
                # D6: cannot certify a payout to an unverified project.
                row["status"] = "pending_registration"
                if owed_now > 0:
                    pending.append(row)
                continue
            withhold, payout = self._split(owed_now, withhold_bps)
            row.update({"viridis_withhold_minor": withhold,
                        "project_payout_minor": payout, "status": "ready"})
            lines.append(row)
        return lines, pending

    def _disbursement_schedule(self, data: dict) -> dict:  # D3 read-only
        bps = _viridis_withhold_bps()
        lines, pending = self._schedule_lines(bps, data.get("project_id"))
        ready = [l for l in lines if l["owed_now_minor"] > 0]
        return self._ok({
            "viridis_withhold_bps": bps,
            "viridis_withhold_pct": bps / 100.0,
            "currency": "USD",
            "ready_count": len(ready),
            "total_owed_now_minor": sum(l["owed_now_minor"] for l in ready),
            "total_viridis_withhold_minor": sum(l["viridis_withhold_minor"] for l in ready),
            "total_project_payout_minor": sum(l["project_payout_minor"] for l in ready),
            "lines": ready,
            "pending_registration": pending,   # funded but not yet fundable
            "note": "Automated split preview. certify_disbursement freezes it "
                    "into a certified batch; the CEO executes the transfers.",
        })

    def _certify_disbursement(self, data: dict) -> dict:  # D4/D5 exactly-once
        batch_id = data.get("batch_id")
        if not batch_id or not isinstance(batch_id, str):
            raise ValidationError("missing 'batch_id'", field="batch_id",
                                  constraint="non-empty str (idempotency key)")
        for d in self._disbursements:  # D4 idempotent
            if d["batch_id"] == batch_id:
                return self._ok({**d, "duplicate": True})
        bps = _viridis_withhold_bps()
        lines, _pending = self._schedule_lines(bps)
        payable = [l for l in lines if l["owed_now_minor"] > 0]  # ready only (D6)
        if not payable:
            raise ValidationError("nothing to disburse: no ready project has "
                                  "newly-accrued proceeds", field="batch_id",
                                  value=batch_id,
                                  constraint="at least one ready owed line")
        frozen = [{"project_id": l["project_id"],
                   "beneficiary": l["beneficiary"],
                   "verification_ref": l["verification_ref"],
                   "owed_minor": l["owed_now_minor"],
                   "viridis_withhold_minor": l["viridis_withhold_minor"],
                   "project_payout_minor": l["project_payout_minor"]}
                  for l in payable]
        total_withhold = sum(l["viridis_withhold_minor"] for l in payable)
        total_payout = sum(l["project_payout_minor"] for l in payable)
        prev = self._disbursements[-1]["certificate_hash"] if self._disbursements \
            else _DISBURSE_GENESIS
        content = {"batch_id": batch_id,
                   "period_index": len(self._disbursements),
                   "viridis_withhold_bps": bps,
                   "lines": frozen,
                   "total_viridis_withhold_minor": total_withhold,
                   "total_project_payout_minor": total_payout,
                   "total_disbursed_minor": total_withhold + total_payout,
                   "certified_at": _utcnow(), "prev_hash": prev}
        cert = {**content,
                "certificate_hash": hashlib.sha256(
                    (prev + _content_hash(content)).encode()).hexdigest()}
        # Commit: advance each project's cumulative certified amount (D4).
        for l in payable:
            self._disbursed_by_project[l["project_id"]] = \
                self._disbursed_by_project.get(l["project_id"], 0) + l["owed_now_minor"]
        self._disbursements.append(cert)
        return self._ok({**cert, "duplicate": False})

    def _verify_disbursement(self, data: dict) -> dict:  # D5 read-only
        prev = _DISBURSE_GENESIS
        for i, d in enumerate(self._disbursements):
            body = {k: v for k, v in d.items() if k != "certificate_hash"}
            recomputed = hashlib.sha256(
                (prev + _content_hash(body)).encode()).hexdigest()
            if d["prev_hash"] != prev or recomputed != d["certificate_hash"]:
                return self._ok({"valid": False, "broken_at_index": i})
            prev = d["certificate_hash"]
        # D7: whole-book conservation of disbursed proceeds.
        total_certified = sum(d["total_disbursed_minor"] for d in self._disbursements)
        total_attributed = sum(self._disbursed_by_project.values())
        return self._ok({"valid": True, "batches": len(self._disbursements),
                         "total_disbursed_minor": total_certified,
                         "conserved": total_certified == total_attributed})

    def _verra_supply(self, data: dict) -> dict:  # VR5 read-only
        """The tradeable Verra VCS book: verified credits carrying genuine
        Verra provenance, cross-referenceable on registry.verra.org. Read-only.
        Every retirement of this supply nets the project 85% and Viridis the
        15% marketplace take (VR3)."""
        creds = [c.public() for c in self._credits.values()
                 if c.registry == "verra"
                 and not getattr(c, "delisted_at", "")]
        return self._ok({
            "registry": "verra",
            "viridis_take_bps": _viridis_withhold_bps(),
            "count": len(creds),
            "available_g": sum(c["available_g"] for c in creds),
            "listed_g": sum(c["listed_g"] for c in creds),
            "retired_g": sum(c["retired_g"] for c in creds),
            "credits": creds,
            "note": "Verra VCS supply. Retirements reference the VCS project + "
                    "serial and are cross-referenceable on registry.verra.org; "
                    "the actual on-registry retirement is posted via the "
                    "operator's Verra account.",
        })

    def _verra_retirement_record(self, data: dict) -> dict:  # VR6 read-only
        """Generate the Verra-portal-ready retirement record(s) for a
        retirement made against Verra supply. The clearinghouse settles the
        sale + certifies it internally; this produces the exact record the
        Viridis Verra account submits on registry.verra.org to make the
        retirement final (portal today; auto-postable when Verra's transaction
        API goes live, July 2026+). Read-only.
        """
        pid = data.get("purchase_id")
        rec = self._purchases.get(pid)
        if rec is None:  # O8
            raise ValidationError("unknown purchase", field="purchase_id",
                                  value=pid, constraint="must exist")
        # Group the Verra fills by (vcs project, serial, vintage, methodology).
        groups: Dict[tuple, dict] = {}
        for f in rec.get("fills", []):
            if f.get("registry") != "verra":
                continue  # VR6: only Verra-registry credits produce records
            key = (f.get("vcs_project_id", ""), f.get("serial_number", ""),
                   f.get("vintage", ""))
            cr = self._credits.get(f["credit_id"])
            methodology = cr.methodology if cr else ""
            g = groups.setdefault(key, {"quantity_g": 0, "methodology": methodology,
                                        "credit_ids": set()})
            g["quantity_g"] += int(f["mass_g"])
            g["credit_ids"].add(f["credit_id"])
        if not groups:
            raise ValidationError(
                "no Verra-registry credits in this retirement — nothing to "
                "submit to Verra", field="purchase_id", value=pid,
                constraint="retirement must include registry=verra fills")
        records = []
        for (vcs, serial, vintage), g in groups.items():
            # 1 VCU = 1 tCO2e = 1,000,000 g. Report grams AND tonnes.
            records.append({
                "vcs_project_id": vcs,
                "serial_number": serial,
                "vintage": vintage,
                "methodology": g["methodology"],
                "quantity_g": g["quantity_g"],
                "quantity_tco2e": g["quantity_g"] / 1_000_000,
                "retirement_beneficiary": rec.get("buyer"),
                "retirement_reason": data.get(
                    "retirement_reason",
                    "voluntary offset — Viridis agent-economy retirement"),
                "retirement_date": _utcnow(),
                "internal_certificate_hash": rec.get("certificate_hash"),
                "public_cross_reference": (
                    "https://registry.verra.org/app/search/VCS/" + vcs
                    if vcs else "https://registry.verra.org/"),
            })
        total_g = sum(r["quantity_g"] for r in records)
        return self._ok({
            "purchase_id": pid,
            "registry": "verra",
            "account_holder": "Viridis Conservation (Verra account)",
            "submission_status": "ready_to_submit",
            "submission_channel": "verra_portal",   # -> "verra_api" when live
            "records": records,
            "total_quantity_g": total_g,
            "total_quantity_tco2e": total_g / 1_000_000,
            "note": "Submit these on registry.verra.org under the Viridis "
                    "account to finalize the on-registry retirement. When "
                    "Verra's transaction API (S&P Global next-gen registry, "
                    "2026) is live, this record auto-posts via the API adapter.",
        })

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {"credits": len(self._credits),
                       "purchases": len(self._purchases),
                       "retired_g": sum(c.retired_g for c in self._credits.values())}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Verified conservation credits matched to agent compute "
                           "emissions: cheapest-first, exactly-once retirement, "
                           "content-addressed offset certificates. The conservation "
                           "flywheel of the agent economy.",
            "capabilities": ["list_credit", "delist_credit",
                             "buy_offset", "buy_offset_budget",
                             "net_position", "verify_certificate", "book",
                             "get_purchase", "settlement_batch", "verify_retirement",
                             "register_project", "project_funding", "list_projects",
                             "disbursement_schedule", "certify_disbursement",
                             "verify_disbursement", "verra_supply", "verra_retirement_record"],
            "inputs": {"action": "str", "issuer": "str", "project_id": "str",
                       "mass_g": "int > 0", "price_minor_per_kg": "int >= 0",
                       "verification_ref": "str (required - verified supply only)",
                       "buyer": "str", "purchase_id": "str",
                       "budget_minor": "int > 0 (buy_offset_budget)",
                       "dry_run": "bool (optional; O10 no mutation)",
                       "since": "ISO-8601 str (optional, settlement_batch)",
                       "emitted_g": "number >= 0", "certificate": "dict"},
            "outputs": {"status": "str (ok|error)", "data": "dict"},
            "a2a_role": "offsets",
        }


def build(config: Optional[AgentConfig] = None) -> OffsetClearinghouseAgentCore:
    return OffsetClearinghouseAgentCore(config)
