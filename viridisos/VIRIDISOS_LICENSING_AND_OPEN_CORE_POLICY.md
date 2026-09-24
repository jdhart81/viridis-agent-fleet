# ViridisOS — Licensing & Open-Core Policy

**Decision (2026-07-19):** ViridisOS is **protocol-open, toll-the-flow**. We open source everything whose
openness spreads the standard, and we capture revenue only at the **trust root** and the **settlement
flow** — never at access or knowledge.

**Strategic objective:** maximize the network effect of the ViridisOS certification standard (which *is*
the mission — verified conservation accounting becoming default infrastructure) while capturing a
mission-aligned share of the value that flows through it.

---

## Objective, as invariants

- **INV-NETWORK** — every design choice lowers friction to verify, cite, integrate, and re-issue against
  the canon. Adoption of the standard is the primary metric.
- **INV-FLOW-REVENUE** — revenue is captured on the *value flowing through* the network (settlement
  take-rate) and on the *authority to issue trusted certificates* (the trust root), not on access to code
  or proofs.
- **INV-MOAT-CONSISTENCY** — never close anything whose openness is what makes the product credible. The
  recompute path and the proofs must be inspectable, or the word "verifiable" is a lie. Secrecy that
  breaks verifiability is forbidden.
- **INV-MISSION-ALIGNMENT** — the take-rate makes revenue rise with verified restoration throughput.
  Earning more = more audited conservation capital in motion. Revenue is the feasibility condition of the
  mission, not a tax on it.

## The core insight

Our moat was never the math. Openness of the proofs is a *feature we sell* — a certificate no one can
recompute is worthless, so the recompute path and the theorems must be public. The enforceable moat is
the **certification mark + the trust root**, exactly like:

- **USDA Organic** — the standard is public; the *seal* is a protected, licensed mark.
- **A Certificate Authority** — TLS and OpenSSL are free; DigiCert is a billion-dollar company because it
  holds the *authority to issue trusted certificates*.
- **Let's Encrypt** — made issuance free and drove HTTPS from ~40% to ~95%+ of web traffic. Network effect
  wins by removing friction; value is captured elsewhere.

A competitor can clone every line of ViridisOS and still cannot issue a certificate the market trusts —
they hold neither the root key nor the right to the mark.

## The license map (by layer)

| Layer | What it is | Posture | License |
|---|---|---|---|
| **L0 Canon** | Lean proofs, Aristotle audits, theorems | **Open** (drives academic + trust network effect) | Apache-2.0 / MIT *(already in place)* |
| **Module recompute kernels** | the `verify.py` numeric cores derived from public theorems | **Open** (required for third-party verifiability) | Apache-2.0 |
| **The Standard** | certificate format + verification algorithm spec | **Open spec, free forever** | CC-BY-4.0 (spec) |
| **Reference runtime (L2)** | module contract, registry, provenance, reference certifier | **Open source** (drives developer network effect; self-hostable) | Apache-2.0 |
| **Trust root + issuance (L3)** | the authoritative ViridisOS signing key, registry, revocation | **Commercial** | Proprietary |
| **Settlement rails (L1 FINANCE/DAO)** | metered value flow, take-rate | **Commercial** | Proprietary |
| **App + surfaces (L4)** | conservation app, dashboards, partner portal, enterprise API | **Commercial** | Proprietary *(already in place)* |
| **The certification mark** | "Certified by ViridisOS" name/seal | **Protected trademark, licensed** | Trademark + usage license |

Non-negotiable: **verification is free, forever, for everyone.** Anyone can check any certificate against
the open standard at zero cost. This is the network-effect engine and the trust guarantee; it is never
metered.

## The three tollbooths (revenue that does not throttle the network)

1. **The trust root (issuance authority).** Self-hosted / self-signed certificates from the open runtime
   are "valid but self-rooted." A **ViridisOS-rooted** certificate carries the trusted mark. Free tier for
   small issuers to maximize adoption; metered / enterprise pricing above threshold. *(The DigiCert lever.)*

2. **The settlement take-rate — the primary engine.** A thin basis-point fee on the value of credits and
   instruments settled through FINANCE/DAO while carrying a ViridisOS-rooted certificate. We tax the flow,
   not the access. Two distinct rates:
   - **Full-service surface (the app):** higher take (the current ~20% platform fee) — captive, full-service.
   - **Open protocol rails (third-party issuers):** *thin* protocol fee (target ~0.5–2%), deliberately low
     so the network chooses our rails over rolling their own. Volume × thin-fee > friction × fat-fee.
   *(The Stripe / gas-fee lever — revenue scales with mission throughput.)*

3. **Enterprise & mark licensing.** Registries, insurers, and auditors pay for API SLAs, revocation feeds,
   portfolio dashboards, and the right to require/display the **"Certified by ViridisOS"** mark as a line
   item in their own standards. *(The Visa network / mark-licensing lever.)*

Optional fourth: **privacy-preserving benchmark data** — aggregate priors from certified parcels sold as a
premium data product. Real data network effect; gated separately.

## Why this is the right call, mission + business

- **Network effect and revenue become the same variable.** We earn in proportion to verified restoration
  finance moving through the network. There is no configuration in which maximizing revenue works against
  the mission — that is the point.
- **Openness compounds the moat instead of leaking it.** Every external verifier, citation, and self-hosted
  module makes the standard more authoritative and harder to displace. Closing the proofs would tax
  knowledge, throttle adoption, and forfeit the "verifiable" claim we sell.
- **The flywheel funds itself.** Take-rate revenue recycles into the nightly research arm → new certified
  modules → more network value → more flow. Revenue → modules → adoption → revenue.

## Open decisions (Justin's to set)

1. **Protocol take-rate.** Recommend starting **1%** on third-party-rail settled value (vs. ~20% full-service
   app take). Dial to taste; thinner = faster network capture.
2. **Trust-root federation (later).** Whether to let major registries run their own ViridisOS-compliant
   roots under a cross-certification program (CA/Browser-Forum model) — deepens the network by getting
   others to invest in it, while we keep root governance + program revenue. Recommend: yes, post-traction.
3. **Kernel openness granularity.** Default here is *all* kernels open (max trust). If a specific module has
   a genuine fast-follower risk, it can ship source-available-but-commercial without breaking any invariant,
   since the trust root stays closed regardless.

---

*Companion to `VIRIDISOS_BUSINESS_BRIEF.md` and `VIRIDISOS_SYSTEMS_ARCHITECTURE.md`. Current on-disk state
already matches the split: canon = Apache/MIT (open), conservation app = proprietary. This policy makes it
deliberate and extends it to the runtime, standard, mark, and take-rate.*
