# Sol — build `disclosure-compiler` (Compliance Disclosure Compiler)

**This is the premium-seat unlock (Phase 2 of the revenue-growth system).** Three of the five seat bundles — `energy-seat` ($249), `climate-seat` ($149), `compliance-seat` ($149) — are dormant *only* because they include `disclosure-compiler`, which doesn't exist yet. Building it flips those bundles from coverage-disabled to coverage-ready and completes the energy/climate flagship. Context: `docs/deployment/REVENUE_GROWTH_SYSTEM.md`, `REVENUE_TOOLS_BUILD_LIST.md` #3.

Build it exactly like `taxcredit-engine` / `ghg-ledger` (your reference implementations): deterministic Decimal/stdlib core + thin MCP adapter + bundled, versioned, source-linked framework packs + letter-series invariant tests + content-addressed audit hash that composes with notary. Ship end-to-end: build → gateway → droplet (**20→21**) → submission pipeline → **verify the 3 seat plans go coverage-ready**.

## What it is
Turns "what regulation applies to me" (from `regulatory-radar`) into **"here is your filled disclosure draft"** — CSRD/ESRS, TNFD, SEC climate, IFRS S2 — by **deterministic templating**, not generation. Company facts + a `ghg-ledger` emissions result → a structured, cited, gap-flagged disclosure draft. Zero marginal cost; no inference in the serving path. It assembles from bundled framework templates; it never writes prose from a model.

## Spec invariants (DC1–DC8 — restate, implement, test each)
- **DC1 — Deterministic templating only.** The draft is assembled from bundled framework datapoint schemas + supplied facts. No LLM inference in the serving path; nothing is fabricated to fill a field.
- **DC2 — Framework packs bundled, versioned, source-linked.** `data/framework_packs.vX.json` holds each framework's required datapoints (id, label, requirement, expected input, source_id). Every draft carries `framework_pack.version` + `sha256` + the sources used (like taxcredit's rule_pack).
- **DC3 — Fail closed on missing datapoints.** A required datapoint with no supplied value renders as an explicit `MISSING: <datapoint>` gap, excluded from the "filled" set — never fabricated or defaulted. The draft reports a **completeness score** (filled / required).
- **DC4 — Full traceability.** Every filled datapoint cites its source — a supplied fact key or a `ghg-ledger` result field (with that result's factor-pack lineage). No unsourced numbers in a draft.
- **DC5 — Composes with `ghg-ledger`.** Accepts a `ghg-ledger` inventory result as the emissions input, **verifies its `audit_sha256`**, and carries that hash into the disclosure's provenance. A tampered or stale ghg result is rejected, not silently used.
- **DC6 — Content-addressed, deterministic audit.** `audit_sha256` over canonical(inputs + pack sha + result) + a `notary_payload` so a disclosure draft is stampable on the notary rail. No timestamp in hashed content — byte-reproducible. Provide `verify_result`.
- **DC7 — Applicability-scoped.** The draft states which framework(s) apply and why (fed from `regulatory-radar`); it won't emit a framework the caller isn't subject to unless `force: true` is explicitly set (and records that it was forced).
- **DC8 — Honest labeling.** Output is a **"disclosure draft for professional review,"** not a filed or assured report. Disclaimer + completeness score in every result and in `describe`.

## Tool surface
- `compile_disclosure(framework, company_facts, ghg_result?, options?)` → filled datapoints + `gaps[]` + completeness + per-datapoint citations + `audit_sha256`/`notary_payload`.
- `list_frameworks()` / `get_framework(id)` → supported frameworks, required datapoints, sources, pack sha.
- `verify_result(result)` → recompute audit + `framework_pack_current`.
- `describe_agent()` / health with version + pack digest.

## Bundled data — `data/framework_packs.vX.json` (enumerate; else DC3 gap / DC7 unsupported)
MVP frameworks, each a structured datapoint schema (not prose), source-linked:
- **ESRS E1 (Climate change)** — the flagship: Scope 1/2/3 gross emissions, intensity, targets, transition plan datapoints; maps directly onto `ghg-ledger` output.
- **SEC climate disclosure** — governance, material climate risks, GHG metrics (as applicable).
- **IFRS S2** — climate-related disclosures (governance/strategy/risk/metrics).
- **TNFD** — a starter nature-related datapoint set (LEAP-aligned), clearly labeled MVP.
Sources dated + URL'd (EFRAG ESRS, SEC final rule, ISSB IFRS S2, TNFD framework) + a non-authoritative `builder-spec` pin. Frameworks not in the pack → `unsupported` (DC7); datapoints not supplied → `MISSING` gaps (DC3).

## Composition with the rails (the flywheel)
- `regulatory-radar` → which frameworks apply (DC7).
- `ghg-ledger` → the verified emissions input (DC5).
- `notary` → stamps the draft as an auditable artifact (DC6).
- `metering` → priced call.
- *Optional future paid tier:* `narrative-engine` to render the templated datapoints into prose — a **separate metered tier**, never in the free/deterministic path (FIN2).

## Pricing / gate
Per doctrine, agent-market micro for adoption: **$2.00 / disclosure draft** (`PRICE_MINOR = 200`), 10 free/day. Capital comes from the **premium seats it unlocks**. Add `disclosure-compiler` to `payment_gate.py` `PRICE_MINOR` + the gate attach tuple, the deck maps (`ROLE`("revenue · compliance")/`PRICE_L`/`PRICE`(200)/footnote), and healthz.

## Tests (DC1–DC8, stdlib unittest) — assert exact behavior
ESRS E1 draft populated from a `ghg-ledger` result (Scope 1/2/3 fields mapped, cited); a missing required datapoint → `MISSING` gap + correct completeness score; a fabricated value never appears; a tampered `ghg_result` audit hash → rejected (DC5); an unsupported framework → `unsupported` (not a blank draft); `force:true` on a non-applicable framework is recorded; `verify_result` tamper-detection; deterministic re-run → identical `audit_sha256`. Wire into `run_fleet_tests.py`; full gate stays green.

## Ship checklist (end-to-end)
- [ ] Core + adapter + `mcp_server.py`; DC1–DC8 tests green; in `run_fleet_tests.py`
- [ ] `data/framework_packs.vX.json` — datapoint schemas + sources + sha
- [ ] Mounted `/disclosure-compiler/mcp`; healthz + version; payment gate $2.00; gate attach tuple + deck maps updated
- [ ] Build image, **tag rollback** (`viridis-stable:pre-disclosure-<date>`), `docker compose up -d --force-recreate gateway`; verify healthz **20→21**, all ok, gated set includes `disclosure-compiler`, persistence intact
- [ ] **Unlock the seats:** confirm `energy-seat` / `climate-seat` / `compliance-seat` flip from coverage-disabled → **coverage-ready** in `subscriptions.list_plans()` (they still wait on Stripe Price IDs, but coverage is now complete); `/seats` reflects it
- [ ] Submission pipeline: regen `deploy/glama/fleet_manifest.json` + add to `fleet_bridge.py` ROLE → push public repo → Glama Sync + Build & Release → Smithery `hartjustin6/disclosure-compiler` (Continue needs a 2nd click) → official registry `io.github.jdhart81/disclosure-compiler`

## Follow-ups (v0.2 — not blockers)
Full ESRS datapoint coverage; EU-taxonomy alignment; the optional `narrative-engine` prose tier (separate paid tier); XBRL/iXBRL export. Keep every framework change a new dated pack version with sources + bumped sha.
