# Viridis Agent Fleet — MCP Surface

> **The first agent fleet whose members are provably born, authorized, metered,
> paid, carbon-accounted, and offset — by each other.**
> [Read the receipts.](docs/GENESIS_RECEIPTS.md) Executed 2026-07-11 against the
> live gateway over MCP streamable-http; 12/12 cross-agent invariants passed.
> The rails it ran on are live at the same endpoint, free to call.

The public MCP-facing surface of the **Viridis agent stable**: a 13-agent
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
| **Revenue** | `smartscale` | [`/smartscale/mcp`](https://mcp.viridisconservation.com/smartscale/mcp) | Credit-card-calibrated measurement — the first sellable service |
| **Revenue** | `protogen` | [`/protogen/mcp`](https://mcp.viridisconservation.com/protogen/mcp) | MCP CAD services; bundles with SmartScale (measure → CAD) |
| **Revenue** | `regulatory-radar` | [`/regulatory-radar/mcp`](https://mcp.viridisconservation.com/regulatory-radar/mcp) | CSRD/TNFD compliance-as-a-service |
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
gateway/                          # reference gateway: one process hosts all 13 over streamable-http
docs/GENESIS_RECEIPTS.md          # the first self-transaction — live, 12/12 invariants
docs/A2A_ECONOMY.md               # the full identity→trust→escrow thesis + composition demo
```

## Status

**LIVE.** All 13 published on the MCP registry under `io.github.jdhart81/*`,
hosted at `https://mcp.viridisconservation.com` (13/13 healthy). Since
2026-07-11 the gateway is **durable**: every state change (escrows, identities,
certificates, meters, ledgers) is persisted before the caller sees the result
and survives restarts — verified in production. Genesis receipts for the
fleet's first self-transaction are in
[docs/GENESIS_RECEIPTS.md](docs/GENESIS_RECEIPTS.md).

Current posture: endpoints are open and free to call; no funds move — escrow,
offsets, and metering are state machines, with payment rails (x402 for A2A,
Stripe for human-facing services) attaching next. See `docs/A2A_ECONOMY.md`.

---

© 2026 Viridis LLC. The private fleet (agent cores, tests, orchestration) is
not included here by design.
