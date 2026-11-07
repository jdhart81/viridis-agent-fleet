"""Pure, deterministic site valuation (method ``vef-method/0.1.0``).

``value_site(inputs)`` returns ecological complexity quantities. It never reads the
clock, the network, environment variables or random state; the same inputs and method
version always produce byte-identical canonical output (Invariant 1).

Every reported number is a *quantity* object that states its value, units, formula,
inputs, uncertainty (sigma, 95 % interval, basis) and status. Nothing here is a price or
a financial value; see LIMITS.md.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ._decimal import ONE, ZERO, pinned, publish, sqrt
from .bound import capacity
from .canonical import canonical_dumps
from .connectivity import equivalent_connected_area
from .constants import (
    CONJECTURE_LABEL,
    DSCORE_WEIGHTS,
    METHOD_VERSION,
    Z_95,
)
from .dscore import d_score, normalized_component, taxonomic_component
from .inputs import normalize_site_inputs
from .soil import soil_index

STATUS_PUBLISHED = "published method"
STATUS_CONVENTION = "v0.1 method convention"
STATUS_INPUT = "input"
STATUS_CONJECTURE = CONJECTURE_LABEL

COMPLEXITY_UNITS = "complexity-ha (D-weighted equivalent connected hectares)"


def _publish_tree(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return publish(obj)
    if isinstance(obj, dict):
        return {key: _publish_tree(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_publish_tree(value) for value in obj]
    return obj


@pinned
def _quantity(value: Decimal, units: str, formula: str, inputs: dict[str, Any], sigma: Decimal,
              basis: str, status: str, *, low: Decimal | None = ZERO,
              high: Decimal | None = None, notes: str = "") -> dict[str, Any]:
    lower = value - Z_95 * sigma
    upper = value + Z_95 * sigma
    if low is not None:
        lower = max(low, lower)
    if high is not None:
        upper = min(high, upper)
    return {
        "value": value,
        "units": units,
        "formula": formula,
        "inputs": inputs,
        "uncertainty": {"sigma": sigma, "ci95": [lower, upper], "basis": basis},
        "status": status,
        "notes": notes,
    }


@pinned
def _relative(sigma: Decimal, value: Decimal) -> Decimal:
    return sigma / value if value > ZERO else ZERO


@pinned
def evaluate(site: dict[str, Any]) -> dict[str, Any]:
    """Valuation of already-normalized inputs (see ``value_site``)."""
    warnings: list[str] = []
    q: dict[str, dict[str, Any]] = {}
    bio = site["biodiversity"]

    # --- D-Score components -------------------------------------------------------
    comps = {
        "taxonomic": taxonomic_component(bio["taxonomic"]),
        "productivity": normalized_component(bio["productivity"], "P"),
        "functional": normalized_component(bio["functional"], "F"),
        "spectral": normalized_component(bio["spectral"], "S"),
    }
    symbols = {"taxonomic": "T", "productivity": "P", "functional": "F", "spectral": "S"}
    for name, comp in comps.items():
        if comp["sigma_basis"] == "default":
            warnings.append(f"biodiversity.{name}: no sigma supplied; declared default used")
        if not comp["source"]:
            warnings.append(f"biodiversity.{name}: no source given")
        status = STATUS_PUBLISHED if comp.get("detail") else STATUS_INPUT
        q[f"component_{symbols[name]}"] = _quantity(
            comp["value"], "dimensionless [0, 1]", comp["formula"],
            comp.get("detail", {"source": comp["source"]}), comp["sigma"], comp["sigma_basis"],
            status, high=ONE)

    d_value, d_sigma = d_score(comps)
    q["d_score"] = _quantity(
        d_value, "dimensionless [0, 1]", "D = 0.30 T + 0.25 P + 0.25 F + 0.20 S",
        {"weights": dict(DSCORE_WEIGHTS), **{symbols[n]: c["value"] for n, c in comps.items()}},
        d_sigma, "components independent: sigma_D = sqrt(sum (w_i sigma_i)^2)",
        STATUS_PUBLISHED, high=ONE,
        notes="Hart, D-Score manuscript (MEE-26-04-332); data Zenodo 10.5281/zenodo.19543988")

    # --- Soil and data richness -----------------------------------------------------
    soil_detail = None
    weight = site["weights"]["soil"]
    if site["soil"] is not None:
        soil_detail = soil_index(site["soil"])
        if soil_detail["sigma_basis"] == "default":
            warnings.append("soil: no sigma supplied; declared default used")
        q["soil_index"] = _quantity(
            soil_detail["value"], "dimensionless [0, 1]",
            "G = mean of GSIP indicator scores (piecewise-linear response curves)",
            {"indicator_scores": soil_detail["indicator_scores"]}, soil_detail["sigma"],
            soil_detail["sigma_basis"], STATUS_CONVENTION, high=ONE)
        dr_value = (ONE - weight) * d_value + weight * soil_detail["value"]
        dr_sigma = sqrt(((ONE - weight) * d_sigma) ** 2 + (weight * soil_detail["sigma"]) ** 2)
        dr_formula, dr_status = "D* = (1 - w_soil) D + w_soil G", STATUS_CONVENTION
        dr_inputs: dict[str, Any] = {"D": d_value, "G": soil_detail["value"], "w_soil": weight}
    else:
        warnings.append("soil: no GSIP indicators supplied; D* equals the D-Score")
        dr_value, dr_sigma = d_value, d_sigma
        dr_formula, dr_status = "D* = D (no soil indicators supplied)", STATUS_PUBLISHED
        dr_inputs = {"D": d_value}
    q["data_richness"] = _quantity(dr_value, "dimensionless [0, 1]", dr_formula, dr_inputs,
                                   dr_sigma, "first-order propagation, terms independent",
                                   dr_status, high=ONE)

    # --- Habitat and connectivity -----------------------------------------------------
    habitat = site["habitat"]
    conn = equivalent_connected_area(habitat)
    rel_area = habitat["area_relative_uncertainty"]
    if habitat["area_uncertainty_basis"] == "default":
        warnings.append("habitat: no area uncertainty supplied; declared default used")
    if conn["unverified_patch_ids"]:
        warnings.append("habitat: unverified patches excluded from scoring: "
                        + ", ".join(conn["unverified_patch_ids"]))
    if not conn["verified_patch_ids"]:
        warnings.append("habitat: no verified patches; complexity score is zero")
    area = conn["verified_area_ha"]
    eca = conn["eca_ha"]
    area_basis = f"relative area uncertainty {rel_area} ({habitat['area_uncertainty_basis']})"
    q["verified_area_ha"] = _quantity(area, "ha", "A_v = sum of verified patch areas",
                                      {"verified_patches": conn["verified_patch_ids"]},
                                      rel_area * area, area_basis, STATUS_INPUT)
    q["eca_ha"] = _quantity(
        eca, "ha", "ECA = sqrt(sum_i sum_j a_i a_j p*_ij), a_i = area_i x condition_i",
        {"kernel": habitat["kernel"], "links_used": len(conn["links_used"])},
        rel_area * eca, area_basis + "; link probabilities treated as exact",
        STATUS_PUBLISHED, notes="Saura & Pascual-Hortal 2007; Saura et al. 2011; "
                                "link kernel from HDFM (exp(-alpha d / s))")
    fraction = min(ONE, eca / area) if area > ZERO else ZERO
    q["connectivity_fraction"] = _quantity(
        fraction, "dimensionless [0, 1]", "phi = min(1, ECA / A_v)",
        {"ECA": eca, "A_v": area}, ZERO,
        "not modeled: area uncertainty cancels in the ratio; link probabilities treated as exact",
        STATUS_PUBLISHED, high=ONE)

    # --- Headline: complexity score -------------------------------------------------------
    score = dr_value * eca
    score_sigma = sqrt((eca * dr_sigma) ** 2 + (dr_value * rel_area * eca) ** 2)
    q["complexity_score"] = _quantity(
        score, COMPLEXITY_UNITS, "K = D* x ECA", {"D*": dr_value, "ECA": eca}, score_sigma,
        "first-order: sigma_K^2 = (ECA sigma_D*)^2 + (D* sigma_ECA)^2", STATUS_CONVENTION,
        notes="habitat-hectares analogue (Parkes, Newell & Cheal 2003) with connectivity")

    # --- Intelligence-bound term (conjecture) ------------------------------------------------
    thermo = site["thermodynamics"]
    bound_detail = None
    if thermo is None:
        warnings.append("thermodynamics: no NPP / temperature supplied; "
                        "intelligence-bound term not computed")
    else:
        bound_detail = capacity(thermo, dr_value, area, eca)
        rel_npp = thermo["npp_relative_uncertainty"]
        rel_t = thermo["temperature_sigma_K"] / thermo["mean_temperature_K"]
        rel_dr = _relative(dr_sigma, dr_value)
        rel_power = sqrt(rel_npp ** 2 + rel_area ** 2)
        rel_bound = sqrt(rel_power ** 2 + rel_dr ** 2 + rel_t ** 2)
        if thermo["npp_uncertainty_basis"] == "default":
            warnings.append("thermodynamics: no NPP uncertainty supplied; declared default used")
        power = bound_detail["power_w"]
        bound = bound_detail["stated_bound_bits_per_s"]
        cap = bound_detail["capacity_bits_per_s"]
        channel_limited = bound_detail["limiting_term"] == "observation_channel"
        cap_rel = ZERO if channel_limited else rel_bound
        cap_basis = ("observation-channel parameters treated as exact" if channel_limited else
                     "first-order: NPP, area, D* and T terms independent; ECA scales with area")
        q["npp_power_w"] = _quantity(
            power, "W", "P = NPP x E_C x A_v / yr", {
                "NPP_gC_per_m2_yr": thermo["npp_gC_per_m2_yr"],
                "E_C_J_per_gC": "2.803e6 / (6 x 12.011) (glucose-equivalent)",
                "A_v_ha": area, "yr_s": "31557600 (Julian year)"},
            rel_power * power, "relative NPP and area uncertainties in quadrature", STATUS_INPUT)
        q["stated_bound_bits_per_s"] = _quantity(
            bound, "bits/s", "B = P D* / (k_B T ln 2)",
            {"P_W": power, "D*": dr_value, "T_K": thermo["mean_temperature_K"],
             "k_B_J_per_K": "1.380649e-23 (exact, SI 2019)"},
            rel_bound * bound, "first-order: P, D* and T terms independent", STATUS_CONJECTURE,
            notes="Intelligence bound (Hart), read on the maintenance/erasure side; conjecture")
        q["complexity_capacity_bits_per_s"] = _quantity(
            cap, "bits/s", "C = min(B, P (ECA / A_v) D* / (k_B T ln 2)[, rho B_obs])",
            {"limiting_term": bound_detail["limiting_term"], "B": bound,
             "connectivity_limited": bound_detail["connectivity_limited_bits_per_s"],
             "channel_limited": bound_detail["channel_limited_bits_per_s"]},
            cap_rel * cap, cap_basis, STATUS_CONJECTURE,
            notes="never exceeds B by construction (Invariant 3); conjecture")
        q["bound_utilization"] = _quantity(
            bound_detail["bound_utilization"], "dimensionless [0, 1]", "C / B",
            {"C": cap, "B": bound}, ZERO, "ratio of terms sharing P, D* and T; not modeled",
            STATUS_CONJECTURE, high=ONE)
        q["compute_parity_w_at_300k"] = _quantity(
            bound_detail["compute_parity_w_at_300k"], "W",
            "W_eq = C x k_B x 300 K x ln 2", {"C": cap, "T_ref_K": Decimal(300)},
            cap_rel * bound_detail["compute_parity_w_at_300k"], cap_basis, STATUS_CONJECTURE,
            notes="power at which a Landauer-limited computer at 300 K has the same bit-rate "
                  "ceiling as this site's complexity capacity; a units restatement, conjecture")

    uses_bound = bound_detail is not None
    result = {
        "method_version": METHOD_VERSION,
        "site_id": site["site_id"],
        "site_name": site["name"],
        "observed_at": site["observed_at"],
        "headline": {
            "complexity_score": q["complexity_score"]["value"],
            "units": COMPLEXITY_UNITS,
            "ci95": q["complexity_score"]["uncertainty"]["ci95"],
        },
        "quantities": q,
        "connectivity": {
            "verified_patch_ids": conn["verified_patch_ids"],
            "unverified_patch_ids": conn["unverified_patch_ids"],
            "links_used": conn["links_used"],
            "links_ignored": conn["links_ignored"],
        },
        "soil": None if soil_detail is None else {
            "indicator_scores": soil_detail["indicator_scores"],
            "curves": soil_detail["curves"],
            "weight": weight,
        },
        "uses_intelligence_bound": uses_bound,
        "labels": {"intelligence_bound": CONJECTURE_LABEL if uses_bound else "not used"},
        "warnings": warnings,
    }
    result = _publish_tree(result)
    result["explanation"] = _explanation(result)
    if uses_bound and CONJECTURE_LABEL not in result["explanation"]:
        raise AssertionError("Invariant 7: bound used without conjecture label")
    return result


@pinned
def value_site(raw_inputs: Any) -> dict[str, Any]:
    """Validate, normalize and value a site. Pure and deterministic."""
    return evaluate(normalize_site_inputs(raw_inputs))


def _fmt(value: Any) -> str:
    return canonical_dumps(value) if isinstance(value, Decimal) else str(value)


def _explanation(result: dict[str, Any]) -> str:
    q = result["quantities"]
    k = q["complexity_score"]
    lines = [
        f"Site {result['site_id']} has a complexity score K = {_fmt(k['value'])} {COMPLEXITY_UNITS} "
        f"(95% interval {_fmt(k['uncertainty']['ci95'][0])} to {_fmt(k['uncertainty']['ci95'][1])}).",
        f"K = D* x ECA: data richness D* = {_fmt(q['data_richness']['value'])} times the equivalent "
        f"connected area of verified habitat, ECA = {_fmt(q['eca_ha']['value'])} ha out of "
        f"{_fmt(q['verified_area_ha']['value'])} ha verified (connectivity fraction "
        f"{_fmt(q['connectivity_fraction']['value'])}).",
        f"The D-Score is {_fmt(q['d_score']['value'])} (published method: "
        "D = 0.30 T + 0.25 P + 0.25 F + 0.20 S).",
    ]
    if result["connectivity"]["unverified_patch_ids"]:
        lines.append("Unverified habitat is listed but not scored: "
                     + ", ".join(result["connectivity"]["unverified_patch_ids"]) + ".")
    if result["uses_intelligence_bound"]:
        c = q["complexity_capacity_bits_per_s"]
        b = q["stated_bound_bits_per_s"]
        lines.append(
            "The complexity-capacity term uses the intelligence bound, which is a conjecture, "
            "not an established law. Read on the maintenance/erasure side, the site's "
            f"photosynthetic power ({_fmt(q['npp_power_w']['value'])} W) sets a stated bound "
            f"B = {_fmt(b['value'])} bits/s; the connectivity-limited capacity is "
            f"C = {_fmt(c['value'])} bits/s (limiting term: {c['inputs']['limiting_term']}), "
            "which never exceeds B. These are thermodynamic ceilings, not measured information "
            f"flows. Compute parity: a Landauer-limited computer at 300 K would need "
            f"{_fmt(q['compute_parity_w_at_300k']['value'])} W for the same ceiling (conjecture).")
    else:
        lines.append("The intelligence-bound term was not computed (no NPP and temperature).")
    lines.append("This is an ecological complexity measure, not a price or a financial value. "
                 "Method " + result["method_version"] + "; see METHOD.md and LIMITS.md.")
    return " ".join(lines)
