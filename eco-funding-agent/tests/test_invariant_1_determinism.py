"""Invariant 1 - Determinism: same inputs and method version give byte-identical results
and receipts, regardless of key order, list order, number representation, process,
hash seed or repetition."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from decimal import Decimal

from conftest import ROOT, clone, random_site

from viridis_eco_funding import make_receipt, receipt_text, value_site, verify_receipt
from viridis_eco_funding.canonical import canonical_dumps, loads_decimal
from viridis_eco_funding.inputs import normalize_site_inputs


def test_repeated_runs_are_byte_identical(woodland_site):
    first_value = canonical_dumps(value_site(woodland_site))
    first_receipt = receipt_text(make_receipt(woodland_site))
    for _ in range(25):
        assert canonical_dumps(value_site(clone(woodland_site))) == first_value
        assert receipt_text(make_receipt(clone(woodland_site))) == first_receipt


def _shuffle(obj, rng):
    if isinstance(obj, dict):
        items = list(obj.items())
        rng.shuffle(items)
        return {k: _shuffle(v, rng) for k, v in items}
    if isinstance(obj, list):
        return [_shuffle(v, rng) for v in obj]
    return obj


def test_key_order_and_patch_order_do_not_matter(woodland_site):
    rng = random.Random(7)
    expected = receipt_text(make_receipt(woodland_site))
    for _ in range(20):
        shuffled = _shuffle(clone(woodland_site), rng)
        rng.shuffle(shuffled["habitat"]["patches"])
        rng.shuffle(shuffled["habitat"]["links"])
        for link in shuffled["habitat"]["links"]:
            if rng.random() < 0.5:
                link["from"], link["to"] = link["to"], link["from"]
        assert receipt_text(make_receipt(shuffled)) == expected


def test_number_representation_does_not_matter(woodland_site):
    as_text = json.dumps(woodland_site)
    from_floats = json.loads(as_text)
    from_decimals = loads_decimal(as_text)
    stringly = clone(woodland_site)
    stringly["thermodynamics"]["npp_gC_per_m2_yr"] = "620.000"
    stringly["habitat"]["patches"][0]["area_ha"] = Decimal("7.40")
    texts = {receipt_text(make_receipt(x)) for x in (from_floats, from_decimals, stringly)}
    assert len(texts) == 1


def test_normalization_is_idempotent(rng):
    for _ in range(200):
        site = random_site(rng)
        once = normalize_site_inputs(site)
        assert canonical_dumps(normalize_site_inputs(once)) == canonical_dumps(once)


def test_random_sites_are_deterministic(rng):
    for _ in range(100):
        site = random_site(rng)
        assert receipt_text(make_receipt(site)) == receipt_text(make_receipt(clone(site)))


def test_fresh_processes_with_different_hash_seeds_agree(woodland_site, tmp_path):
    site_path = tmp_path / "site.json"
    site_path.write_text(json.dumps(woodland_site))
    script = ("import json,sys; from viridis_eco_funding import make_receipt, receipt_text; "
              "print(receipt_text(make_receipt(json.load(open(sys.argv[1])))))")
    outputs = set()
    for seed in ("0", "1", "12345", "random"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT / "src")}
        out = subprocess.run([sys.executable, "-c", script, str(site_path)], env=env,
                             capture_output=True, text=True, check=True)
        outputs.add(out.stdout)
    outputs.add(receipt_text(make_receipt(woodland_site)) + "\n")
    assert len(outputs) == 1


def test_no_clock_network_or_randomness_in_valuation(woodland_site, monkeypatch):
    import time
    import urllib.request

    def forbidden(*_a, **_k):
        raise AssertionError("valuation must not touch clock, network or randomness")

    monkeypatch.setattr(time, "time", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(random, "random", forbidden)
    assert value_site(woodland_site)["method_version"] == "vef-method/0.1.0"


def test_caller_decimal_context_cannot_change_bytes(woodland_site):
    """Review finding: canonical bytes must not depend on the caller's decimal context."""
    from decimal import ROUND_DOWN, localcontext

    expected = receipt_text(make_receipt(woodland_site))
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 6, ROUND_DOWN
        hostile = make_receipt(woodland_site)
        assert receipt_text(hostile) == expected
        assert verify_receipt(hostile)["valid"]
    assert verify_receipt(hostile)["valid"]


def test_receipts_survive_plain_json_round_trip_at_extremes(woodland_site, rng):
    """Review finding: every published number must survive a JSON-double round trip."""
    cases = []
    for distance in (360000, 400000, 999999):
        site = clone(woodland_site)
        site["habitat"]["links"][1]["distance_m"] = distance
        cases.append(site)
    tiny = clone(woodland_site)
    tiny["habitat"]["patches"][0]["condition"] = "1e-299"
    tiny["habitat"]["patches"][1]["area_ha"] = "1.23456789012345e-300"
    cases.append(tiny)
    cases.extend(random_site(rng) for _ in range(150))
    for site in cases:
        wire = json.loads(json.dumps(json.loads(receipt_text(make_receipt(site)))))
        report = verify_receipt(wire)
        assert report["valid"], [c for c in report["checks"] if not c["ok"]]


def test_unicode_normalization_forms_are_equal(woodland_site):
    import unicodedata
    nfc, nfd = clone(woodland_site), clone(woodland_site)
    nfc["name"] = unicodedata.normalize("NFC", "Prairie de l'Érable")
    nfd["name"] = unicodedata.normalize("NFD", "Prairie de l'Érable")
    assert nfc["name"] != nfd["name"]
    assert receipt_text(make_receipt(nfc)) == receipt_text(make_receipt(nfd))
