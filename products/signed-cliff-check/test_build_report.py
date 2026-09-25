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


# ---------------------------------------------------------------- growth loop (v0.2.0)
import shutil
import subprocess

import pytest

VERIFY_HTML = HERE / "verify.html"
NODE = shutil.which("node")


def _vcore_js():
    page = VERIFY_HTML.read_text()
    m = re.search(r'<script id="vcore">(.*?)</script>', page, re.S)
    assert m, "vcore script block missing"
    return m.group(1)


def _node(js_body: str, receipt_text: str = "") -> dict:
    prog = (_vcore_js() +
            "\nconst V = module.exports;\n"
            "const input = require('fs').readFileSync(0, 'utf8');\n"
            "(async () => { " + js_body + " })().catch(e => { console.log(JSON.stringify({error: String(e)})); });")
    out = subprocess.run([NODE, "-e", prog], input=receipt_text, capture_output=True,
                         text=True, timeout=30, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_gl1_only_network_call_is_same_origin_registry_lookup():
    page = VERIFY_HTML.read_text()
    for banned in ("XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource", "import("):
        assert banned not in page, banned
    assert page.count("fetch(") == 1                       # the single wrapper
    assert "fetch(u, o)" in page
    assert 'const REGISTRY_BASE = "/orc/v0/commitments/";' in page   # same-origin path
    assert "fetchImpl(REGISTRY_BASE + v.commit_hash" in page
    assert "issuer_proof" not in _vcore_js()               # never trusts receipt-supplied URLs
    assert not re.search(r"<script[^>]+src=", page, re.I)
    assert not re.search(r"<link[^>]+href=", page, re.I)
    assert not re.search(r"<(img|iframe)[^>]+src=", page, re.I)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_gl2_page_logic_verifies_real_receipt_and_rejects_tampering():
    receipt, _ = _build(salt="cd" * 32)
    text = json.dumps(receipt, indent=2)
    ok = _node("console.log(JSON.stringify(await V.verifyReceipt(input)));", text)
    assert ok["verified"] is True, ok
    assert ok["computed_digest"] == receipt["result"]["audit_sha256"]
    # tamper each bound field by one hex char / one digit
    def flip(h):
        return ("0" if h[0] != "0" else "1") + h[1:]
    for path in (("signature", "commit_hash"), ("signature", "salt"), ("result", "audit_sha256")):
        t = json.loads(text)
        t[path[0]][path[1]] = flip(t[path[0]][path[1]])
        bad = _node("console.log(JSON.stringify(await V.verifyReceipt(input)));", json.dumps(t))
        assert bad["verified"] is False, path
    t = json.loads(text)
    t["result"]["credit_amount_usd"] = "999999.00"
    bad = _node("console.log(JSON.stringify(await V.verifyReceipt(input)));", json.dumps(t))
    assert bad["verified"] is False and bad["checks"]["digest_recomputes"] is False


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_gl2_canonical_handles_non_ascii_like_python():
    facts = dict(SPEC["facts"])
    receipt, _ = br.build("48E", facts, "Café Énergie — Montréal", "Prøject ☀", today=TODAY,
                          salt="ef" * 32)
    ok = _node("console.log(JSON.stringify(await V.verifyReceipt(input)));",
               json.dumps(receipt, indent=2, ensure_ascii=False))
    assert ok["verified"] is True


def test_gl3_receipt_carries_verify_page_link():
    receipt, _ = _build()
    page = receipt["verify"]["page"]
    assert page.startswith(br.VERIFY_PAGE_URL)
    assert page.endswith("?c=" + receipt["signature"]["commit_hash"])
    assert receipt["product_version"] == "0.3.0"


def test_gl4_report_shows_verify_url_and_one_footer_cta():
    receipt, page = _build()
    assert receipt["verify"]["page"] in page
    assert page.count("data-cta=footer") == 1
    assert "<script" not in page.lower()


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_gl6_buy_button_only_when_payment_link_set():
    out = _node("console.log(JSON.stringify({empty: V.renderCta(''), set: V.renderCta('https://buy.stripe.com/test_x')}));")
    assert 'data-cta="buy"' not in out["empty"] and 'data-cta="intake"' in out["empty"]
    assert 'data-cta="buy"' in out["set"] and "https://buy.stripe.com/test_x" in out["set"]
    assert 'const PAYMENT_LINK_URL = ""' in VERIFY_HTML.read_text()


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_gl8_issuer_check_outcomes_with_mocked_registry():
    receipt, _ = _build(salt="ab" * 32)
    js = r"""
    const v = await V.verifyReceipt(input);
    const seen = [];
    const mk = (status, body) => async (u) => { seen.push(u); return {
      status, ok: status >= 200 && status < 300, json: async () => body }; };
    const good = {commitment: v.commit_hash, digest: v.digest, attestation: "computed",
                  registered_at: "2026-09-25T00:00:00+00:00", issuer: {name: "Viridis LLC"}};
    const out = {
      issued: await V.checkIssuer(v, mk(200, good)),
      missing: await V.checkIssuer(v, mk(404, {})),
      down: await V.checkIssuer(v, mk(503, {})),
      mismatch: await V.checkIssuer(v, mk(200, {...good, digest: "0".repeat(64)})),
      thrown: await V.checkIssuer(v, async () => { throw new Error("offline"); }),
      notIntact: await V.checkIssuer({...v, verified: false}, mk(200, good)),
      urls: seen };
    console.log(JSON.stringify(out));"""
    o = _node(js, json.dumps(receipt))
    assert o["issued"]["issued"] is True and o["issued"]["attestation"] == "computed"
    assert o["missing"]["reason"] == "not_registered"
    assert o["down"]["reason"] == "unavailable"
    assert o["mismatch"]["reason"] == "registry_mismatch" and o["mismatch"]["issued"] is False
    assert o["thrown"]["reason"] == "unavailable"
    assert o["notIntact"]["reason"] == "not_intact"
    assert all(u == "/orc/v0/commitments/" + receipt["signature"]["commit_hash"] for u in o["urls"])
    assert len(o["urls"]) == 4


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_gl9_page_verifies_orc_vectors_like_python():
    vec = json.loads((HERE.parents[1] / "docs/standards/orc/vectors.json").read_text())
    for case in vec["vectors"]:
        o = _node("console.log(JSON.stringify(await V.verifyReceipt(input)));",
                  json.dumps(case["receipt"], ensure_ascii=False))
        assert o["kind"] == "orc", case["name"]
        assert (1 if o["verified"] else 0) == case["expect_level"], case["name"]


# ---------------------------------------------------------------- v0.3.0 ORC output
def test_sc8_orc_file_written_and_equivalent(tmp_path):
    sys.path.insert(0, str(HERE.parents[1]))
    from fleet_utils import orc
    assert br.main([str(HERE / "sample_solar_48e.json"), "--out", str(tmp_path)]) == 0
    rc = json.loads(next(tmp_path.glob("*.receipt.json")).read_text())
    o = json.loads(next(tmp_path.glob("*.orc.json")).read_text())
    assert o["digest"]["value"] == rc["result"]["audit_sha256"]
    assert o["commitment"]["value"] == rc["signature"]["commit_hash"]
    assert orc.verify(o)["label"] == "INTACT"
    assert rc["product_version"] == "0.3.0"


def test_sc9_no_network_without_register(tmp_path, monkeypatch):
    import urllib.request
    def boom(*a, **k):
        raise AssertionError("network used without --register")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert br.main([str(HERE / "sample_solar_48e.json"), "--out", str(tmp_path)]) == 0


def test_sc9_register_success_failure_and_missing_token(tmp_path, monkeypatch):
    receipt, _ = _build(salt="ab" * 32)
    issued = dict(br.to_orc(json.loads(json.dumps(receipt))),
                  issuer_proof={"method": "registry", "url": "https://x/" + "0" * 64})

    class Resp:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self.body).encode()

    seen = {}
    def ok_opener(req, timeout):
        seen["headers"] = dict(req.headers); seen["url"] = req.full_url
        return Resp({"receipt": issued, "registered": {}})
    out = br.register(SPEC, receipt, token="tkn", opener=ok_opener)
    assert out["issuer_proof"]["method"] == "registry"
    assert seen["headers"]["X-viridis-admin-token"] == "tkn"
    assert seen["url"] == br.REGISTER_URL

    def down(req, timeout):
        raise OSError("offline")
    assert br.register(SPEC, receipt, token="tkn", opener=down) is None
    wrong = dict(issued, commitment={"value": "f" * 64})
    assert br.register(SPEC, receipt, token="tkn",
                       opener=lambda r, timeout: Resp({"receipt": wrong})) is None
    monkeypatch.delenv("VIRIDIS_ADMIN_TOKEN", raising=False)
    assert br.register(SPEC, receipt, opener=ok_opener) is None
