"""Site input schema (``vef-site/0.1``): validation and normalization.

``normalize_site_inputs`` turns user data into one canonical, fully explicit form:

* every default is written out, with a ``*_basis`` field saying whether a value was
  supplied or defaulted, so a receipt is self-describing;
* numbers become Decimals quantized to 15 significant digits;
* patches are sorted by id and links by endpoint pair, so key order and list order in
  the caller's JSON cannot change the result (Invariant 1);
* unknown keys are rejected rather than silently ignored.

Normalization is idempotent: ``normalize(normalize(x)) == normalize(x)``.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Mapping

from ._decimal import ONE, ZERO, pinned, quantize_input
from .canonical import to_canonical_data
from .constants import (
    DEFAULT_AREA_RELATIVE_UNCERTAINTY,
    DEFAULT_COMPONENT_SIGMA,
    DEFAULT_NPP_RELATIVE_UNCERTAINTY,
    DEFAULT_SOIL_SIGMA,
    DEFAULT_SOIL_WEIGHT,
    DEFAULT_TEMPERATURE_SIGMA_K,
    HDFM_KERNEL_ALPHA,
    HDFM_KERNEL_SCALE_M,
    RAREFACTION_REFERENCE_OBSERVATIONS,
    RAREFACTION_REFERENCE_SPECIES,
    RAREFACTION_Z,
    RAREFACTION_Z_RANGE,
    SITE_SCHEMA,
)

MAX_PATCHES = 2000
MAX_LINKS = 20000
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

COMPONENTS = ("taxonomic", "productivity", "functional", "spectral")

SOIL_INDICATORS = {
    "soc_g_per_kg": (Decimal(0), Decimal(600)),
    "ph": (Decimal(2), Decimal(11)),
    "bd_kg_per_dm3": (Decimal("0.1"), Decimal("2.6")),
    "cec_cmol_per_kg": (Decimal(0), Decimal(200)),
    "n_g_per_kg": (Decimal(0), Decimal(50)),
}


class SiteInputError(ValueError):
    """Raised when site inputs fail validation. The message names the field."""


def _obj(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SiteInputError(f"{field}: expected an object")
    return value


def _only(value: Mapping[str, Any], allowed: set[str], field: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise SiteInputError(f"{field}: unknown key(s) {extra}; allowed {sorted(allowed)}")


def _text(value: Any, field: str, *, max_len: int = 200, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise SiteInputError(f"{field}: expected a non-empty string")
    text = value.strip()
    if len(text) > max_len:
        raise SiteInputError(f"{field}: longer than {max_len} characters")
    return text


def _num(value: Any, field: str, low: Decimal | None = None, high: Decimal | None = None,
         *, low_open: bool = False) -> Decimal:
    try:
        number = quantize_input(value, field=field)
    except ValueError as exc:
        raise SiteInputError(str(exc)) from exc
    if low is not None and (number < low or (low_open and number == low)):
        bound = f"> {low}" if low_open else f">= {low}"
        raise SiteInputError(f"{field}: must be {bound}, got {number}")
    if high is not None and number > high:
        raise SiteInputError(f"{field}: must be <= {high}, got {number}")
    return number


def _int(value: Any, field: str, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise SiteInputError(f"{field}: expected an integer")
    if isinstance(value, Decimal) and value == value.to_integral_value():
        value = int(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int):
        raise SiteInputError(f"{field}: expected an integer")
    if not low <= value <= high:
        raise SiteInputError(f"{field}: must be between {low} and {high}, got {value}")
    return value


def _sigma(spec: Mapping[str, Any], field: str, default: Decimal, key: str = "sigma",
           high: Decimal = ONE, basis_key: str = "sigma_basis") -> tuple[Decimal, str]:
    """Read an uncertainty and record whether it was supplied or defaulted.

    Accepts its own normalized output (value + basis) so normalization is idempotent.
    """
    stated = spec.get(basis_key)
    if stated not in (None, "default", "supplied"):
        raise SiteInputError(f"{field}.{basis_key}: expected 'default' or 'supplied'")
    if spec.get(key) is None:
        return default, "default"
    value = _num(spec[key], f"{field}.{key}", ZERO, high)
    if stated == "default":
        if value != default:
            raise SiteInputError(f"{field}.{basis_key}: 'default' requires {key} = {default}")
        return value, "default"
    return value, "supplied"


def _mode(spec: Mapping[str, Any], field: str, expected: str) -> None:
    if "mode" in spec and spec["mode"] != expected:
        raise SiteInputError(f"{field}.mode: expected {expected!r}, got {spec['mode']!r}")


def _component(name: str, raw: Any) -> dict[str, Any]:
    field = f"biodiversity.{name}"
    spec = _obj(raw, field)
    if name == "taxonomic" and "species_observed" in spec:
        _only(spec, {"mode", "species_observed", "observations", "z", "z_range",
                     "reference_species", "reference_observations", "source"}, field)
        _mode(spec, field, "rarefaction")
        species = _int(spec.get("species_observed"), f"{field}.species_observed", 1, 10_000_000)
        observations = _int(spec.get("observations"), f"{field}.observations", 1, 10_000_000_000)
        z = _num(spec.get("z", RAREFACTION_Z), f"{field}.z", Decimal("0.05"), Decimal("0.95"))
        z_range_raw = spec.get("z_range", list(RAREFACTION_Z_RANGE))
        if not isinstance(z_range_raw, (list, tuple)) or len(z_range_raw) != 2:
            raise SiteInputError(f"{field}.z_range: expected [low, high]")
        z_low = _num(z_range_raw[0], f"{field}.z_range[0]", Decimal("0.05"), Decimal("0.95"))
        z_high = _num(z_range_raw[1], f"{field}.z_range[1]", Decimal("0.05"), Decimal("0.95"))
        if not z_low <= z <= z_high:
            raise SiteInputError(f"{field}: z must lie inside z_range")
        return {
            "mode": "rarefaction",
            "species_observed": species,
            "observations": observations,
            "z": z,
            "z_range": [z_low, z_high],
            "reference_species": _num(spec.get("reference_species", RAREFACTION_REFERENCE_SPECIES),
                                      f"{field}.reference_species", ZERO, low_open=True),
            "reference_observations": _num(
                spec.get("reference_observations", RAREFACTION_REFERENCE_OBSERVATIONS),
                f"{field}.reference_observations", ZERO, low_open=True),
            "source": _text(spec.get("source"), f"{field}.source", max_len=1000, required=False),
        }
    _only(spec, {"mode", "value", "sigma", "sigma_basis", "source"}, field)
    _mode(spec, field, "normalized")
    if "value" not in spec:
        hint = " or species_observed + observations" if name == "taxonomic" else ""
        raise SiteInputError(f"{field}: supply a normalized value in [0, 1]{hint}")
    sigma, basis = _sigma(spec, field, DEFAULT_COMPONENT_SIGMA)
    return {
        "mode": "normalized",
        "value": _num(spec["value"], f"{field}.value", ZERO, ONE),
        "sigma": sigma,
        "sigma_basis": basis,
        "source": _text(spec.get("source"), f"{field}.source", max_len=1000, required=False),
    }


def _patches(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise SiteInputError("habitat.patches: expected a non-empty list")
    if len(raw) > MAX_PATCHES:
        raise SiteInputError(f"habitat.patches: at most {MAX_PATCHES} patches")
    patches: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw):
        field = f"habitat.patches[{index}]"
        spec = _obj(item, field)
        _only(spec, {"id", "area_ha", "verified", "condition", "habitat_class", "evidence"}, field)
        patch_id = _text(spec.get("id"), f"{field}.id", max_len=120)
        if patch_id in patches:
            raise SiteInputError(f"{field}.id: duplicate patch id {patch_id!r}")
        verified = spec.get("verified", False)
        if not isinstance(verified, bool):
            raise SiteInputError(f"{field}.verified: expected true or false")
        patches[patch_id] = {
            "id": patch_id,
            "area_ha": _num(spec.get("area_ha"), f"{field}.area_ha", ZERO, Decimal(10_000_000),
                            low_open=True),
            "verified": verified,
            "condition": _num(spec.get("condition", 1), f"{field}.condition", ZERO, ONE),
            "habitat_class": _text(spec.get("habitat_class"), f"{field}.habitat_class",
                                   required=False),
            "evidence": _text(spec.get("evidence"), f"{field}.evidence", max_len=1000,
                              required=False),
        }
    return [patches[key] for key in sorted(patches)]


def _links(raw: Any, patch_ids: set[str]) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SiteInputError("habitat.links: expected a list")
    if len(raw) > MAX_LINKS:
        raise SiteInputError(f"habitat.links: at most {MAX_LINKS} links")
    links: dict[tuple[str, str], dict[str, Any]] = {}
    for index, item in enumerate(raw):
        field = f"habitat.links[{index}]"
        spec = _obj(item, field)
        _only(spec, {"from", "to", "mode", "probability", "distance_m", "hdfm_linked", "source"},
              field)
        a = _text(spec.get("from"), f"{field}.from", max_len=120)
        b = _text(spec.get("to"), f"{field}.to", max_len=120)
        for end in (a, b):
            if end not in patch_ids:
                raise SiteInputError(f"{field}: unknown patch id {end!r}")
        if a == b:
            raise SiteInputError(f"{field}: a link must join two different patches")
        pair = (a, b) if a < b else (b, a)
        if pair in links:
            raise SiteInputError(f"{field}: duplicate link between {pair[0]!r} and {pair[1]!r}")
        modes = [key for key in ("probability", "distance_m", "hdfm_linked") if key in spec]
        if len(modes) != 1:
            raise SiteInputError(f"{field}: give exactly one of probability, distance_m, hdfm_linked")
        link: dict[str, Any] = {
            "from": pair[0],
            "to": pair[1],
            "source": _text(spec.get("source"), f"{field}.source", max_len=1000, required=False),
        }
        mode = {"probability": "probability", "distance_m": "distance",
                "hdfm_linked": "hdfm_linked"}[modes[0]]
        _mode(spec, field, mode)
        link["mode"] = mode
        if mode == "probability":
            link["probability"] = _num(spec["probability"], f"{field}.probability", ZERO, ONE,
                                       low_open=True)
        elif mode == "distance":
            link["distance_m"] = _num(spec["distance_m"], f"{field}.distance_m", ZERO,
                                      Decimal(1_000_000))
        else:
            if spec["hdfm_linked"] is not True:
                raise SiteInputError(f"{field}.hdfm_linked: must be true when given "
                                     "(omit the link when cores are not linked)")
            link["hdfm_linked"] = True
        links[pair] = link
    return [links[key] for key in sorted(links)]


def _soil(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    spec = _obj(raw, "soil")
    _only(spec, set(SOIL_INDICATORS) | {"indicators", "sigma", "sigma_basis", "source"}, "soil")
    values: Mapping[str, Any] = spec
    if "indicators" in spec:  # normalized form
        values = _obj(spec["indicators"], "soil.indicators")
        _only(values, set(SOIL_INDICATORS), "soil.indicators")
        clash = sorted(set(SOIL_INDICATORS) & set(spec))
        if clash:
            raise SiteInputError(f"soil: give indicators either inline or under 'indicators', not both {clash}")
    indicators = {}
    for key, (low, high) in SOIL_INDICATORS.items():
        if values.get(key) is not None:
            indicators[key] = _num(values[key], f"soil.{key}", low, high)
    if not indicators:
        raise SiteInputError(f"soil: supply at least one of {sorted(SOIL_INDICATORS)}")
    sigma, basis = _sigma(spec, "soil", DEFAULT_SOIL_SIGMA)
    return {
        "indicators": indicators,
        "sigma": sigma,
        "sigma_basis": basis,
        "source": _text(spec.get("source"), "soil.source", max_len=1000, required=False),
    }


def _thermodynamics(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    spec = _obj(raw, "thermodynamics")
    _only(spec, {"npp_gC_per_m2_yr", "npp_relative_uncertainty", "npp_uncertainty_basis",
                 "mean_temperature_K", "temperature_sigma_K", "temperature_uncertainty_basis",
                 "observation_channel", "source"}, "thermodynamics")
    npp_sigma, npp_basis = _sigma(spec, "thermodynamics", DEFAULT_NPP_RELATIVE_UNCERTAINTY,
                                  key="npp_relative_uncertainty",
                                  basis_key="npp_uncertainty_basis")
    t_sigma, t_basis = _sigma(spec, "thermodynamics", DEFAULT_TEMPERATURE_SIGMA_K,
                              key="temperature_sigma_K", high=Decimal(50),
                              basis_key="temperature_uncertainty_basis")
    channel = None
    if spec.get("observation_channel") is not None:
        ch = _obj(spec["observation_channel"], "thermodynamics.observation_channel")
        _only(ch, {"rho", "entropy_rate_bits_per_s", "source"}, "thermodynamics.observation_channel")
        channel = {
            "rho": _num(ch.get("rho"), "thermodynamics.observation_channel.rho", ZERO, ONE),
            "entropy_rate_bits_per_s": _num(ch.get("entropy_rate_bits_per_s"),
                                            "thermodynamics.observation_channel.entropy_rate_bits_per_s",
                                            ZERO, Decimal("1E60"), low_open=True),
            "source": _text(ch.get("source"), "thermodynamics.observation_channel.source",
                            max_len=1000, required=False),
        }
    return {
        "npp_gC_per_m2_yr": _num(spec.get("npp_gC_per_m2_yr"), "thermodynamics.npp_gC_per_m2_yr",
                                 ZERO, Decimal(5000)),
        "npp_relative_uncertainty": npp_sigma,
        "npp_uncertainty_basis": npp_basis,
        "mean_temperature_K": _num(spec.get("mean_temperature_K"),
                                   "thermodynamics.mean_temperature_K", Decimal(150), Decimal(400)),
        "temperature_sigma_K": t_sigma,
        "temperature_uncertainty_basis": t_basis,
        "observation_channel": channel,
        "source": _text(spec.get("source"), "thermodynamics.source", max_len=1000, required=False),
    }


@pinned
def normalize_site_inputs(raw: Any) -> dict[str, Any]:
    """Validate and normalize site inputs. Raises :class:`SiteInputError` on bad input."""
    data = _obj(to_canonical_data(_obj(raw, "site")), "site")
    _only(data, {"schema", "site_id", "name", "observed_at", "biodiversity", "habitat", "soil",
                 "thermodynamics", "weights", "vergecommon"}, "site")
    schema = data.get("schema", SITE_SCHEMA)
    if schema != SITE_SCHEMA:
        raise SiteInputError(f"schema: expected {SITE_SCHEMA!r}, got {schema!r}")

    bio = _obj(data.get("biodiversity"), "biodiversity")
    _only(bio, set(COMPONENTS), "biodiversity")
    missing = [name for name in COMPONENTS if name not in bio]
    if missing:
        raise SiteInputError(
            f"biodiversity: missing component(s) {missing}; the D-Score needs all four "
            "(supply a normalized value with its sigma when only a proxy is available)")

    habitat = _obj(data.get("habitat"), "habitat")
    _only(habitat, {"patches", "links", "kernel", "area_relative_uncertainty",
                    "area_uncertainty_basis"}, "habitat")
    patches = _patches(habitat.get("patches"))
    kernel_raw = _obj(habitat.get("kernel", {}), "habitat.kernel")
    _only(kernel_raw, {"alpha", "scale_m"}, "habitat.kernel")
    area_sigma, area_basis = _sigma(habitat, "habitat", DEFAULT_AREA_RELATIVE_UNCERTAINTY,
                                    key="area_relative_uncertainty",
                                    basis_key="area_uncertainty_basis")

    weights = _obj(data.get("weights", {}), "weights")
    _only(weights, {"soil"}, "weights")
    soil = _soil(data.get("soil"))
    soil_weight = _num(weights.get("soil", DEFAULT_SOIL_WEIGHT), "weights.soil", ZERO,
                       Decimal("0.9"))

    binding = None
    if data.get("vergecommon") is not None:
        vc = _obj(data["vergecommon"], "vergecommon")
        _only(vc, {"coop_id", "project_id"}, "vergecommon")
        coop_id = _text(vc.get("coop_id"), "vergecommon.coop_id", max_len=36)
        if not _UUID.match(coop_id):
            raise SiteInputError("vergecommon.coop_id: expected a UUID")
        binding = {"coop_id": coop_id.lower(),
                   "project_id": _text(vc.get("project_id"), "vergecommon.project_id", max_len=120)}

    observed_at = data.get("observed_at")
    return {
        "schema": SITE_SCHEMA,
        "site_id": _text(data.get("site_id"), "site_id", max_len=120),
        "name": _text(data.get("name"), "name", required=False),
        "observed_at": _text(observed_at, "observed_at", max_len=40) if observed_at is not None else None,
        "biodiversity": {name: _component(name, bio[name]) for name in COMPONENTS},
        "habitat": {
            "patches": patches,
            "links": _links(habitat.get("links"), {p["id"] for p in patches}),
            "kernel": {
                "alpha": _num(kernel_raw.get("alpha", HDFM_KERNEL_ALPHA), "habitat.kernel.alpha",
                              ZERO, Decimal(100), low_open=True),
                "scale_m": _num(kernel_raw.get("scale_m", HDFM_KERNEL_SCALE_M),
                                "habitat.kernel.scale_m", ZERO, Decimal(1_000_000), low_open=True),
            },
            "area_relative_uncertainty": area_sigma,
            "area_uncertainty_basis": area_basis,
        },
        "soil": soil,
        "thermodynamics": _thermodynamics(data.get("thermodynamics")),
        "weights": {"soil": soil_weight if soil is not None else ZERO},
        "vergecommon": binding,
    }
