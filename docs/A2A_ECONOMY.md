# The Viridis A2A Economy Layer
> Added 2026-07-09 · The three novel agents in the deployment stable + the composition that proves they work together.
> Companion: [FOCUS_SHORTLIST.md](FOCUS_SHORTLIST.md) · [../../FLEET_STRUCTURE.md](../../FLEET_STRUCTURE.md)

## The thesis in one sentence

As autonomous agents start hiring and paying each other, the scarce infrastructure
is not more services — it's the **rails that make an agent safe to hire and pay**:
a way to know *who* an agent is, *whether* to trust it, and *how* to transact
without either side getting burned. Viridis can own that layer early, because each
rail sits directly on a moat we already have.

## The three rails (identity → trust → escrow)

| Rail | Agent | Question it answers | Viridis moat it stands on |
|---|---|---|---|
| **Identity** | `agent-identity-registry-agent` | *Who is this agent, and what can it do?* | Market-registry + content-addressed DIDs; supply side of discovery |
| **Trust** | `agent-trust-oracle-agent` | *Should I delegate authority/money to it?* | Viridis Security's formal-verification thesis; ShenDao/OTA signal lineage; Adversarial Landauer reputation-as-information |
| **Settlement** | `agent-escrow-agent` | *How do we transact without a trusted middleman?* | Energy AI's proven x402 / HTTP-402 micropayment idiom (idempotent, refundable) |

They are deliberately small, composable, and stdlib-only. Each exposes the
fleet-standard `process/health/describe` contract and dispatches on an `action`
key, so any MCP orchestrator can wire them in minutes.

## How they compose — the market loop

```
   ┌──────────────┐   discover(cap)   ┌───────────────────┐
   │  BUYER agent │ ────────────────► │ IDENTITY registry │  who can do this?
   └──────┬───────┘ ◄──────────────── └───────────────────┘
          │ score(provider)           ┌───────────────────┐
          ├─────────────────────────► │   TRUST oracle    │  safe to hire?
          │ ◄──────────────────────── └───────────────────┘
          │ open→fund→release         ┌───────────────────┐
          ├─────────────────────────► │   ESCROW agent    │  pay on delivery
          │ ◄──────────────────────── └───────────────────┘
          │ record_outcome(delivered/dispute_lost)   │
          └──────────────────────────────────────────┘
                 outcome feeds back into reputation → the flywheel
```

The feedback edge is the point: every settled (or disputed) escrow updates the
provider's reputation, which sharpens the next discovery+trust decision. The rails
get more valuable the more they're used — a network effect, not a feature.

## Proof it works: the composition demo

`scripts/a2a_economy_demo.py` drives all three cores through their real `process()`
contract — exactly as an orchestrator would — and asserts 13 cross-agent invariants:

- **Discovery** AND-matches capabilities (a `cad`-only competitor is correctly excluded when the buyer needs `cad + step-export`).
- **Trust** gives a first-contact provider a neutral 0.5 prior — no blind trust, no unfair zero.
- **Escrow** freezes the fee at open ($1.49 platform / $147.51 net on a $149 job), releases on delivery, and keeps a tamper-evident 3-entry audit chain.
- **Feedback** raises reputation 0.50 → 0.667 after a clean job; a verifiable attestation is issued and validated.
- **Dispute path** refunds the buyer, **blocks a double-spend** (cannot release a refunded escrow), and drops reputation 0.667 → 0.50.

Run it:
```bash
python3 scripts/a2a_economy_demo.py           # narrative + assertions
python3 scripts/a2a_economy_demo.py --quiet   # CI mode (exits non-zero on any failure)
```

It doubles as an integration test — wire it into CI alongside `run_fleet_tests.py`
(which covers each agent in isolation; the demo covers them in composition).

## The settlement-stack extension (added 2026-07-09, second pass)

Three more primitives complete the rails. Hiring and paying an agent is not
enough — you must **count the work, resolve the fight, and account for the
physics**:

| Rail | Agent | Question it answers | Viridis moat it stands on |
|---|---|---|---|
| **Metering** | `agent-metering-agent` | *How much work was actually done, and was the SLA kept?* | Energy AI's x402 idiom (idempotent on event_id, prepaid/metered billing); tamper-evident chains |
| **Arbitration** | `agent-arbitration-agent` | *Who wins a dispute — provably?* | Viridis Security "authority must be proof-backed": deterministic, machine-verifiable rulings (verify_ruling recomputes them) |
| **Accounting** | `agent-compute-ledger-agent` | *What did the cognition cost, physically?* | The Intelligence Bound itself: joules, gCO2e, and Landauer-limit efficiency per unit of agent work — "compute is carbon" as a ledger |

