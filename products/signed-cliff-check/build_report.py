#!/usr/bin/env python3
"""Viridis Signed Cliff Check — buyer-ready, signed 48E/45Y scenario report.

Turns one deterministic taxcredit-engine calculation into a deliverable a
human can hand to a CPA or lender: verdict, dollar amount, eligibility flags,
audit trail, official sources, an OBBBA wind/solar placed-in-service
deadline check, an adder-upside sweep, and a commit-reveal signature.

Stdlib only. No network. Never moves money or contacts anyone.

--- INVARIANTS ---
SC1  Every dollar figure comes from TaxCreditEngineCore; this module does no
     tax arithmetic of its own (it only compares engine outputs).
SC2  The primary result's audit_sha256 re-verifies with the engine's own
     verify_result() before the report is written; a mismatch aborts.
SC3  Signature: commit_hash == SHA-256(salt || audit_sha256), where salt is
     32 random bytes (hex). Anyone holding the receipt can recompute it.
SC4  Missing facts produce an INDETERMINATE report that lists the missing
     fields; the report never implies eligibility the engine did not grant.
SC5  The deadline check is only emitted for wind/solar and only states the
     rule and the date arithmetic; it never asserts construction began.
SC6  Same facts + same rule pack => identical audit_sha256 (determinism);
     only salt, commit_hash and generated_at differ between runs.
SC7  Output is a self-contained HTML file plus a JSON receipt; no external
     assets, scripts or network calls.
SC8  (v0.3) An Outcome Receipt (<stem>.orc.json, ORC v0.1) is written next to
     the receipt; its digest equals audit_sha256 and its commitment equals the
     report's commit_hash, so both formats verify identically.
SC9  (v0.3) Network use is opt-in only: without --register nothing leaves the
     machine. With --register the hosted gateway re-computes the result and
     registers the seal (ISSUED); any failure there is reported and never
     fails the build or alters the local report.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import importlib.util
import json
import secrets
import sys
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

FLEET_ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = FLEET_ROOT / "taxcredit-engine-agent" / "src"
VERIFY_ENDPOINT = "https://mcp.viridisconservation.com/taxcredit-engine/mcp"
VERIFY_PAGE_URL = "https://mcp.viridisconservation.com/cliff-check/verify"
OBBBA_BOC_CUTOFF = date(2026, 7, 4)
OBBBA_PIS_DEADLINE = date(2027, 12, 31)
NOTICE_2025_42 = "https://www.irs.gov/pub/irs-drop/n-25-42.pdf"


def load_engine():
    spec = importlib.util.spec_from_file_location(
        "viridis_taxcredit_pkg", ENGINE_SRC / "__init__.py",
        submodule_search_locations=[str(ENGINE_SRC)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["viridis_taxcredit_pkg"] = mod
    spec.loader.exec_module(mod)
    return mod.build()


def run(engine, credit: str, facts: dict) -> dict:
    out = asyncio.run(engine.process({"action": "calculate", "credit": credit,
                                      "facts": facts}))
    if out.get("status") != "ok":
        raise SystemExit(f"engine error: {out.get('message')} "
                         f"(field={out.get('field')})")
    return out["data"]


def sign(audit_sha256: str, salt: str | None = None) -> dict:          # SC3
    salt = salt or secrets.token_hex(32)
    commit = hashlib.sha256((salt + audit_sha256).encode()).hexdigest()
    return {"scheme": "sha256(salt||audit_sha256)", "salt": salt,
            "content_digest": audit_sha256, "commit_hash": commit}


def deadline_check(facts: dict, today: date) -> dict | None:           # SC5
    tech = str(facts.get("technology", "")).lower()
    if tech not in {"wind", "solar"} or "construction_begin_date" not in facts:
        return None
    boc = date.fromisoformat(str(facts["construction_begin_date"]))
    if boc <= OBBBA_BOC_CUTOFF:
        deadline = date(boc.year + 4, 12, 31)
        rule = ("Construction began on or before 2026-07-04, so the OBBBA "
                "placed-in-service deadline does not apply; the continuity "
                "safe harbor generally requires placement in service by the "
                "end of the fourth calendar year after construction began.")
        basis = "continuity_safe_harbor"
    else:
        deadline = OBBBA_PIS_DEADLINE
        rule = ("Construction began after 2026-07-04, so the facility must be "
                "placed in service by 2027-12-31 to qualify.")
        basis = "obbba_placed_in_service_deadline"
    pis = facts.get("placed_in_service_date")
    planned = date.fromisoformat(str(pis)) if pis else None
    return {"technology": tech, "construction_begin_date": boc.isoformat(),
            "basis": basis, "rule": rule, "deadline": deadline.isoformat(),
            "days_remaining": (deadline - today).days,
            "planned_placed_in_service": planned.isoformat() if planned else None,
            "planned_meets_deadline": (planned <= deadline) if planned else None,
            "caveat": ("Whether and when construction began is a legal "
                       "determination (physical work test under Notice "
                       "2025-42); this report takes the date as a supplied fact."),
            "source": NOTICE_2025_42}


def adder_sweep(engine, credit: str, facts: dict, base_amount: str) -> list:
    """48E only: what each bonus adder is worth, per the engine (SC1)."""
    if credit != "48E":
        return []
    rows = []
    for label, patch in [("Domestic content bonus", {"domestic_content_met": True}),
                         ("Energy community bonus", {"energy_community": True}),
                         ("Both adders", {"domestic_content_met": True,
                                          "energy_community": True})]:
        f = {**facts, **patch}
        if all(facts.get(k) == v for k, v in patch.items()):
            continue
        r = run(engine, credit, f)
        if r.get("calculation_status") != "eligible":
            continue
        delta = Decimal(r["credit_amount_usd"]) - Decimal(base_amount)
        rows.append({"scenario": label, "credit_amount_usd": r["credit_amount_usd"],
                     "percentage": r["rate"]["percentage"], "delta_usd": f"{delta:.2f}"})
    return rows


def build(credit: str, facts: dict, client: str, project: str,
          today: date | None = None, salt: str | None = None) -> tuple[dict, str]:
    engine = load_engine()
    today = today or datetime.now(timezone.utc).date()
    result = run(engine, credit, facts)
    status = result.get("calculation_status")
    check = engine.verify_result(deepcopy(result))                      # SC2
    if not check["valid"]:
        raise SystemExit("self-verification failed; refusing to sign")
    signature = sign(result["audit_sha256"], salt) if "audit_sha256" in result else None
    receipt = {
        "product": "viridis-signed-cliff-check", "product_version": "0.3.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "client": client, "project": project, "credit": credit,
        "calculation_status": status, "result": result,
        "deadline_check": deadline_check(facts, today),
        "adder_upside": (adder_sweep(engine, credit, facts,
                                     result["credit_amount_usd"])
                         if status == "eligible" else []),
        "signature": signature,
        "verify": {"endpoint": VERIFY_ENDPOINT, "tool": "verify_tax_credit_result",
                   "cost": "free", "how": "POST the 'result' object; expect valid=true",
                   "page": (VERIFY_PAGE_URL + "?c=" + signature["commit_hash"]
                            if signature else VERIFY_PAGE_URL)},
    }
    return receipt, render_html(receipt)


# ---------------------------------------------------------------- rendering
def _e(v) -> str:
    return html.escape(str(v))


def _money(v) -> str:
    return f"${Decimal(str(v)):,.2f}"


def render_html(r: dict) -> str:                                        # SC7
    res, status = r["result"], r["calculation_status"]
    tone = {"eligible": "ok", "ineligible": "bad"}.get(status, "warn")
    if status == "indeterminate":
        headline = "More facts needed"
        missing = [f["id"].split(":", 1)[1] for f in res.get("eligibility_flags", [])
                   if f["id"].startswith("required:")]
        body = ("<p>The engine will not guess. Supply these facts to get a "
                "signed figure:</p><ul>" +
                "".join(f"<li><code>{_e(m)}</code></li>" for m in missing) + "</ul>")
    else:
        headline = _money(res.get("credit_amount_usd", "0"))
        rate = res.get("rate", {})
        body = (f"<p class=sub>{_e(r['credit'])} · {_e(status)} · "
                f"{_e(rate.get('percentage', rate.get('amount_usd', '')))}"
                f"{'%' if 'percentage' in rate else ''} · {_e(res.get('tier', rate.get('rate_class','')))} rate</p>")
    flags = "".join(
        f"<tr><td class={ {'pass':'ok','fail':'bad'}.get(f['status'],'warn') }>"
        f"{ {'pass':'✔','fail':'✘'}.get(f['status'],'?') }</td><td>{_e(f['id'])}</td>"
        f"<td>{_e(f['detail'])}</td></tr>" for f in res.get("eligibility_flags", []))
    trail = "".join(
        f"<tr><td>{_e(t['rule_id'])}</td><td>{_e(t['formula'])}</td>"
        f"<td><code>{_e(json.dumps(t.get('operands', {})))}</code></td>"
        f"<td>{_money(t['result_usd']) if 'result_usd' in t else _e(t.get('result',''))}</td></tr>"
        for t in res.get("audit_trail", []))
    srcs = "".join(
        f"<li>{_e(s.get('authority', s.get('id', '')))} — "
        + (f"<a href='{_e(s['url'])}'>{_e(s.get('title', ''))}</a>" if s.get("url")
           else _e(s.get("title", "")))
        + (f" (accessed {_e(s['accessed_on'])})" if s.get("accessed_on") else "")
        + "</li>"
        for s in res.get("rule_pack", {}).get("sources", []))
    dl, dl_html = r.get("deadline_check"), ""
    if dl:
        meets = dl["planned_meets_deadline"]
        verdict = ("Planned date meets the deadline" if meets else
                   "Planned date MISSES the deadline" if meets is False else
                   "No planned placed-in-service date supplied")
        dl_html = (f"<section><h2>Placed-in-service deadline</h2>"
                   f"<p class='{'ok' if meets else 'bad' if meets is False else 'warn'} pill'>{_e(verdict)}</p>"
                   f"<p>{_e(dl['rule'])}</p><p><b>Deadline:</b> {_e(dl['deadline'])} "
                   f"({_e(dl['days_remaining'])} days from report date)</p>"
                   f"<p class=fine>{_e(dl['caveat'])} <a href='{_e(dl['source'])}'>Notice 2025-42</a></p></section>")
    up = "".join(f"<tr><td>{_e(u['scenario'])}</td><td>{_e(u['percentage'])}%</td>"
                 f"<td>{_money(u['credit_amount_usd'])}</td><td>+{_money(u['delta_usd'])}</td></tr>"
                 for u in r.get("adder_upside", []))
    up_html = (f"<section><h2>Adder upside</h2><table><tr><th>Scenario</th><th>Rate</th>"
               f"<th>Credit</th><th>vs. base</th></tr>{up}</table>"
               f"<p class=fine>Each row is a separate engine run with only that fact changed. "
               f"Qualifying for an adder requires its own documentation.</p></section>") if up else ""
    sig = r.get("signature") or {}
    pack = res.get("rule_pack", {})
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Signed Cliff Check — {_e(r['project'])}</title><style>
:root{{--bg:#fbfaf7;--fg:#1b2420;--dim:#5d6b64;--line:#dfe3dd;--ok:#1f7a4d;--bad:#b3261e;--warn:#9a6700}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1512;--fg:#e3ebe6;--dim:#93a39a;--line:#26322c;--ok:#4ade80;--bad:#f87171;--warn:#fbbf24}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:820px;margin:0 auto;padding:32px 16px}} h1{{font-size:14px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin:0}}
.big{{font-size:44px;font-weight:700;margin:8px 0 0}} .sub{{color:var(--dim);margin:4px 0 0}}
section{{border-top:1px solid var(--line);margin-top:28px;padding-top:12px}} h2{{font-size:17px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} td,th{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
code{{font:12px ui-monospace,Menlo,monospace;word-break:break-all}} .fine{{font-size:12px;color:var(--dim)}}
.pill{{display:inline-block;padding:2px 10px;border-radius:99px;border:1px solid currentColor;font-weight:600}}
.ok{{color:var(--ok)}} .bad{{color:var(--bad)}} .warn{{color:var(--warn)}} a{{color:inherit}}
@media print{{body{{background:#fff;color:#000}}}}</style></head><body><main>
<h1>Viridis Signed Cliff Check · {_e(r['client'])} · {_e(r['project'])}</h1>
<p class="big {tone}">{_e(headline)}</p>{body}
{dl_html}
{f'<section><h2>Eligibility checks</h2><table>{flags}</table></section>' if flags else ''}
{up_html}
{f'<section><h2>Audit trail</h2><table><tr><th>Rule</th><th>Formula</th><th>Operands</th><th>Result</th></tr>{trail}</table></section>' if trail else ''}
<section><h2>Signature &amp; verification</h2>
<p class=verify-line><b>Anyone can verify this report in 10 seconds:</b> open <a href='{_e(r['verify']['page'])}'>{_e(r['verify']['page'])}</a> and drop in the receipt file that came with it.</p><table>
<tr><td>Result digest (audit_sha256)</td><td><code>{_e(res.get('audit_sha256','—'))}</code></td></tr>
<tr><td>Input digest</td><td><code>{_e(res.get('input_sha256','—'))}</code></td></tr>
<tr><td>Rule pack</td><td>{_e(pack.get('version','—'))} · <code>{_e(pack.get('sha256','—'))}</code></td></tr>
<tr><td>Commitment</td><td><code>{_e(sig.get('commit_hash','—'))}</code></td></tr>
<tr><td>Salt</td><td><code>{_e(sig.get('salt','—'))}</code></td></tr></table>
<p class=fine>Check it by hand: SHA-256(salt + result digest) must equal the commitment. Agents can re-verify the full result free at
<code>{_e(r['verify']['endpoint'])}</code> (tool <code>verify_tax_credit_result</code>). Same facts under the same rule pack always give the same digest.</p></section>
{f'<section><h2>Sources</h2><ul>{srcs}</ul></section>' if srcs else ''}
<section class=cta data-cta=footer><p><b>Have a project facing the 12/31/2027 deadline?</b> <a href='{_e(VERIFY_PAGE_URL)}'>Get a signed check for your own project</a>.</p></section>
<section class=fine><p>{_e(res.get('disclaimer',''))}</p><p>Generated {_e(r['generated_at'])} · Viridis LLC · viridisconservation.com</p></section>
</main></body></html>"""


