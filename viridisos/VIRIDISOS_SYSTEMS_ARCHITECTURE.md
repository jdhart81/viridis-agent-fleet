# ViridisOS — Systems Architecture

**How to build the ViridisOS platform, the certification layer, and the research-derived modules.**
This is the engineering blueprint behind `VIRIDISOS_BUSINESS_BRIEF.md`. It composes assets that
already exist rather than starting over. Authored 2026-07-08.

Guiding invariant: **every number ViridisOS emits traces to a machine-checked theorem.** If a claim
can't be tied to a verified Lean module in the canon, it does not ship through the certified path.

---

## 1. The stack (five layers)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ L4  SURFACES        conservation app (Next.js) · SDK/API · dashboards ·    │
│                     client reports · partner portal                        │
├──────────────────────────────────────────────────────────────────────────┤
│ L3  CERTIFICATION   "certified-by-theorem" attestations (the moat):        │
│     & STANDARDS      issue + verify claims against canon + measured data    │
├──────────────────────────────────────────────────────────────────────────┤
│ L2  MODULE RUNTIME  pluggable priced modules (Mutualist, Tempo, Nucleation,│
│                     Scheduler, …) — each declares a backing theorem         │
├──────────────────────────────────────────────────────────────────────────┤
│ L1  CORE PLANES     MEASURE · VERIFY · FINANCE · DATA  (existing chassis)   │
│                     + DAO/settlement ledger (K0→K7)                         │
├──────────────────────────────────────────────────────────────────────────┤
│ L0  VERIFICATION    the Lean canon (theorems) · Aristotle · significance    │
│     BACKBONE         gate · Zenodo/git — the source of every certified claim │
└──────────────────────────────────────────────────────────────────────────┘
```

Existing assets mapped in: **L0** = `viridis-canon` repo + `RESEARCH_PIPELINE_v2/` gate/tree.
**L1** = `03_APPLICATIONS/platform/` (`BUILD_CHASSIS`, `MEASURE`, `VERIFY`, `FINANCE`, `DATA`) +
`07_DAO_AGENT/`. **L4** = `viridis-conservation-app/` (`SYSTEM_ARCHITECTURE.md`), HDFM
(`03_APPLICATIONS/hdfm`), Earth API (`EARTH_API_INTEGRATION.md`, AlphaEarth K3). **L2 + L3 are the new
build.**

## 2. L0 — Verification backbone (already built; the moat substrate)

The canon is the root of trust. Each theorem is a Lean 4 module, zero-`sorry`, axiom-audited, gate-passed,
deposited to Zenodo with a DOI and mirrored to git. ViridisOS references a theorem by **(DOI, Lean module
name, Aristotle project id)**. The significance gate + research tree (`RESEARCH_PIPELINE_v2/`) decide what
enters the canon; ViridisOS only *consumes* verified entries. Nothing here changes — L0 is the supply.

## 3. L1 — Core planes (exists; unify under one runtime)

- **MEASURE** — parcel → D-Score/HDFM/Earth-API embeddings → measured state. (`BUILD_MEASURE.md`,
  `LiveCOGProvider`, AlphaEarth K3.)
- **VERIFY** — signs a K3 attestation over a computation (bit-identical recompute). This is the
  cryptographic primitive the certification layer builds on. (`BUILD_VERIFY.md`, VW3 signer.)
- **FINANCE** — D-Capital instruments, fee logic, settlement. (`BUILD_FINANCE.md`.)
- **DATA** — the shared data plane / access + storage (Supabase Postgres + RLS). (`BUILD_DATA.md`.)
- **DAO/Ledger** — K0→K7 settlement record. (`07_DAO_AGENT/`, `/settle`.)

Build task at L1: expose each plane behind a **stable internal API** (typed request/response) so L2
modules call planes uniformly rather than reaching into app internals.

## 4. L2 — Module runtime (new build) — the plug-in system

The heart of "ViridisOS." A **module** is a self-contained priced capability backed by one theorem.
Spec invariance — every module implements this contract:

```
Module {
  id, name, line                     # e.g. "mutualist", Finance line
  backing: { doi, lean_module, aristotle_id }   # REQUIRED — no backing, no certified output
  inputs:  [ plane refs ]            # what it reads from MEASURE/DATA/VERIFY
  compute(inputs) -> outputs         # the kernel (often an existing verify.py engine)
  outputs: { values, units, provenance }
  certify_hook()                     # emits a claim object for L3
  price()                            # metering / entitlement
}
```

Runtime responsibilities: **registration** (a module registers its id + backing + routes), **capability
discovery** (surfaces query available modules), **entitlement/metering** (who can call it, billing),
**provenance stamping** (every output carries backing DOI + input hashes). The research→product bridge
(`product_bridge.py`) already emits module concepts; the product tree (`product_tree.py`) orders which to
build. Implementing a module = wrapping the run's existing `verify.py`/engine as `compute()` and wiring
its backing theorem.

**Invariant M-1:** a module with unverified or integrity-flagged backing may run in *sandbox/preview*
but MUST NOT emit a certified claim (mirrors the product tree's BLOCKED state).

## 5. L3 — Certification & Standards (new build) — the moat

Turns a module output into a sellable, auditable certificate.

- **Claim object:** `{ subject (parcel/portfolio), module_id, output, backing (DOI + Lean id),
  input_data_hashes, timestamp }`.
- **Attestation:** VERIFY (L1) signs the claim → a K3 attestation. Anyone can later recompute
  bit-identically and check the signature + that the backing theorem is a live canon DOI.
- **Standard:** a published spec ("certified to ViridisOS Measurement-Adequacy v1", backed by Runs
  046/050/044) that MRV registries, insurers, and auditors can require as a line item.
- **Registry:** issued certificates recorded (DAO ledger / DATA plane) with revocation if a backing
  theorem is ever weakened.

**Invariant C-1:** a certificate is valid iff (a) its backing DOI resolves to a gate-passed canon entry,
(b) the signed recompute matches, and (c) the input data hashes verify. This three-part check is the moat.

## 6. Data flow (end to end)

```
parcel/portfolio
   → MEASURE (Earth API embeddings + HDFM) ─────────────► measured state + data hashes
   → MODULE.compute (e.g. Mutualist risk-premium)  ─────► output + provenance (backing DOI)
   → VERIFY signs (K3 attestation) ────────────────────► signed claim
   → CERTIFY issues certificate (checks backing + recompute + hashes)
   → FINANCE prices the instrument / DAO ledger settles (K0→K7)
   → SURFACE renders the certified result (app / report / API)
