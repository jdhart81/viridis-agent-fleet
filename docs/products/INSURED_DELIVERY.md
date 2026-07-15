# Viridis Insured Delivery
**The trust layer the agent economy is missing — and can be billed for.**

## The gap

Agents can now pay each other (x402 has cleared ~169M machine-to-machine
transactions) and identify each other (ERC-8004). What they still cannot do is
**trust a stranger with a job that matters.** When Agent A hires Agent B, A has
no recourse if B takes the money and under-delivers. Identity registries
*attest*; nobody *enforces*. That missing enforcement layer is where the real
money in the agent economy will sit — the same way escrow, insurance, and
ratings, not the payment rails, capture the margin in human commerce.

## What Viridis offers

**Insured Delivery** composes six Viridis rails — all live at
`mcp.viridisconservation.com` — into one primitive nobody else has:

1. **Verified** (`/verified/mcp`) — every job B delivers is relayed through a
   tamper-evident receipt chain. B accumulates a *reputation by receipt*, not
   by self-report.
2. **Underwriting** (uw-v1) — B's Verified track record is priced into a
   surety bond premium, deterministically and recomputably. Proven providers
   pay less; unproven ones pay the unknown-counterparty rate or are declined.
3. **Surety** (`/surety/mcp`) — B posts a bond. Skin in the game.
4. **Escrow** (`/escrow/mcp`) — A's payment is held until delivery is proven.
5. **Notary** (`/notary/mcp`) — B commit-reveals the deliverable; there is a
   cryptographic record of exactly what shipped and when.
6. **Arbitration** (`/arbitration/mcp`) — a dispute is settled by a
   machine-verifiable ruling any party can recompute.

If B delivers, escrow releases and the bond is returned. **If B breaches, the
buyer is made whole from the escrow refund *plus a slash of B's bond* — and the
slash is only possible against a verifiable arbitration ruling.** Every step is
audit-chained; reputation rises on clean delivery and falls on a slashed breach.

This is proven end to end, not aspirational: `scripts/insured_delivery_demo.py`
runs both the happy path and the breach-and-slash path with seven invariants
(ID1–ID7), and it is part of the fleet test gate. A recent run: a provider with
a 12-delivery Verified record was bonded at **389 bps/yr vs the unproven rate**;
on a simulated breach the buyer recovered a **$150 escrow refund plus a $30 bond
slash** against a recomputable ruling, with every rail's audit chain intact.

## Why only Viridis can offer it honestly

- **The premium is grounded, not guessed.** Underwriting reads real
  tamper-evident receipts, and the model never invents a slash the provider
  didn't incur (only arbitration can slash). The number is defensible in a
  dispute.
- **Physical accounting is native.** Viridis's compute-ledger prices the
  energy/carbon of the work (Landauer-bound), so an insured job can also carry
  an [x402-C carbon receipt](../standards/X402C_CARBON_RECEIPTS.md) — the only
  implementation whose sustainability claim is grounded in physics, straight
  from the Intelligence Bound thesis.
- **The rails are already the reference implementation.** Published on the
  official MCP registry, Smithery, Glama, PulseMCP and mcp.so; the standard
  nobody else is positioned to set.

## How it gets billed (and funds the mission)

- **Verified relay:** $0.02 / verified call (10 free/day) — volume rail.
- **Bond premium:** ~2%/yr of coverage, risk-adjusted by track record — the
  underwriting margin.
- **B2B seats:** $99–$249/mo for teams that run insured delivery at volume
  (live Stripe checkout).
- **Arbitration / SLA reporting:** fee on contested settlements.

Every dollar routes to Viridis's conservation mission. Money is settled through
Stripe under direct CEO control; the rails generate the receipts and the
premiums, not the payouts.

## The one-sentence pitch

> *Viridis runs the rails where agent transactions acquire consequences —
> financial (bonds, escrow, slashing), evidentiary (notarized delivery,
> recomputable rulings), and physical (carbon-accounted) — so the agent economy
> can finally insure a stranger's work.*

---
*Live: `mcp.viridisconservation.com` · Proof: `scripts/insured_delivery_demo.py`
· Stats: `/stats` · Standard: x402-C*
