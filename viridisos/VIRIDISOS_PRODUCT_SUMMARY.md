# ViridisOS — Product Summary

**One line:** ViridisOS is the operating system for verifiable conservation — a software platform where every number it emits is backed by a machine-checked theorem, sold with a certification standard no competitor can claim.

---

## What it is

ViridisOS is the product platform that turns Viridis's library of Lean-verified theorems into certified conservation products. The conservation-finance market prices ecosystem services, risk, and permanence with arbitrary, un-auditable numbers. Viridis has spent 90+ nightly research runs proving the underlying physics as machine-checked (zero-`sorry`, gate-passed) theorems deposited to a public canon. ViridisOS is the delivery vehicle for that verified science: the theorems are the moat, the platform ships them as priced capabilities, and a certification standard is how the moat gets sold.

The guiding invariant is simple and absolute: **every number ViridisOS emits traces to a machine-checked theorem.** If a claim can't be tied to a verified theorem in the canon, it does not ship through the certified path.

## The product, in three parts

**1. The Platform.** The software system that land trusts, project developers, insurers, and MRV markets run on — built on the existing MEASURE · VERIFY · FINANCE · DATA chassis, plus a module runtime where each research result plugs in as a priced capability.

**2. The Certification Standard (the moat).** A paid "certified-by-a-verified-theorem" gate on MRV, carbon, biodiversity, and permanence claims. When a claim ships through ViridisOS it carries a cryptographic attestation tracing back to a Lean-checked theorem plus the measured data. Anyone can independently recompute it bit-for-bit and verify the signature. No competitor can issue this.

**3. Domain modules.** Priced capabilities that plug into the platform, each backed by one specific verified theorem. Wrapping a research run's numeric kernel, declaring its backing theorem, and registering it takes under an hour — so the roadmap effectively writes itself as the research arm produces new modules.

## How it's built — the five-layer stack

```
L4  SURFACES        conservation app · SDK/API · dashboards · reports · partner portal
L3  CERTIFICATION   "certified-by-theorem" attestations — the moat (issue + verify claims)
L2  MODULE RUNTIME  pluggable priced modules, each declaring a backing theorem
L1  CORE PLANES     MEASURE · VERIFY · FINANCE · DATA (existing chassis) + DAO ledger (K0→K7)
L0  VERIFICATION    the Lean canon · Aristotle · significance gate · Zenodo/git
    BACKBONE        — the source of every certified claim
```

The advantage of this design is that most of the stack already exists. L0 (the canon and research pipeline), L1 (the core planes, HDFM, Earth API/AlphaEarth, DAO ledger), and L4 (the live conservation app) are already standing. The genuinely new engineering is **L2, the module runtime, and L3, the certification layer** — the two pieces that convert verified science into a sellable, auditable product.

## End-to-end data flow

A parcel or portfolio flows through MEASURE (Earth API embeddings + HDFM → measured state and data hashes), then a module computes its output with provenance, VERIFY signs it into an attestation, CERTIFY issues the certificate after checking backing + recompute + hashes, FINANCE prices the instrument and the DAO ledger settles, and a surface renders the certified result.

## The first modules

| Module | What it sells | Backing theorem | State |
|---|---|---|---|
| **Restoration (Nucleation)** — planting-design law | "concentrate, don't broadcast": a go/no-go number + deposition setpoint that reframes broadcast seeding as stranded capital | FNT | LIVE |
| **Afforestation** | afforestation certification | AST | LIVE |
| **Harmonization** | align-by-harmonization vs. force meter; durable-vs-held permanence test | GHT | LIVE |
| **Mutualist** — risk-premium pricing | the first physically-grounded risk premium for natural-capital assets (the Diversification Wall) | SRPT | BLOCKED until SRPT publishes |
| **Tempo** — stewardship cadence | optimal intervention timing + a certified tempo standard | Stewardship Tempo | next to ship |

A module is LIVE only if its backing theorem is published in the canon; otherwise it is BLOCKED and can run in preview but cannot issue a certificate. That gate is the product working as designed.

## The invariants that make it defensible

- **Backing-or-nothing** — no certificate without a resolvable, gate-passed canon DOI.
- **Recompute-verifiable** — every certificate is independently, bit-identically recomputable.
- **Blocked propagation** — unverified or integrity-flagged backing means the module cannot certify.
- **Provenance everywhere** — every output carries its backing DOI, input hashes, and timestamp.
- **Never publish to canon** — ViridisOS only consumes canon DOIs; publication stays human-gated.

## Why it wins

The moat is invisible to competitors yet legible to buyers: a machine-checked proof is a correctness asset, and the certification standard makes it a purchasable line item. It compounds, because the research arm produces a new fundable, moated module on a nightly cadence. And it rides assets that already exist — the app, HDFM, Earth API, the DAO ledger, and the canon — unifying them rather than starting over.

---

*Source docs: `VIRIDISOS_BUSINESS_BRIEF.md`, `README.md`, `VIRIDISOS_SYSTEMS_ARCHITECTURE.md`, `PLATFORM_CATALOG.md` (2026-07-08 product tree). This summary consolidates them into a single briefing.*
