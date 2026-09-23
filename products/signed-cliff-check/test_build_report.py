"""Invariant tests SC1–SC7 for the Signed Cliff Check builder."""
import hashlib
import json
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_report as br  # noqa: E402

SPEC = json.loads((HERE / "sample_solar_48e.json").read_text())
TODAY = date(2026, 9, 23)


def _build(facts=None, **kw):
    return br.build(SPEC["credit"], facts or dict(SPEC["facts"]),
                    "Client", "Proj", today=TODAY, **kw)


def test_sc1_amount_comes_from_engine():
    receipt, _ = _build()
    engine = br.load_engine()
    direct = br.run(engine, "48E", dict(SPEC["facts"]))
    assert receipt["result"]["credit_amount_usd"] == direct["credit_amount_usd"]
    # 2.4M x 30% (PWA met, no adders) — engine output, asserted for regression
    assert Decimal(direct["credit_amount_usd"]) == Decimal("720000.00")


def test_sc2_result_self_verifies():
    receipt, _ = _build()
    engine = br.load_engine()
    assert engine.verify_result(receipt["result"])["valid"]


def test_sc2_tampered_result_fails_verification():
    receipt, _ = _build()
    engine = br.load_engine()
    tampered = dict(receipt["result"], credit_amount_usd="999999.00")
    assert not engine.verify_result(tampered)["valid"]


def test_sc3_signature_recomputes():
    receipt, _ = _build()
    s = receipt["signature"]
    assert len(s["salt"]) == 64
    assert s["content_digest"] == receipt["result"]["audit_sha256"]
    assert hashlib.sha256((s["salt"] + s["content_digest"]).encode()).hexdigest() == s["commit_hash"]


def test_sc4_missing_facts_are_indeterminate_and_listed():
    facts = dict(SPEC["facts"]); facts.pop("pwa_met"); facts.pop("energy_community")
    receipt, page = _build(facts)
    assert receipt["calculation_status"] == "indeterminate"
    assert receipt["adder_upside"] == []
    assert "More facts needed" in page and "pwa_met" in page and "energy_community" in page
    assert "$720,000" not in page


def test_sc5_deadline_post_cutoff_solar():
    dl = _build()[0]["deadline_check"]
    assert dl["basis"] == "obbba_placed_in_service_deadline"
    assert dl["deadline"] == "2027-12-31"
    assert dl["days_remaining"] == (date(2027, 12, 31) - TODAY).days
    assert dl["planned_meets_deadline"] is True


def test_sc5_deadline_missed_and_pre_cutoff_and_non_solar():
    late = dict(SPEC["facts"], placed_in_service_date="2028-03-01")
    assert _build(late)[0]["deadline_check"]["planned_meets_deadline"] is False
    early = dict(SPEC["facts"], construction_begin_date="2026-06-01")
    dl = _build(early)[0]["deadline_check"]
    assert dl["basis"] == "continuity_safe_harbor" and dl["deadline"] == "2030-12-31"
    geo = dict(SPEC["facts"], technology="geothermal")
    assert _build(geo)[0]["deadline_check"] is None


def test_adder_sweep_uses_engine_and_is_positive():
    rows = _build()[0]["adder_upside"]
    assert [r["scenario"] for r in rows] == ["Domestic content bonus",
                                             "Energy community bonus", "Both adders"]
    both = rows[-1]
    assert Decimal(both["credit_amount_usd"]) == Decimal("1200000.00")  # 50%
    assert all(Decimal(r["delta_usd"]) > 0 for r in rows)


def test_sc6_deterministic_digest_varies_only_in_signature():
    a, _ = _build(); b, _ = _build()
    assert a["result"]["audit_sha256"] == b["result"]["audit_sha256"]
    assert a["signature"]["salt"] != b["signature"]["salt"]
    fixed = _build(salt="ab" * 32)[0]["signature"]["commit_hash"]
    assert fixed == _build(salt="ab" * 32)[0]["signature"]["commit_hash"]


def test_sc7_html_is_self_contained():
    _, page = _build()
    assert "<script" not in page.lower()
    assert not re.search(r"(src|href)=['\"]?https?://[^'\"]*\.(css|js)", page)
    assert "$720,000.00" in page and "Placed-in-service deadline" in page


def test_cli_writes_html_and_receipt(tmp_path):
    assert br.main([str(HERE / "sample_solar_48e.json"), "--out", str(tmp_path)]) == 0
    files = sorted(p.name for p in tmp_path.iterdir())
    assert any(f.endswith(".html") for f in files)
    assert any(f.endswith(".receipt.json") for f in files)