def to_orc(receipt: dict) -> dict:                                      # SC8
    sys.path.insert(0, str(FLEET_ROOT))
    from fleet_utils import orc
    return orc.from_cliff_check(receipt)


REGISTER_URL = "https://mcp.viridisconservation.com/internal/orc/seal-cliff-check"


def register(spec: dict, receipt: dict, url: str = REGISTER_URL,
             token: str | None = None, opener=None) -> dict | None:     # SC9
    """Ask the hosted gateway to replay + register this report's seal.
    Returns the ISSUED ORC on success, None on any failure (never raises)."""
    import os
    import urllib.request
    token = token if token is not None else os.environ.get("VIRIDIS_ADMIN_TOKEN", "")
    if not token:
        print("register: skipped (VIRIDIS_ADMIN_TOKEN not set)", file=sys.stderr)
        return None
    body = json.dumps({"credit": spec["credit"], "facts": spec["facts"],
                       "receipt": receipt}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "content-type": "application/json", "x-viridis-admin-token": token})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=20) as resp:
            out = json.loads(resp.read().decode())
        rc = out["receipt"]
        if rc["commitment"]["value"] != receipt["signature"]["commit_hash"]:
            raise ValueError("registry returned a different commitment")
        return rc
    except Exception as exc:
        print(f"register: failed ({type(exc).__name__}: {exc}); report is still "
              "valid at INTACT level", file=sys.stderr)
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("facts", help="JSON file: {credit, client, project, facts}")
    ap.add_argument("--out", default="out", help="output directory")
    ap.add_argument("--register", action="store_true",
                    help="opt-in: have the hosted gateway replay and register the "
                         "seal (needs VIRIDIS_ADMIN_TOKEN); off by default")
    a = ap.parse_args(argv)
    spec = json.loads(Path(a.facts).read_text())
    receipt, page = build(spec["credit"], spec["facts"], spec.get("client", "Client"),
                          spec.get("project", "Project"))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    stem = "".join(c if c.isalnum() else "-" for c in spec.get("project", "report")).strip("-").lower()
    (out / f"{stem}.html").write_text(page)
    (out / f"{stem}.receipt.json").write_text(json.dumps(receipt, indent=2))
    orc_receipt = to_orc(json.loads(json.dumps(receipt)))
    if a.register and receipt.get("signature"):
        issued = register(spec, receipt)
        if issued is not None:
            orc_receipt = issued
            print("register: ISSUED (sealed in the Viridis registry)")
    (out / f"{stem}.orc.json").write_text(json.dumps(orc_receipt, indent=2))
    print(f"{receipt['calculation_status']}: {out / (stem + '.html')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
