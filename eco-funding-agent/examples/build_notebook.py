"""Build and execute examples/woodland_valuation.ipynb: python examples/build_notebook.py"""
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell

cells = [
    md("""# Valuing one VergeCommon woodland project

This notebook walks one woodland project through the whole `viridis-eco-funding` flow: read the public project record, value the site, explain every number, seal a reproducible receipt, verify it, check monotonicity, and model a pledge pool.

**Synthetic data.** VergeCommon's public directory (`GET https://vergecommon.com/api/network`) listed zero opted-in co-ops on 2026-11-07, so the co-op record below is a **synthetic** record in the exact shape of the public API. The measurements are synthetic too, at realistic magnitudes for a Vermont northern-hardwood woodlot. Replace both with real data before drawing any conclusion.

**Labels.** Numbers derived from the intelligence bound are a **conjecture** and are marked as such. The complexity score is an ecological measure, not a price. Any real funding pool needs legal review before money moves; this notebook moves nothing."""),
    code("""import json, io
from pathlib import Path
from viridis_eco_funding import (value_site, explain_valuation, make_receipt, verify_receipt,
                                 receipt_text, simulate_pool, describe_method, METHOD_VERSION)
from viridis_eco_funding.canonical import canonical_dumps
from viridis_eco_funding.vergecommon import ReadOnlyVergeCommonClient, fetch_and_bind

DATA = Path("data")
site = json.loads((DATA / "woodland_site.json").read_text())
record = json.loads((DATA / "vergecommon_public_coop_SYNTHETIC.json").read_text())
print(METHOD_VERSION)
print(record["coop"]["name"])
for p in record["coop"]["projects"]:
    print(f"  {p['id']:18s} {p['kind']:9s} {p['status']:9s} {p['name']}")"""),
    md("""## 1. Bind the public project (read-only)

The hook uses the same public endpoint as VergeCommon's own `get_public_coop` MCP tool: a bodiless HTTPS **GET** to `/api/network?id=<uuid>`, with no credentials. Against the live service you would write `fetch_and_bind(site)`. Here the real client code runs against the synthetic record through an offline opener, so the request object it builds is the one it would send."""),
    code("""class OfflineResponse(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *exc): return False

sent = []
def offline_opener(request, timeout):
    sent.append((request.get_method(), request.full_url, request.data))
    return OfflineResponse(json.dumps(record).encode())

source = fetch_and_bind(site, ReadOnlyVergeCommonClient(opener=offline_opener))
print("request sent:", sent)
print(json.dumps({k: source[k] for k in ("project_name", "project_kind", "project_status", "record_sha256")}, indent=2))
print("trust:", source["trust"])"""),
    md("""## 2. Value the site

`value_site` is pure and deterministic. Every quantity carries its value, units, formula, inputs, uncertainty (sigma, 95 % interval, basis) and status: *published method*, *v0.1 method convention*, *input*, or *conjecture*."""),
    code("""valuation = value_site(site)
print(f"{'quantity':32s} {'value':>22s}  {'sigma':>18s}  units / status")
for name, q in valuation["quantities"].items():
    print(f"{name:32s} {canonical_dumps(q['value']):>22s}  {canonical_dumps(q['uncertainty']['sigma']):>18s}  {q['units'][:30]} / {q['status']}")
print()
print("warnings:", valuation["warnings"])"""),
    code("""print(valuation["explanation"])"""),
    md("""## 3. Explain one number end to end

`explain_valuation` gives the same walk-through an agent receives from the MCP tool. Here is the headline score and the conjecture-labelled capacity term."""),
    code("""steps = {s["quantity"]: s for s in explain_valuation(valuation)["steps"]}
for name in ("complexity_score", "complexity_capacity_bits_per_s"):
    s = steps[name]
    print(name, "| status:", s["status"])
    print("  formula:", s["formula"])
    print("  inputs: ", canonical_dumps(s["inputs"]))
    print("  value:  ", canonical_dumps(s["value"]), s["units"])
    print("  95% CI: ", canonical_dumps(s["uncertainty"]["ci95"]), "|", s["uncertainty"]["basis"])
    print("  notes:  ", s["notes"])"""),
    md("""## 4. Seal a reproducible receipt and verify it

The receipt holds the normalized inputs, the method version, the result and the bound public record, with SHA-256 digests over canonical JSON. Anyone can re-run it offline. The seal is a content digest, not an identity signature."""),
    code("""receipt = make_receipt(site, source=source)
print("seal digest:", receipt["seal"]["digest"])
print("inputs sha256:", receipt["inputs_sha256"])
report = verify_receipt(receipt, source_record=record)
print("valid:", report["valid"])
for c in report["checks"]:
    print(f"  {c['check']:18s} {'ok' if c['ok'] else 'FAIL'}  {c['detail']}")
print()
print("byte-identical on re-run:", receipt_text(receipt) == receipt_text(make_receipt(site, source=source)))

tampered = json.loads(json.dumps(json.loads(receipt_text(receipt))))
tampered["result"]["quantities"]["complexity_score"]["value"] = 70
print("tampered receipt valid:", verify_receipt(tampered)["valid"])"""),
    md("""## 5. Monotonicity: verify the stepping-stone patch

The `stepping-stone` old-field patch is listed but unverified, so it is not scored. Suppose an autumn 2027 survey verifies it and an HDFM corridor check confirms its link to the southern core. Invariant 2 guarantees the score cannot fall."""),
    code("""surveyed = json.loads(json.dumps(site))
for p in surveyed["habitat"]["patches"]:
    if p["id"] == "stepping-stone":
        p["verified"], p["evidence"] = True, "SYNTHETIC: autumn survey 2027"
for l in surveyed["habitat"]["links"]:
    if l.get("to") == "stepping-stone":
        l.pop("distance_m"); l["hdfm_linked"] = True
surveyed["observed_at"] = "2027-11-15"
after = value_site(surveyed)
for name in ("verified_area_ha", "eca_ha", "connectivity_fraction", "complexity_score"):
    print(f"{name:24s} {canonical_dumps(valuation['quantities'][name]['value']):>16s} -> {canonical_dumps(after['quantities'][name]['value'])}")
assert after["quantities"]["complexity_score"]["value"] >= valuation["quantities"]["complexity_score"]["value"]"""),
    md("""## 6. Model a pledge pool (simulation only)

Three pledges, a quarterly calendar starting 2026-10-01, and three release rules:
- **m1**: a verified, dated *receipt* showing K >= 7.0 releases 15 % (receipt-backed: it must be for this site, dated inside its quarter, and used once);
- **m2**: verified area >= 15 ha releases 20 % (no earlier than quarter 2);
- **o1**: an outcome-linked release of up to 40 %, in proportion to ECA growth from 12 to 15 ha.

The baseline receipt (observed 2026-10-31) lands in quarter 0 and the post-survey receipt (observed 2027-11-15) in quarter 4. A replay of the baseline receipt in quarter 6 is rejected. Releases plus remaining balance equal pledges in every quarter, and nothing is released without a met rule."""),
    code("""pool = json.loads((DATA / "woodland_pool.json").read_text())
observations = [
    {"id": "baseline-2026Q4", "period": 0, "receipt": receipt},
    {"id": "survey-2027Q4", "period": 4, "receipt": make_receipt(surveyed)},
    {"id": "replay-attempt", "period": 6, "receipt": receipt},
]
sim = simulate_pool(pool, observations)
print(f"{'quarter':>7s} {'pledged':>10s} {'released':>10s} {'to date':>10s} {'remaining':>10s}  events")
for p in sim["periods"]:
    ev = ", ".join(f"{e['rule_id']}:{e['amount_minor']}" for e in p["events"])
    print(f"{p['period']:>7d} {p['pledged_to_date_minor']:>10d} {p['released_this_period_minor']:>10d} {p['released_to_date_minor']:>10d} {p['remaining_minor']:>10d}  {ev}")
print()
for r in sim["rules"]:
    print(f"{r['id']:28s} {r['status']:9s} met_period={r['met_period']} effective_bps={canonical_dumps(r['effective_bps'])}")
print()
for o in sim["observations"]:
    print(f"observation {o['id']:16s} accepted={o['accepted']}  {o['reason']}")
print("invariants:", sim["invariants"])
print(sim["explanation"])"""),
    md("""## What this does and does not show

- K = 7.1 complexity-ha means that about 7.1 hectares of fully connected, reference-quality habitat would carry the same data-weighted connected area. It is not a price.
- The capacity term (about 2e25 bits/s) is a thermodynamic **ceiling** under a **conjecture**, not a measured information flow. Compute parity (about 58 kW at 300 K) restates it in watts.
- The receipt proves the numbers can be reproduced from these inputs. It does not prove the inputs are true. Here they are synthetic.
- See [LIMITS.md](../LIMITS.md) before using any number to make a decision."""),
]

nb = nbformat.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"}})
client = NotebookClient(nb, timeout=120, kernel_name="python3",
                        resources={"metadata": {"path": str(root / "examples")}})
client.execute()
for cell in nb.cells:  # strip volatile execution metadata so the file is stable in git
    cell.get("metadata", {}).pop("execution", None)
nbformat.write(nb, root / "examples" / "woodland_valuation.ipynb")
print("written")
