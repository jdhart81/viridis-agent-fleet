# Viridis Revenue Tools — Build List for Sol
**Date:** 2026-07-12 · **Author:** Claude (research + spec) · **Builder:** Sol · **Deploy target:** `mcp.viridisconservation.com` gateway (DO droplet, docker compose)

## Thesis

Viridis is cash-starved but hosting is ~$0 (stdlib cores, no inference in the serving path, $6/mo droplet). That makes every viable revenue tool pure upside. The winning move is to build **deterministic, zero-marginal-cost services that (a) have proven willingness-to-pay and (b) compose with the trust-and-settlement rails we already run for free.** The free rails (identity, trust, escrow, metering, arbitration, notary, surety) are the moat; the priced tools are the revenue; each new priced tool drives more rail usage, and the free rails make our priced tools stickier than any standalone competitor. That is the flywheel — and it only gets born once.

## What the market is telling us (July 2026)

- **The agent economy is real and the rails are commoditizing.** x402 has cleared ~169M transactions / ~$50M volume across ~69k active agents; Stripe shipped Machine Payments + Tempo; Cloudflare and AWS embedded x402 micropayments at the edge; Nevermined does sub-cent ($0.001) billing. **Payment is solved — the money is in the *services agents pay for*, not the pipe.**
- **The economic layer is still "hostile to agents" — wide-open gaps.** Agents can transact but can't do their own **tax/accounting** (IRS has no guidance; every x402 settlement has "no reporting anchor connecting settlement to a taxpayer"; Basis AI raised $100M for agentic accounting), **reputation/credit** (banks now need to score agents — "reputation is the missing infrastructure layer"), **adjudicated escrow** (ERC-8183 evaluator pattern is emerging but immature), and **insurance/bonding** (immature). **Viridis already runs the substrate for all four.**
- **Climate/energy compute has budget-line WTP.** Carbon accounting software is a $20.8B → $110B (2034, 27.6% CAGR) market driven by Scope 3 + CSRD/ESRS mandates. Clean-energy tax credits (45V up to $3.28/kg H₂ for 2026 with PWA on a 4-tier carbon-intensity scale; modern 45Q commonly starts at $17/ton before PWA; 45Y/45X) are **deterministic IRS formulas** energy developers pay advisors real money to run. These tie straight to EnergyAI and the Viridis conservation lane.

## Design invariants (every tool must satisfy these)

1. **Zero marginal cost.** Pure deterministic compute on stdlib. No LLM inference in the serving path; no paid third-party APIs. All reference data (emission factors, tax tables, GREET tiers, reg text, schemas) is **bundled static data**, versioned in-repo.
2. **Fleet-standard shape.** Core + adapter + `mcp_server.py` per the template; mount at `/<tool>/mcp`; healthz + version; invariant tests (letter-series) that fail loud.
3. **Composes with the rails.** Every priced call should be meterable (metering agent), settleable (escrow), and provable (notary) so usage of a paid tool pulls the free rails with it.
4. **Priced via the existing gate.** 100 free calls/day → then per-call price or credit packs (`redeem_payment`), same PG9–11 loop already live. Rails stay free forever.
5. **Optional inference is a *separate paid tier*, pass-through metered** (FIN2 / Planet `activation_gate` precedent) — never in the free path.

---

## The build list

Ranked by (willingness-to-pay clarity × build speed × flywheel fit). `$` = est. price; `∆$0` = zero marginal cost confirmed.

### Tier 1 — Cash now (highest WTP, deterministic, days-to-build)

**1. `taxcredit-engine` — Clean-Energy Tax Credit Engine** ⭐ build first
Input facility/project params → scenario credit value + tier + eligibility flags + a defensible audit trail for 45Q, 45V, 45Y, 48E, and enumerated 45X components. Rates are date/path/PWA dependent: modern 45Q commonly starts at $17/metric ton and can reach 5×; 45V is inflation-adjusted annually (2026 maximum $3.28/kg with PWA). The engine accepts a verified 45VH2-GREET lifecycle result and tiers it; it does not replace GREET or tax advice. Official rule packs are bundled, dated, and source-linked.
- *Demand:* energy developers, project-finance, tax advisors run these constantly; today it's spreadsheets + $500/hr consultants.
- *Pricing:* $2–5/calc or B2B monthly seat. *∆$0.* *Composes:* metering + notary (stamped, auditable result). *Flywheel:* direct EnergyAI tie-in; anchors the energy vertical.

