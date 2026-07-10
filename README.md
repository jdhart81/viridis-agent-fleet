# Viridis Agent Fleet — MCP Surface

The public MCP-facing surface of the **Viridis agent stable**: a 13-agent
agent-to-agent (A2A) economy published on the [Model Context Protocol
registry](https://registry.modelcontextprotocol.io) under the `earth.viridis`
namespace. This repository is the **callable spec + provenance** for those
listings — the registry manifests, the JSON-Schema tool definitions, the
public agent contracts, and the reference gateway. The agent cores are
maintained privately; everything here is what a *calling* agent needs.

By [Viridis LLC](https://viridis.earth) — conservation technology.

## The economy: identity → trust → escrow → settlement → constitution

Trustworthy agents transacting with agents needs rails. This fleet ships them
as composable MCP services:

| Layer | Agent | What it provides |
|---|---|---|
| **Identity** | `agent-identity-registry` | Content-addressed agent DIDs + capability discovery — the passport + directory |
| **Trust** | `agent-trust-oracle` | Decay-weighted reputation + tamper-evident trust attestations |
| **Settlement** | `agent-escrow` | Trustless escrow with an exactly-once state machine + audit hash chain |
| **Metering** | `agent-metering` | Usage metering + SLA accounting — the meter behind x402 |
| **Arbitration** | `agent-arbitration` | Dispute-resolution oracle consuming trust signals |
| **Compute ledger** | `agent-compute-ledger` | "Compute is carbon" cost/energy accounting for agent work |
| **Covenant** | `agent-covenant` | Deny-by-default authority leases for agents wielding real power |
| **Provenance** | `agent-provenance` | Genesis certificates, lineage, cascading recalls |
| **Offsets** | `agent-offset-clearinghouse` | Verified-credit carbon accountability — the conservation flywheel |
| **Revenue** | `smartscale` | Credit-card-calibrated measurement — the first sellable service |
| **Revenue** | `protogen` | MCP CAD services; bundles with SmartScale (measure → CAD) |
| **Revenue** | `regulatory-radar` | CSRD/TNFD compliance-as-a-service |
| **Enabler** | `narrative-engine` | Grant / investor / policy narrative generation |

## Layout

```
mcp-publish/<agent>/server.json   # MCP registry manifest (earth.viridis/*)
mcp-publish/<agent>/tools.json    # JSON-Schema tool definitions (one per action)
mcp-publish/<agent>/DEPLOY.md     # env, endpoints, how a caller uses it
contracts/<agent>.md              # public agent contract (capabilities, invariants)
gateway/                          # reference gateway: one process hosts all 13 over streamable-http
docs/A2A_ECONOMY.md               # the full identity→trust→escrow thesis + composition demo
```

## Calling an agent

Every agent is a streamable-HTTP MCP server hosted behind
`https://mcp.viridis.earth/<path>/mcp` (paths in each `server.json`). Point any
MCP client at the URL, or discover them on the registry by searching
`earth.viridis`. Each `tools.json` is the exact tool surface — one tool per
agent action, with typed input/output schemas.

## Status

**LIVE (2026-07-09).** All 13 published on the MCP registry under
`io.github.jdhart81/*` and hosted at `https://viridis-agent-stable.fly.dev`
(`/healthz` = 13 ok). The as-shipped manifests are in `mcp-publish-github/`
(the `mcp-publish/` set holds the branded `earth.viridis` variants for the
round-1b rebrand + custom domain `mcp.viridis.earth`).

Round-1 posture: endpoints are open (read-tool posture); no funds move — escrow,
offsets, and metering are state machines, with payment rails (x402 for A2A,
Stripe for human-facing services) attaching in a later round. See
`docs/A2A_ECONOMY.md`.

---

© 2026 Viridis LLC. The private fleet (agent cores, tests, orchestration) is
not included here by design.
