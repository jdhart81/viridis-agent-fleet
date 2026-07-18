"""
green-router-agent — Core business logic.

THE RESTORATION FUNCTION OF THE INTELLIGENCE BOUND, AS A PRODUCT.
dI/dt <= P*D/(kB*T*ln2): every bit of intelligence an agent produces
dissipates energy. This mount makes any agent workload pay its entropy
bill through verified restoration — voluntarily, because we make it the
cheapest and most credible way to do it:

    quote_footprint  (FREE)  — honest joules/gCO2e for a workload, with
                               every assumption stated and the Landauer
                               context attached
    green_route      (FREE)  — rank compute backends by carbon for the
                               workload (quality routing lives on
                               /neurogenesis, NG7 — we teach the edge)
    certify          (PAID)  — compute the footprint, then RETIRE real
                               verified offsets through the fleet's own
                               clearinghouse (Verra provenance rides into
                               the certificate) — composed at the gateway,
                               fail-closed: no retirement, no certificate
    verify_certificate (FREE)— recompute the footprint from the stored
                               workload and cross-reference the retirement

Vendored engine: src/vg/thermo.py (verdigraph-neurogenesis thermodynamic
accountant; IEA grid model, Uptime PUE, disclosed per-query energy
estimates; DOI 10.5281/zenodo.20400274).

Fleet-standard interface: async process(), async health(), sync describe().
process() dispatches on "action" and NEVER raises on bad input.

--- INVARIANTS (spec-invariance contract) ---
GR1 PHYSICS HONESTY: every footprint is computed from DECLARED models
    (backend Wh/1k-token estimate, grid gCO2e/kWh, facility PUE) with
    sources stated in the response; estimates are labeled estimates;
    the Landauer floor is attached as context, never as a claim of
    proximity. No fabricated precision.
GR2 DETERMINISM: identical workload + identical model parameters always
    produce the identical footprint and retirement mass. No randomness,
    no network, no LLM in the serving path.
GR3 CERTIFICATION IS REAL RETIREMENT: a certificate reaches state
    "certified" ONLY after the offsets clearinghouse retirement succeeds
    (gateway composition, exactly-once per certificate via the
    clearinghouse's own O2 idempotency). Retirement failure voids the
    pending certificate and returns a structured error — fail-closed,
    never a paper promise.
GR4 MACHINE-VERIFIABLE: a certificate stores the workload snapshot and
    model parameters; verify_certificate recomputes the footprint from
    them and compares, and carries the clearinghouse purchase_id so any
    third party can independently run the x402-C verify_retirement
    check on /offsets/mcp. Free forever.
GR5 QUOTES AND VERIFICATION ARE FREE (rails doctrine): the standard
    spreads because checking it costs nothing; certification is the
    taxed transaction.
GR6 NO INVENTED CAPACITY: backends are the labeled defaults or
    caller-declared overrides (custom_backend with explicit
    wh_per_1k_tokens); green_route ranks only what exists and never
    silently substitutes a backend.
GR7 NEVER RAISES on bad input — structured error envelopes (fleet C1);
    every error teaches the fix (FT9/PB9 doctrine).
GR8 HONEST BOOKS: certificates persist (StateStore) with retired grams
    and clearinghouse cost; totals are derivable by anyone from
    list_certificates; retired mass reconciles against the clearinghouse
    ledger via the stored purchase ids.
GR9 BOUNDED: retirement per certificate is capped (CERT_MAX_G, default
    50 kg) so a mispriced workload can never obligate unbounded offset
    cost against a flat fee; over-cap requests get a structured error
    teaching split-or-enterprise.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ALL vendored imports module-level (PS8 gotcha: the gateway evicts src.*
# after adapter load; function-level relative imports crash at call time).
from src.vg.thermo import (BackendEnergy, FacilityModel, GridModel,
                           ThermodynamicAccountant, default_backends,
                           landauer_energy_per_bit)

logger = logging.getLogger(__name__)

SAFETY_FACTOR = 1.2       # retire 20% over the point estimate — stated, GR1
CERT_MAX_G = 50_000       # GR9: 50 kg CO2e cap per certificate
MIN_RETIRE_G = 1          # never certify zero grams


# --------------------------------------------------------------------------- #
# Fleet-standard base
# --------------------------------------------------------------------------- #
@dataclass
class AgentConfig:
    name: str
    version: str = "0.1.0"
    debug: bool = False


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentCore:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(config.name)

    async def health(self) -> dict:
        return {"status": "ok", "agent": self.config.name,
                "version": self.config.version, "timestamp": _utcnow(),
                "checks": {}}

    def _err(self, message: str, *, error_type: str = "Error",
             field: str = "", value: Any = None, constraint: str = "") -> dict:
        return {"status": "error", "error_type": error_type, "field": field,
                "value": value, "constraint": constraint, "message": message,
                "timestamp": _utcnow()}

    def _ok(self, data: Any = None) -> dict:
        return {"status": "ok", "data": data, "error": None,
                "timestamp": _utcnow()}


class ValidationError(ValueError):
    def __init__(self, message, field="", value=None, constraint=""):
        super().__init__(message)
        self.field, self.value, self.constraint = field, value, constraint


# --------------------------------------------------------------------------- #
class GreenRouterCore(AgentCore):
    """Carbon-accounted routing + real-retirement certification."""

    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config or AgentConfig(name="green-router-agent"))
        self._certificates: Dict[str, dict] = {}
        self._seq = 0
        self._quotes = 0

    # ------------------------------------------------------------------ #
    async def process(self, input_data: Any) -> dict:
        try:
            if not isinstance(input_data, dict):                    # GR7/C1
                return self._err("input_data must be a dict",
                                 error_type="ValidationError",
                                 field="input_data",
                                 value=type(input_data).__name__,
                                 constraint="input_data must be a dict")
            action = input_data.get("action", "describe")
            handler = {"quote_footprint": self._quote,
                       "green_route": self._route,
                       "certify": self._certify,
                       "verify_certificate": self._verify,
                       "list_certificates": self._list,
                       "describe": lambda _d: self._ok(self.describe()),
                       }.get(action)
            if handler is None:
                return self._err(
                    f"unknown action '{action}'",
                    error_type="ValidationError", field="action", value=action,
                    constraint="one of: quote_footprint, green_route, "
                               "certify, verify_certificate, "
                               "list_certificates, describe")
            return handler(input_data)
        except ValidationError as e:
            return self._err(str(e), error_type="ValidationError",
                             field=e.field, value=e.value,
                             constraint=e.constraint)
        except Exception as e:  # noqa: BLE001  (GR7)
            self.logger.exception("green-router process failed")
            return self._err(f"internal error: {e}", error_type="RuntimeError")

    # ---------------- footprint math (GR1/GR2) ------------------------- #
    @staticmethod
    def _accountant(workload: dict) -> tuple:
        """Build the (accountant, backend_id, params) for a workload.
        Deterministic; every override is caller-declared (GR6)."""
        backends = default_backends()
        custom = workload.get("custom_backend")
        if isinstance(custom, dict):
            bid = str(custom.get("id") or "").strip()
            wh = custom.get("wh_per_1k_tokens")
            if not bid or not isinstance(wh, (int, float)) or wh < 0:
                raise ValidationError(
                    "custom_backend needs {id, wh_per_1k_tokens >= 0, "
                    "note?} — you declare your own backend's energy, we "
                    "never invent it (GR6)",
                    field="custom_backend", constraint="id + wh_per_1k_tokens")
            backends[bid] = BackendEnergy(
                bid, float(wh),
                str(custom.get("note") or "caller-declared estimate"))
        backend_id = str(workload.get("backend_id") or "frontier_cloud")
        if backend_id not in backends:
            raise ValidationError(
                f"unknown backend '{backend_id}'",
                field="backend_id", value=backend_id,
                constraint=f"one of: {', '.join(sorted(backends))} — or "
                           "declare custom_backend with wh_per_1k_tokens")
        grid = GridModel(float(workload["grid_gco2e_per_kwh"]),
                         "caller-declared grid intensity") \
            if workload.get("grid_gco2e_per_kwh") is not None else GridModel()
        pue = workload.get("pue")
        facility = FacilityModel(float(pue), "caller-declared PUE") \
            if pue is not None else FacilityModel()
        acct = ThermodynamicAccountant(backends=backends, grid=grid,
                                       facility=facility)
        return acct, backend_id

    def _footprint(self, workload: Any) -> dict:
        if not isinstance(workload, dict):
            raise ValidationError(
                "workload is required: {backend_id? (frontier_cloud | "
                "efficient_cloud | local_small), total_tokens, "
                "output_tokens, calls? (default 1), success_score? [0,1], "
                "grid_gco2e_per_kwh?, pue?, custom_backend?}",
                field="workload", constraint="object")
        total = workload.get("total_tokens")
        out = workload.get("output_tokens")
        if not isinstance(total, int) or total < 0 \
                or not isinstance(out, int) or out < 0 or out > total:
            raise ValidationError(
                "total_tokens and output_tokens must be non-negative "
                "integers with output_tokens <= total_tokens "
                '(example: {"total_tokens": 3000, "output_tokens": 800})',
                field="workload", constraint="0 <= output <= total")
        calls = workload.get("calls", 1)
        if not isinstance(calls, int) or calls < 1 or calls > 10_000_000:
            raise ValidationError("calls must be an int in [1, 10000000]",
                                  field="calls", value=calls,
                                  constraint="1..10000000")
        score = workload.get("success_score", 1.0)
        acct, backend_id = self._accountant(workload)
        one = acct.account_inference(backend_id, total, out, float(score))
        be = acct.backends[backend_id]
        gco2e_total = one.carbon_gco2e * calls
        required_g = min(CERT_MAX_G + 1,           # cap check happens later
                         max(MIN_RETIRE_G,
                             math.ceil(gco2e_total * SAFETY_FACTOR)))
        return {
            "backend_id": backend_id,
            "calls": calls,
            "per_call": {
                "it_energy_joules": one.it_energy_joules,
                "facility_energy_joules": one.facility_energy_joules,
                "carbon_gco2e": one.carbon_gco2e,
                "useful_bits": one.useful_bits,
            },
            "total": {
                "facility_energy_joules": one.facility_energy_joules * calls,
                "carbon_gco2e": gco2e_total,
                "useful_bits": one.useful_bits * calls,
            },
            "retirement_required_g": required_g,
            "assumptions": {                                     # GR1
                "backend_energy": {"id": backend_id,
                                   "wh_per_1k_tokens": be.wh_per_1k_tokens,
                                   "note": be.note},
                "grid": {"gco2e_per_kwh": acct.grid.gco2e_per_kwh,
                         "source": acct.grid.source},
                "facility_pue": {"pue": acct.facility.pue,
                                 "source": acct.facility.source},
                "safety_factor": SAFETY_FACTOR,
                "honesty": ("estimates from disclosed per-query energy "
                            "figures, not telemetry; retirement mass is "
                            "ceil(gCO2e x safety_factor)"),
            },
            "physics_context": {
                "landauer_joules_per_bit_at_300K":
                    landauer_energy_per_bit(300.0),
                "note": ("dI/dt <= P*D/(kB*T*ln2): the Landauer floor is "
                         "the yardstick, not a proximity claim — the gap "
                         "IS the finding"),
            },
        }

    # ---------------- actions ------------------------------------------ #
    def _quote(self, data: dict) -> dict:
        fp = self._footprint(data.get("workload"))
        self._quotes += 1
        return self._ok({**fp,
                         "next_steps": {                          # GR5 funnel
                             "certify": ("call certify with the same "
                                         "workload — the fleet's own "
                                         "clearinghouse retires "
                                         f"{fp['retirement_required_g']} g "
                                         "of Verra-provenance verified "
                                         "offsets and you receive a "
                                         "machine-verifiable certificate"),
                             "route_greener": ("call green_route to rank "
                                               "backends by carbon for "
                                               "this workload"),
                         }})

    def _route(self, data: dict) -> dict:
        workload = data.get("workload")
        fp_base = self._footprint(workload)                       # validates
        acct, _ = self._accountant(workload)
        allowed = data.get("allowed_backends")
        ranking = []
        for bid, be in sorted(acct.backends.items()):
            if isinstance(allowed, list) and allowed and bid not in allowed:
                continue
            one = acct.account_inference(
                bid, workload["total_tokens"], workload["output_tokens"],
                float(workload.get("success_score", 1.0)))
            ranking.append({"backend_id": bid,
                            "wh_per_1k_tokens": be.wh_per_1k_tokens,
                            "carbon_gco2e_per_call": one.carbon_gco2e,
                            "note": be.note})
        ranking.sort(key=lambda r: r["carbon_gco2e_per_call"])
        if not ranking:
            raise ValidationError(
                "allowed_backends excluded every known backend",
                field="allowed_backends",
                constraint="include at least one known or custom backend")
        greenest = ranking[0]
        savings = (fp_base["per_call"]["carbon_gco2e"]
                   - greenest["carbon_gco2e_per_call"])
        return self._ok({
            "workload_backend": fp_base["backend_id"],
            "greenest": greenest,
            "ranking": ranking,
            "gco2e_saved_per_call_vs_workload_backend": max(0.0, savings),
            "note": ("ranked by carbon only (GR6); for quality-floor "
                     "routing use /neurogenesis/mcp route_task (NG7) and "
                     "bring the chosen backend here"),
        })

    def _certify(self, data: dict) -> dict:
        workload = data.get("workload")
        fp = self._footprint(workload)
        required = fp["retirement_required_g"]
        if required > CERT_MAX_G:                                 # GR9
            return self._err(
                f"workload needs {required} g CO2e retired — above the "
                f"{CERT_MAX_G} g per-certificate cap",
                error_type="over_cap", field="workload", value=required,
                constraint=f"split into batches <= {CERT_MAX_G} g, or "
                           "contact Viridis for an enterprise retirement")
        self._seq += 1
        cert_id = f"grc_{self._seq:06d}"
        snapshot = json.dumps(workload, sort_keys=True, default=str)
        record = {
            "certificate_id": cert_id,
            "status": "pending_retirement",                       # GR3
            "workload": json.loads(snapshot),
            "workload_sha256": hashlib.sha256(
                snapshot.encode()).hexdigest(),
            "footprint": fp,
            "retirement": {"required_g": required, "status": "pending"},
            "created_at": _utcnow(),
        }
        self._certificates[cert_id] = record
        return self._ok(dict(record))

    # Called by the GATEWAY composition after clearinghouse retirement.
    def finalize_certificate(self, cert_id: str, purchase: dict) -> dict:
        record = self._certificates.get(cert_id)
        if record is None:
            return {}
        record["status"] = "certified"
        record["retirement"] = {
            "status": "retired",
            "required_g": record["footprint"]["retirement_required_g"],
            "retired_g": purchase.get("mass_g"),
            "purchase_id": purchase.get("purchase_id"),
            "offset_cost_minor": purchase.get("total_cost_minor",
                                              purchase.get("total_cost")),
            "fills": purchase.get("fills"),
            "clearinghouse_content_hash": purchase.get("content_hash"),
            "independent_check": ("anyone: verify_retirement("
                                  f"'{purchase.get('purchase_id')}') on "
                                  "/offsets/mcp — x402-C"),
        }
        record["certified_at"] = _utcnow()
        return dict(record)

    def void_certificate(self, cert_id: str) -> None:             # GR3
        self._certificates.pop(cert_id, None)

    def _verify(self, data: dict) -> dict:
        cert_id = str(data.get("certificate_id") or "")
        record = self._certificates.get(cert_id)
        if record is None:
            raise ValidationError("unknown certificate_id",
                                  field="certificate_id", value=cert_id,
                                  constraint="must exist "
                                  "(list_certificates shows all)")
        recomputed = self._footprint(record["workload"])          # GR4/GR2
        matches = (recomputed["total"]["carbon_gco2e"]
                   == record["footprint"]["total"]["carbon_gco2e"]
                   and recomputed["retirement_required_g"]
                   == record["footprint"]["retirement_required_g"])
        return self._ok({
            "certificate_id": cert_id,
            "status": record["status"],
            "footprint_recomputation_matches": bool(matches),
            "recomputed_gco2e": recomputed["total"]["carbon_gco2e"],
            "stored_gco2e": record["footprint"]["total"]["carbon_gco2e"],
            "retirement": record.get("retirement"),
            "note": ("valid iff the recomputation matches AND the "
                     "clearinghouse confirms the purchase_id (GR4; run "
                     "the /offsets/mcp verify_retirement check for full "
                     "x402-C independence)"),
        })

    def _list(self, data: dict) -> dict:
        limit = max(1, min(200, int(data.get("limit") or 50)))
        certs = [dict(c) for c in list(self._certificates.values())[-limit:]]
        return self._ok({
            "count": len(self._certificates),
            "certified": sum(1 for c in self._certificates.values()
                             if c["status"] == "certified"),
            "total_retired_g": sum(
                (c.get("retirement") or {}).get("retired_g") or 0
                for c in self._certificates.values()),
            "total_offset_cost_minor": sum(
                (c.get("retirement") or {}).get("offset_cost_minor") or 0
                for c in self._certificates.values()),            # GR8
            "certificates": certs})

    # ------------------------------------------------------------------ #
    async def health(self) -> dict:
        h = await super().health()
        h["checks"] = {
            "quotes": self._quotes,
            "certificates": len(self._certificates),
            "certified": sum(1 for c in self._certificates.values()
                             if c["status"] == "certified"),
            "retired_g": sum(
                (c.get("retirement") or {}).get("retired_g") or 0
                for c in self._certificates.values())}
        return h

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": ("Carbon-accounted agent workloads: free honest "
                            "footprint quotes and carbon-ranked routing; "
                            "paid certificates backed by REAL verified "
                            "offset retirement through the fleet's own "
                            "clearinghouse (Verra provenance, x402-C "
                            "verifiable)."),
            "capabilities": ["quote_footprint", "green_route", "certify",
                             "verify_certificate", "list_certificates",
                             "describe"],
            "inputs": {"action": "str", "workload": "dict",
                       "allowed_backends": "list?",
                       "certificate_id": "str?", "limit": "int?"},
            "outputs": {"carbon_gco2e": "float", "retirement_required_g": "int",
                        "certificate_id": "str", "retirement": "dict"},
        }


def build(config: Optional[AgentConfig] = None) -> GreenRouterCore:
    return GreenRouterCore(config)
