# Signed 48E Cliff Check

Buyer-ready, signed clean-energy tax-credit report built on `taxcredit-engine-agent`.
Stdlib only, no network. The builder never sends, publishes, or charges anything.

## Make a report
```bash
python3 build_report.py sample_solar_48e.json --out out/
# -> out/<project>.html (hand to buyer / CPA) + .receipt.json + .orc.json (keep)
# Opt-in: --register asks the hosted gateway to replay the math and register the
# seal (needs VIRIDIS_ADMIN_TOKEN). The report then verifies as ISSUED, not just INTACT.
```
Input JSON: `{credit: "48E"|"45Y", client, project, facts:{...}}`. The engine lists every
required fact. Missing facts produce an **INDETERMINATE** report that names what's
missing (no guessing).

## What the buyer gets
The buyer gets a verdict and dollar amount, every eligibility check, the OBBBA placed-in-service
deadline with days remaining (wind/solar), the dollar value of each 48E bonus adder, the audit
trail, official sources, and a commit-reveal signature:
`SHA-256(salt || audit_sha256) == commit_hash`, which the buyer can re-verify for free at the
hosted `verify_tax_credit_result` tool.

## Invariants (tested: `pytest test_build_report.py`, 22 tests)
SC1 amounts come only from the engine · SC2 the result self-verifies before signing ·
SC3 the signature recomputes · SC4 missing facts give an indeterminate report · SC5 the deadline
check applies only to wind/solar and never asserts that construction began · SC6 the digest is
deterministic · SC7 the HTML is self-contained · SC8 an ORC v0.1 copy is written with the same digest and commitment · SC9 there is no network access without `--register`. Verify page: GL1 the only network call is a same-origin registry lookup · GL2/GL9 the page's JS verifies exactly as Python does · GL8 issuer check outcomes · GL6 CTA.

## Scope limits (state these to buyers)
A scenario estimate, not tax advice. Whether construction began (the physical work test under
Notice 2025-42), domestic-content and energy-community qualification, prevailing wage and
apprenticeship compliance, and FEOC facts are all supplied by the buyer and must be
confirmed with their adviser.
