# ViridisOS × Agent Fleet — How They Compose

**Date:** 2026-07-19. Companion to `VIRIDISOS_SYSTEMS_ARCHITECTURE.md`,
`VIRIDISOS_LICENSING_AND_OPEN_CORE_POLICY.md`, and the fleet's `FLEET_STRUCTURE.md`.

**Thesis:** ViridisOS and the Viridis Agent Fleet are not two products. They are **two halves of one
operating system that share a single thermodynamic root of trust.** ViridisOS certifies the *world* (is
this conservation claim real?); the fleet certifies the *actors* (is this agent trustworthy, did it do the
work, did it settle honestly?). Same DNA — proof-backed authority, recompute-verifiable attestation,
certified-only/human-gated, IB-grounded, thin settlement take-rate — applied to two economies.

**One line:** ViridisOS is the kernel + certification authority; the fleet is the userspace — the
population of autonomous economic agents that run on it and let the OS act in the world at scale.

---

## Framing as invariants

- **INV-ONE-ROOT** — conservation certificates (ViridisOS L3) and agent attestations (fleet
  identity/provenance/notary) resolve to **one** Viridis root of trust and **one** canon/IB backbone. Never
  two roots.
- **INV-ONE-MARK** — "Certified by ViridisOS" is a single protected mark spanning both certificate types.
- **INV-ONE-TOLL** — one thin settlement take-rate (**1%**, already live on the fleet's third-party
  payouts) applies to value flowing through either half. It matches the ViridisOS protocol take-rate by
  design.
- **INV-IB-CURRENCY** — both halves price in the same Intelligence-Bound currency (joules & gCO₂e via the
  P-variable); the compute-ledger and the conservation modules speak the same physics.

## The layer map — the fleet already built ViridisOS layers

| ViridisOS layer | Fleet component that *is* this layer | Note |
|---|---|---|
| **L0 Verification backbone** | Shared Lean canon + Intelligence Bound; `compute-ledger-agent` prices the IB P-variable in joules & gCO₂e | Single root of trust for both halves |
| **L1 Core planes / settlement** | `identity → trust → escrow` + `metering → arbitration → compute-ledger` | Agent-native rebuild of ViridisOS FINANCE + VERIFY + DAO-settlement |
| **L2 Module runtime** | Each agent's `agent.yaml` + adapters (fastapi / mcp / cloudflare / skill) | An agent = a ViridisOS module that runs as an autonomous service |
| **L3 Certification** | `notary` (delivery proofs), `provenance` (genesis certs), `arbitration` (verifiable rulings), `trust-oracle` (attestations) | The recompute-verifiable attestation pattern, applied to agent behavior |
| **L4 Surfaces** | Gateway + ARD catalog (`/.well-known/ai-catalog.json`); conservation app | Two surfaces on one platform |

Consequence: the fleet is not adjacent to ViridisOS — **it is a deployment of ViridisOS's L1/L3 pattern into
the agent economy**, and a population of L2 modules that happen to be autonomous.

## The three seams (one already half-built)

**1. The conservation flywheel — `offset-clearinghouse-agent` is the literal bridge.**
It nets agent compute-emissions against verified conservation credits. So the agent economy becomes a
*demand source* for ViridisOS-certified credits: more agent activity → more compute emissions → more demand
for verified offsets → more conservation finance → mission. Same IB currency on both sides of the ledger.

```
agent economy activity ──(compute-ledger: joules, gCO2e)──► emissions to offset
        ▲                                                          │
        │                                                          ▼
  more agent hiring ◄── conservation finance ◄── ViridisOS-certified credits
                          (offset-clearinghouse buys verified supply)
```

**2. Unify the trust root and the take-rate.** The fleet already charges 1% on third-party payouts —
identical to the ViridisOS protocol take-rate. Run **one** root key, **one** mark, **one** toll across both.
This is the single most important integration action: it makes "Certified by ViridisOS" mean the same,
recompute-verifiable thing whether the subject is a parcel or an agent.

**3. `covenant-agent` is the alignment layer, running.** Deny-by-default, machine-checkable authority
leases = the P3 / alignment-as-feasibility theorem instantiated as code. It is how ViridisOS safely lets
autonomous agents act without Goodharting. ViridisOS's alignment invariants get **enforced at runtime** by
the fleet's covenant / arbitration / surety agents. The orchestration ceiling (the multi-domain IB result)
is the theoretical statement; the covenant agent is its enforcement.

## The composed act (end to end)

A fleet agent — with a verifiable identity, bounded by a covenant, metered, carbon-priced — *performs* a
conservation measurement by calling a ViridisOS module (e.g. Restoration/Nucleation), issues a
ViridisOS-certified claim, and settles through the shared rails. Every step is recompute-verifiable and
IB-grounded, and the agent's own emissions are offset by ViridisOS-verified credits it helped create. The
OS scales from "app users" to "an autonomous machine economy that does conservation work and pays for it."

## Why this is the unique position

- Every **agent-trust** competitor (identity / escrow / reputation) lacks a physics-grounded root.
- Every **conservation-MRV** competitor lacks proof-backing.
- **Viridis is the only entity where the agent-economy rails and the conservation certification share one
  thermodynamic root of trust.** That shared L0 — the canon + the Intelligence Bound — is the moat that
  neither competitor set can cross.

## Recommended integration actions

1. **Merge the roots.** Make ViridisOS's certification root key and the fleet's identity/provenance root the
   same Viridis root; issue two certificate profiles (conservation claim · agent attestation) under it.
2. **One mark, one standard doc.** Extend the ViridisOS Certification Standard to cover agent attestations so
   "Certified by ViridisOS" spans both.
3. **Wire the flywheel explicitly.** Make `offset-clearinghouse-agent` consume ViridisOS-certified credits as
   its verified supply; report the agent-economy → conservation-finance throughput as a headline metric.
4. **Publish the covenant layer as the alignment story.** Position covenant/arbitration/surety as the
   runtime enforcement of the OS's alignment invariants — the answer to "how do you let autonomous agents
   act safely?"

---

*Sources: `Agents to deploy/FLEET_STRUCTURE.md`, `README.md`, `AGENT_FLEET.md`;
`ViridisOS/VIRIDISOS_SYSTEMS_ARCHITECTURE.md`, `VIRIDISOS_LICENSING_AND_OPEN_CORE_POLICY.md`.*
