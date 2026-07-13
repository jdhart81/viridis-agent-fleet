# Viridis Agent Fleet — MCP Surface

> **The first agent fleet whose members are provably born, authorized, metered,
> paid, carbon-accounted, and offset — by each other.**
> [Read the receipts.](docs/GENESIS_RECEIPTS.md) Executed 2026-07-11 against the
> live gateway over MCP streamable-http; 12/12 cross-agent invariants passed.
> The rails it ran on are live at the same endpoint, free to call.

The public MCP-facing surface of the **Viridis agent stable**: an 18-agent
agent-to-agent (A2A) economy published on the [Model Context Protocol
registry](https://registry.modelcontextprotocol.io) under the
`io.github.jdhart81` namespace. This repository is the **callable spec +
provenance** for those listings — the registry manifests, the JSON-Schema tool
definitions, the public agent contracts, and the reference gateway. The agent
cores are maintained privately; everything here is what a *calling* agent needs.

By [Viridis LLC](https://viridisconservation.com) — conservation technology.

## The economy: identity → trust → escrow → settlement → constitution

Trustworthy agents transacting with agents needs rails. This fleet ships them
as composable MCP services:

| Layer | Agent | Endpoint | What it provides |
|---|---|---|---|
| **Identity** | `agent-identity-registry` | [`/identity/mcp`](https://mcp.viridisconservation.com/identity/mcp) | Content-addressed agent DIDs + capability discovery — the passport + directory |
| **Trust** | `agent-trust-oracle` | [`/trust/mcp`](https://mcp.viridisconservation.com/trust/mcp) | Decay-weighted reputation + tamper-evident trust attestations |
| **Settlement** | `agent-escrow` | [`/escrow/mcp`](https://mcp.viridisconservation.com/escrow/mcp) | Trustless escrow with an exactly-once state machine + audit hash chain |
| **Metering** | `agent-metering` | [`/metering/mcp`](https://mcp.viridisconservation.com/metering/mcp) | Usage metering + SLA accounting — the meter behind x402 |
| **Arbitration** | `agent-arbitration` | [`/arbitration/mcp`](https://mcp.viridisconservation.com/arbitration/mcp) | Dispute-resolution oracle consuming trust signals |
| **Compute ledger** | `agent-compute-ledger` | [`/compute-ledger/mcp`](https://mcp.viridisconservation.com/compute-ledger/mcp) | "Compute is carbon" cost/energy accounting for agent work |
| **Covenant** | `agent-covenant` | [`/covenant/mcp`](https://mcp.viridisconservation.com/covenant/mcp) | Deny-by-default authority leases for agents wielding real power |
| **Provenance** | `agent-provenance` | [`/provenance/mcp`](https://mcp.viridisconservation.com/provenance/mcp) | Genesis certificates, lineage, cascading recalls |
| **Offsets** | `agent-offset-clearinghouse` | [`/offsets/mcp`](https://mcp.viridisconservation.com/offsets/mcp) | Verified-credit carbon accountability — the conservation flywheel |
| **Interop** | `agent-erc8004-bridge` | [`/erc8004/mcp`](https://mcp.viridisconservation.com/erc8004/mcp) | MCP-native bridge to ERC-8004 identity and reputation |
| **Surety** | `agent-surety` | [`/surety/mcp`](https://mcp.viridisconservation.com/surety/mcp) | Deterministic bonding and ruling-gated slashing |
| **Notary** | `agent-notary` | [`/notary/mcp`](https://mcp.viridisconservation.com/notary/mcp) | Commit-reveal delivery proofs and verification |
| **Discovery** | `wavefunction-search` | [`/wavefunction/mcp`](https://mcp.viridisconservation.com/wavefunction/mcp) | Demand-side agent and collective discovery |
| **Revenue** | `smartscale` | [`/smartscale/mcp`](https://mcp.viridisconservation.com/smartscale/mcp) | Credit-card-calibrated measurement — the first sellable service |
| **Revenue** | `protogen` | [`/protogen/mcp`](https://mcp.viridisconservation.com/protogen/mcp) | MCP CAD services; bundles with SmartScale (measure → CAD) |
| **Revenue** | `regulatory-radar` | [`/regulatory-radar/mcp`](https://mcp.viridisconservation.com/regulatory-radar/mcp) | CSRD/TNFD compliance-as-a-service |
| **Revenue** | `taxcredit-engine` | [`/taxcredit-engine/mcp`](https://mcp.viridisconservation.com/taxcredit-engine/mcp) | Auditable 45Q/45V/45Y/48E/45X scenarios |
| **Enabler** | `narrative-engine` | [`/narrative-engine/mcp`](https://mcp.viridisconservation.com/narrative-engine/mcp) | Grant / investor / policy narrative generation |

**Federated member:** [EnergyAI](https://api.energyaisolution.com/mcp) — energy
intelligence (solar estimates, US incentives by ZIP, Energy Node Scores) on its
own infrastructure, discoverable through this fleet's catalog.

## Calling an agent

Every agent is a streamable-HTTP MCP server at
`https://mcp.viridisconservation.com/<path>/mcp`. Point any MCP client at the
URL, or discover them on the registry by searching `io.github.jdhart81`.
Machine-readable fleet catalog:
[`/.well-known/ai-catalog.json`](https://mcp.viridisconservation.com/.well-known/ai-catalog.json) ·
Fleet health: [`/healthz`](https://mcp.viridisconservation.com/healthz).
Each `tools.json` in `mcp-publish/` is the exact tool surface — one tool per
agent action, with typed input/output schemas.

## Layout

```
mcp-publish/<agent>/server.json   # MCP registry manifest
mcp-publish/<agent>/tools.json    # JSON-Schema tool definitions (one per action)
mcp-publish/<agent>/DEPLOY.md     # env, endpoints, how a caller uses it
contracts/<agent>.md              # public agent contract (capabilities, invariants)
gateway/                          # reference gateway: one process hosts all 18 over streamable-http
deploy/glama/                     # single-install 18-agent / 117-tool aggregate bridge
docs/GENESIS_RECEIPTS.md          # the first self-transaction — live, 12/12 invariants
docs/A2A_ECONOMY.md               # the full identity→trust→escrow thesis + composition demo
```

## Status

**LIVE.** The gateway hosts 18 agents at `https://mcp.viridisconservation.com`
(18/18 healthy), with Registry manifests under `io.github.jdhart81/*`. Since
2026-07-11 the gateway is **durable**: every state change (escrows, identities,
certificates, meters, ledgers) is persisted before the caller sees the result
and survives restarts — verified in production. Genesis receipts for the
fleet's first self-transaction are in
[docs/GENESIS_RECEIPTS.md](docs/GENESIS_RECEIPTS.md).

## Pricing — built for network growth

**The rails are free, forever.** Identity, trust, escrow, metering,
arbitration, compute-ledger, covenant, provenance, offsets, ERC-8004 bridge,
surety, notary, and discovery cost nothing to call — the rails ARE the
network, and we don't tax adoption of the thing whose value is adoption.

The three paid services are penetration-priced for agent budgets: **smartscale
$0.50/call, protogen $1.00/call, and taxcredit-engine $2.00/call — after 100
free calls per day.** Pay once by
Stripe Checkout (`create_payment` on `/payments/mcp`), then convert the
payment into call credits with `redeem_payment(session_id, agent)` —
`credits = amount ÷ price`, idempotent, never expire. A2A callers settle
per-call via the x402/escrow idiom. Price raises only ever happen via
pre-committed public triggers, and purchased credits are always honored.

Escrow, offsets, and metering remain coordination state machines — custody
stays on the payment rail. See `docs/A2A_ECONOMY.md`.

---

© 2026 Viridis LLC. The private fleet (agent cores, tests, orchestration) is
not included here by design.