**2. `ghg-ledger` — GHG / Carbon Accounting Engine**
Activity data → CO₂e using bundled EPA/DEFRA/IPCC emission factors; Scope 1/2/3 with category rollups; CSRD/ESRS-shaped output.
- *Demand:* $20.8B→$110B market; Scope 3 + CSRD mandates are forcing every mid/large EU-touching company to compute this.
- *Pricing:* metered per calc + report packs. *∆$0* (factors bundled, pure arithmetic). *Composes:* compute-ledger + provenance (factor version lineage). *Flywheel:* conservation-core; feeds offset + nature-credit tools.

**3. `disclosure-compiler` — Compliance Disclosure Compiler**
Extends `regulatory-radar` from "what applies to me" → "here is your filled disclosure." Company facts + `ghg-ledger` output → rule-based CSRD/ESRS, TNFD, SEC climate, IFRS S2 disclosure drafts (deterministic templating, not generative).
- *Demand:* compliance is a budgeted line item; the pain is assembling the report, not knowing the rule.
- *Pricing:* per-report / subscription. *∆$0.* *Composes:* regulatory-radar + ghg-ledger. *Optional* premium narrative tier via metered inference later.

### Tier 2 — Agent-economy infrastructure (recurring, moat, pure flywheel)

**4. `agent-books` — Agent Tax & Bookkeeping** ⭐ biggest open gap
Ingests x402 / Stripe / Tempo settlement logs → double-entry ledger, deterministic revenue/expense classification, jurisdiction-aware tax estimate, and a **"reporting anchor"** linking each atomic settlement to a taxpayer + filing-ready summaries (1099-style).
- *Demand:* the single most-cited unsolved problem in agent finance; Basis AI's $100M raise proves the WTP; IRS guidance vacuum = first-mover land.
- *Pricing:* metered ingest + monthly. *∆$0* (rules, not inference). *Composes:* metering + compute-ledger (we already meter every fleet call — dogfood it). *Flywheel:* every agent that earns money needs this monthly = recurring revenue + rail lock-in.

**5. `agent-credit` — Agent Reputation & Credit Score**
Turns `trust-oracle` + `erc8004-bridge` feedback into a bank-grade, decay-weighted creditworthiness score + a signed, content-addressed attestation others can pull.
- *Demand:* "reputation is the missing infrastructure layer of agentic finance"; banks/counterparties now gate balance-sheet access on agent reputation.
- *Pricing:* per-pull / API seat. *∆$0.* *Composes:* trust + identity + erc8004. *Flywheel:* the more agents transact on our rails, the better our scores → the more valuable the pull.

**6. `escrow-pro` — Adjudicated Escrow & Evidence (ERC-8183 evaluator)**
Premium tier over free escrow: quality-adjudicated release (ERC-8183 Evaluator pattern), SLA-evidence bundles, dispute-resolution packets. Free escrow stays free; adjudication + evidence is paid.
- *Demand:* ERC-8183 programmable-escrow-with-evaluator is emerging but immature — we already have escrow + arbitration + notary to assemble it.
- *Pricing:* bps take-rate on adjudicated value or per-dispute. *∆$0.* *Composes:* escrow + arbitration + notary (this IS the composition demo we already had queued).

**7. `surety-premium` — Bonding / Agent-Transaction Insurance**
Monetize the existing `surety` agent: risk-scored bond issuance + premium pricing; coverage for agent-to-agent transaction failure.
- *Demand:* insurance for agent txns explicitly flagged as an immature gap.
- *Pricing:* premium = f(risk score, coverage). *∆$0.* *Composes:* surety + agent-credit (score sets premium) + arbitration (claims).

