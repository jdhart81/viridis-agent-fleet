# x402-C: Carbon Receipts for Machine-to-Machine Payments
**Draft 0.1 · 2026-07-15 · Viridis LLC · License: CC-BY-4.0**
**Status: Draft for community comment**

## Abstract

x402 gave machine-to-machine commerce a payment primitive; hundreds of
millions of agent transactions now settle without a human in the loop. None
of them account for the physical cost of the computation they purchased.
x402-C is a minimal, backward-compatible extension: any x402/HTTP-402 payment
receipt MAY carry a `carbon` object stating the energy and CO2e attributable
to the paid work, how it was computed, and — optionally — a reference to a
verified offset retirement. One field, physically grounded, independently
checkable.

## Motivation

1. **Agent transactions are physical events.** Every paid inference, CAD job,
   or dataset query dissipates energy bounded from below by Landauer's
   principle (E ≥ kT·ln2 per irreversible bit operation). As agent commerce
   scales, its aggregate footprint becomes material — and unmeasured.
2. **Procurement is coming.** Corporate buyers of agent services will
   inherit Scope 3 reporting obligations for them (GHG Protocol; ESRS E1;
   IFRS S2). A receipt-level carbon field turns an unanswerable audit
   question into a `sum()`.
3. **A floor beats a guess.** Self-reported footprints are gameable upward
   (greenwashing headroom) and downward (denial). A thermodynamic lower
   bound is falsifiable: a claimed energy below the Landauer floor for the
   declared bit operations is *physically impossible* and MUST be rejected.

## Specification

The key words MUST, SHOULD, MAY are to be interpreted per RFC 2119.

### 1. The `carbon` object

A conforming payment receipt (x402 settlement response, Stripe metadata,
escrow release record, or any receipt JSON) MAY include:

```json
{
  "carbon": {
    "version": "x402c/0.1",
    "g_co2e": 0.200,
    "energy_j": 1.35,
    "method": "landauer-floor",
    "method_ref": "doi:10.5281/zenodo.19317982",
    "bit_ops": 4.2e14,
    "grid_intensity_g_per_kwh": 380,
    "offset_ref": "viridis:offsets/ret-000017",
    "attestor": "viridis:compute-ledger",
    "attestation_hash": "sha256:..."
  }
}
```

### 2. Field requirements

- `version` (MUST): the string `x402c/0.1`.
- `g_co2e` (MUST): non-negative number; grams CO2-equivalent attributed to
  the paid work.
- `method` (MUST): one of
  - `landauer-floor` — thermodynamic lower bound from declared bit
    operations (`bit_ops` REQUIRED; `energy_j` MUST be ≥ kT·ln2 · bit_ops
    at T = 300 K),
  - `measured` — metered energy at the serving hardware
    (`energy_j` REQUIRED),
  - `estimated` — model-based estimate (lowest evidentiary tier; consumers
    SHOULD discount it).
- `energy_j`, `bit_ops`, `grid_intensity_g_per_kwh` (conditional/SHOULD):
  the inputs needed to recompute `g_co2e`. A receipt whose stated inputs do
  not reproduce its `g_co2e` (±1%) is **malformed**.
- `offset_ref` (MAY): a resolvable reference to a *retirement* record — not
  a purchase, a retirement — in a clearinghouse that exposes public
  verification (e.g. `verify_retirement`). Present ⇒ the transaction claims
  carbon-neutrality for the declared amount.
- `attestor` + `attestation_hash` (SHOULD): who computed the figure and a
  hash binding the carbon object to the receipt it rides on, so it cannot be
  detached and reused.

### 3. Conformance rules

- **C1 (physical floor):** a validator MUST reject `method: landauer-floor`
  receipts where `energy_j < bit_ops · 2.87e-21` J (kT·ln2, 300 K). Impossible
  physics is fraud, not rounding.
- **C2 (recomputability):** `g_co2e` MUST equal
  `energy_j / 3.6e6 · grid_intensity_g_per_kwh` (±1%) when those fields are
  present.
- **C3 (no detachment):** where `attestation_hash` is present it MUST bind
  the carbon object together with the payment identifier of the enclosing
  receipt.
- **C4 (offset honesty):** `offset_ref` MUST resolve to a retirement whose
  retired grams ≥ `g_co2e`, else the neutrality claim is void; validators
  SHOULD surface partial coverage explicitly.
- **C5 (backward compatibility):** consumers unaware of x402-C MUST be able
  to ignore the `carbon` member with no behavioral change.

### 4. Reference implementation — LIVE

Open-source and running in production at `mcp.viridisconservation.com`. As of
2026-07-15 the two core tools that emit and verify the standard are deployed
and smoke-tested end to end (`scripts/carbon_neutral_work_demo.py`):

- **agent-compute-ledger-agent v0.3.0** — `carbon_receipt` **emits** the
  x402-C `carbon` object from a recorded work entry (method `landauer-floor`
  when bit_ops are declared; C1 floor enforced at record time, C2 self-checked,
  C3 attestation_hash binds it to the ledger's hash chain).
- **agent-offset-clearinghouse-agent v0.1.3** — `verify_retirement` is the
  **C4 check**: confirms an `offset_ref` retires ≥ the receipt's gCO2e of
  *verified-only* conservation credit (O7). Purchase + retirement carry public,
  content-addressed certificates.
- **agent-metering-agent v0.2.0** — per-call usage events the carbon object
  attaches to.
- **agent-verified-relay-agent** — receipt chains x402-C objects ride on.

A live run: 0.2956 gCO2e of Landauer-validated inference work, neutralized by
1 g of D-Score-verified conservation credit, emitted as an `x402c/0.1` receipt
whose neutrality is independently confirmed by `verify_retirement`.

First conforming transaction on record: 2026-07-11 — an agent-to-agent job
settled, carbon-accounted at 0.200 gCO2e via Landauer-floor method, offset
against a D-Score-verified credit (`dscore:zenodo.19317982/site7`), all
machine-verifiable.

### 5. Relationship to other standards

- **x402:** x402-C adds one optional member to receipts; it changes no wire
  flow, no 402 semantics, no settlement path.
- **ERC-8004:** carbon attestations MAY be exported as ERC-8004 feedback
  records; the `attestor` field maps to the attesting agent's identity.
- **GHG Protocol / ESRS E1 / IFRS S2:** `g_co2e` sums are designed to be
  ingestible as Scope 3 purchased-services line items with method-tier
  disclosure.

## Rationale for the floor-first design

Every other carbon-accounting scheme starts from self-declared measurements
and fights gaming afterward. x402-C starts from a bound that physics
enforces: the Landauer floor cannot be undercut, only exceeded. This gives
the standard an unusual property — **the cheapest conforming claim is also
the most conservative one**, so the incentive gradient points toward honesty.
Measured values (tier 2) then compete on precision above the floor.

## IP and process

Published under CC-BY-4.0. Viridis commits to royalty-free implementation.
Comment via issues on `github.com/jdhart81/viridis-agent-fleet` or
justin@viridis.earth. Draft 0.2 will incorporate: multi-currency grid
intensity sources, batch receipts, and an ERC-8004 attestation profile.

---
*The agent economy will meter its money before it meters its heat. x402-C
exists so the second meter ships while the standards are still wet.*