They close the two open loops in the original three: escrow's
`DISPUTED -> (RELEASED|REFUNDED) (arbiter resolves)` now has its arbiter, and
the trust flywheel gains hard inputs (SLA breaches and lost disputes are
evidence and reputation events, not vibes). The compute ledger bridges the
fleet back to the conservation mission: agent carbon disclosure feeds
regulatory-radar's CSRD/TNFD reporting.

**Proof they compose:** `scripts/a2a_settlement_stack_demo.py` drives
meter → invoice → escrow → dispute → SLA-evidence → ruling → settlement →
carbon ledger through the real `process()` contracts and asserts **20
cross-agent invariants** (exits non-zero on failure), including: replayed
usage is never double-billed, the frozen invoice equals the escrow amount,
rulings allocate exactly 100% and are recomputable, settled escrows resist
double-spend, and physically impossible workload claims are rejected at the
Landauer floor.

**Publish packages:** all six A2A primitives (and the four revenue agents)
have MCP registry manifests + introspected tool schemas + DEPLOY.md under
`deploy/mcp-publish/` — prepared to the click, nothing published.

## The founding-era constitution (added 2026-07-09, third pass)

The founding of the agent economy happens exactly once. Rails make agents
*transactable*; three more primitives make the economy *constitutional* —
and each is a moat Viridis already holds:

| Layer | Agent | Question it answers | Viridis moat it stands on |
|---|---|---|---|
| **Authority** | `agent-covenant-agent` | *What may this agent do, exactly?* | Viridis Security: authority must be explicit, bounded, expiring, revocable, audited. Deny-by-default power of attorney; the audit chain is the compliance product |
| **Provenance** | `agent-provenance-agent` | *Who made this agent, and is its bloodline clean?* | The founding is once: monotone genesis indices make the founding cohort provable; lineage recalls quarantine an entire compromised line — containment nobody else has |
| **Offsets** | `agent-offset-clearinghouse-agent` | *Did the agent pay the planet back?* | The conservation flywheel: compute-ledger gCO2e becomes demand for VERIFIED credits (D-Score / land-verification refs required to enter the book). Uncopyable without owning verification |

The identity layer says who you are; provenance says where you came from;
trust says how you've behaved; covenant says what you may do; metering says
what you did; escrow+arbitration settle it; compute-ledger prices the physics;
offsets close the loop with the biosphere. **Thirteen agents, one constitution.**

**Proof it composes:** `scripts/a2a_genesis_demo.py` runs one agent's full
life — born (founding-cohort certificate) → identified (DID) → covenanted →
4 authorized jobs metered and invoiced → 80 gCO2e priced → offset to net-zero
with a verified credit → factory compromised → recall cascades, late children
quarantined at birth, covenant revoked, audit chain verifies. **14 cross-agent
invariants, exits non-zero on failure.**

**Bench (designed, not yet built — next candidates):** `agent-bond-underwriter`
(surety bonds priced from trust+SLA, slashed on lost arbitration),
`agent-census-observatory` (macro-stats of the economy: settled volume, active
meters, carbon intensity — live Intelligence-Bound empirics),
`agent-succession-agent` (orderly agent death: obligations transfer, escrows
settle, data disposition).

## Why this is the right early bet

- **Picks-and-shovels, not a single app.** Whatever agents end up doing, they'll need identity, trust, and settlement. Owning rails beats owning one destination.
- **Each rail monetizes independently** (registry listings, attestation/reputation subscriptions, settlement bps) *and* pulls the others through — an identity buyer is a trust prospect is an escrow user.
- **On-thesis.** Trust-with-proof is the literal Viridis Security mission; settlement reuses shipped Energy AI infra. This isn't a pivot — it's the fleet's moats pointed at a new market.

## Next moves (in leverage order)

1. **MCP publish `agent-identity-registry-agent`** — the hub everything else plugs into; the publish package is ready in `deploy/mcp-publish/` (Justin executes the click-path; Energy AI already proved it).
2. **Publish the rest of the rails** — trust, escrow, then the settlement stack (metering, arbitration, compute-ledger); all six packages are smoke-clean.
3. **Promote `wavefunction-search` from `_rnd-exploration/`** — it's the demand-side intent router that pairs with the supply-side registry; together they're a two-sided market.
4. **Back escrow with a real rail** — wire the x402/Stripe adapter so the state machine moves actual value (no fund movement without Justin's approval).
5. **Feed real signals into trust** — metering SLA reports and arbitration outcomes are now native inputs; connect ShenDao/OTA and Bounty-Hunter's Adversarial Landauer scores as upstream reputation sources.
6. **Persistence adapters** — all six A2A cores are in-memory by design (stdlib-only); add a storage adapter (SQLite/Supabase) behind the same invariants before production volume.