### Tier 3 — Developer / volume tools (broad demand, deterministic, cheap)

**8. `data-guard` — Validation & PII Redaction**
Validate JSON/CSV against schema, dedupe, regex/rule-based PII detection + redaction, format normalization. No inference.
- *Pricing:* per-MB or per-call, free tier. *∆$0.* *Flywheel:* high call volume feeds metering + drives discovery.

**9. `fincalc` — Deterministic Finance Calculators**
DCF, MACRS depreciation, amortization/loan schedules, bond/yield math, unit economics. Embeddable, high-volume.
- *Pricing:* cheap metered. *∆$0.*

**10. `timestamp-notary` — Verifiable Timestamp / Content-Addressing**
Content-addressed hashes + commit-reveal timestamp proofs + merkle inclusion. Extends `notary`.
- *Pricing:* per-proof (fractions of a cent, x402-native). *∆$0.* *Flywheel:* agents need audit trails → volume.

### Tier 4 — Viridis-lane strategic (conservation flywheel, emerging markets)

**11. `nature-credit` — Biodiversity / Nature-Credit Valuation**
D-Score-style biodiversity valuation + TNFD-aligned nature-credit issuance/verification. Builds on the D-Score agent + offset-clearinghouse.
- *Pricing:* per-valuation / issuance fee. *∆$0.* *Flywheel:* extends the conservation IP into a nascent, high-narrative market.

**12. `offset-integrity` — Carbon-Offset Integrity Scorer**
Score offset projects for additionality / permanence / leakage on a deterministic rubric; buyers pay to screen before purchase.
- *Pricing:* per-screen. *∆$0.* *Composes:* offset-clearinghouse + provenance.

---

## Recommended build order for Sol

1. **`taxcredit-engine`** — clearest dollar WTP, EnergyAI tie-in, small deterministic surface. Ship first for a real invoice.
2. **`agent-books`** — biggest open gap + recurring revenue; dogfood on our own metering data.
3. **`ghg-ledger`** — largest TAM; unlocks `disclosure-compiler`, `offset-integrity`, `nature-credit`.
4. **`agent-credit`** + **`escrow-pro`** + **`surety-premium`** — monetize the rails we already run (fastest path since cores exist).
5. `disclosure-compiler`, then Tier 3 volume tools, then Tier 4 strategic.

## Pricing & packaging notes

- Keep penetration pricing (marginal cost ~$0 makes it safe); raise only on observed 402-exhaustion-with-conversion.
- Offer **bundles**: "Energy" (taxcredit + ghg + disclosure), "Agent Ops" (agent-books + agent-credit + escrow-pro + surety-premium), "Dev" (data-guard + fincalc + timestamp-notary).
- Every tool ships with the standard freemium gate (100 free/day → price → `redeem_payment`) so discovery is frictionless and conversion is one call away.
- After each tool ships, run the **submission pipeline** (Smithery publish + Glama aggregate rebuild + official registry) so it's discoverable everywhere day one.

## `taxcredit-engine` handoff status — 2026-07-12

- [x] Core + adapter + `mcp_server.py`, TC-series invariant tests (fail loud)
- [x] Bundled, source-linked reference data versioned in-repo
- [x] Mounted at `/taxcredit-engine/mcp`, healthz + version, added to gateway image
- [x] Priced via existing payment gate; 100 free calls/day, then $2/call
- [x] Deployed to droplet with rollback tag; 18-agent health count verified
- [x] Glama aggregate rebuilt (18 agents / 117 tools); official-registry package generated and schema-validated
- [ ] Complete the account-authorized marketplace actions: official Registry login/publish, Glama admin rebuild, and Smithery publish

The production service does not depend on these directory listings. See
[`TAXCREDIT_ENGINE_DEPLOYMENT_2026-07-12.md`](TAXCREDIT_ENGINE_DEPLOYMENT_2026-07-12.md)
for the live verification and rollback record.