```

## 7. The first three modules (concrete)

| Module | inputs (planes) | compute kernel | backing | output |
|---|---|---|---|---|
| **Mutualist** (risk-premium) | MEASURE (energy throughput proxies), DATA (portfolio) | SRPT engine (Run-093 `verify.py`) | SRPT DOI + Lean module | risk premium floor π, Diversification-Wall residual, contagion sign |
| **Tempo** (cadence) | MEASURE (state drift), DATA (history) | Stewardship-Tempo engine (Run-060) | Tempo DOI | optimal intervention interval + tempo certificate |
| **Restoration** (nucleation) | MEASURE (σ edge-mortality, Δ suitability) | FNT engine (Run-061/FNT) | FNT DOI | Θ go/no-go + n* deposition setpoint |

Each is a wrap-existing-engine + declare-backing + register task, not a from-scratch build.

## 8. Tech stack (reuse what exists)

- **Frontend / surfaces:** Next.js + React (the conservation app), Supabase Auth, RLS.
- **Data plane:** Supabase Postgres (ref `eldfngwmgyebevoxqxwm`), object storage for attestations.
- **Compute kernels:** Python services (the runs' `verify.py`/engines), containerized.
- **Verification:** Lean 4.28.0 canon (`viridis-canon` repo), Aristotle for new proofs, K3 signer for
  attestations.
- **Earth data:** Google Earth Engine service account (AlphaEarth embeddings), STAC + windowed COG.
- **Deploy:** Docker on the DigitalOcean droplet (persistent deploy key); git pull → build → run.
- **DAO/ledger:** existing `07_DAO_AGENT/` runtime.

## 9. Build order (from the product tree + dependencies)

1. **Module runtime (L2) + module contract** — the enabling substrate; nothing plugs in without it.
2. **Certification layer (L3) on top of VERIFY** — the moat; the differentiated, paid piece.
3. **Mutualist module** — freshest cleanly-verified backing (Run-093); proves the module pattern.
4. **Tempo + Restoration modules** — next by product-tree priority.
5. **SDK/API surface (L4)** — expose modules + certification to partners.
6. Backfill remaining product-tree modules in priority order; the daily triage keeps the roadmap current.

## 10. Non-negotiable invariants

- **A-1 Backing-or-nothing:** no certified output without a resolvable, gate-passed canon DOI.
- **A-2 Recompute-verifiable:** every certificate is independently bit-identically recomputable.
- **A-3 Blocked propagation:** a module whose theorem is unverified/integrity-flagged cannot certify
  (BLOCKED) — the product-tree state gates the platform.
- **A-4 Provenance everywhere:** every output carries backing DOI + input hashes.
- **A-5 Human-gated canon:** ViridisOS consumes the canon but never publishes to it; publication stays
  Justin-gated via the research pipeline.

## 11. What exists vs. what to build

**Exists:** L0 canon + pipeline, L1 planes (MEASURE/VERIFY/FINANCE/DATA specs + chassis), the app, HDFM,
Earth API K3, the DAO ledger, the module *kernels* (each run's engine).
**To build:** L2 module runtime + contract, L3 certification/standards layer, the SDK/API surface, and
the per-module wrappers. That is the ViridisOS-specific engineering; everything under it is already
standing.
