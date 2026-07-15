# Viridis Agent Fleet — MCP Surface

The public MCP-facing surface of the **Viridis agent stable**: a 22-agent
agent-to-agent (A2A) economy published on the [Model Context Protocol
registry](https://registry.modelcontextprotocol.io) under the `io.github.jdhart81`
namespace. This repository is the **callable spec + provenance** for those
listings — the registry manifests, the JSON-Schema tool definitions, the
public agent contracts, and the reference gateway. The agent cores are
maintained privately; everything here is what a *calling* agent needs.

By [Viridis LLC](https://viridis.earth) — conservation technology.

## ⚡ First call in 30 seconds — no signup, no key

```bash
curl -s https://mcp.viridisconservation.com/regulatory-radar/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"scan_regulations",
       "arguments":{"jurisdiction":"EU","sector":"manufacturing"}}}'
```

Priced agents include 10 free calls/day; the settlement rails are free
forever. More worked examples (Python client included):
[docs/QUICKSTART_FIRST_CALL.md](docs/QUICKSTART_FIRST_CALL.md). New:
**Viridis Verified** (`/verified/mcp`) wraps *your* MCP server with
tamper-evident delivery receipts, and
[x402-C](docs/standards/X402C_CARBON_RECEIPTS.md) is our draft standard for
carbon receipts on machine-to-machine payments — comments welcome via issues.

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
| **ERC-8004 bridge** | `agent-erc8004-bridge` | Portable identity and reputation interop |
| **Surety** | `agent-surety` | Deterministic bond issuance and transaction coverage |
| **Notary** | `agent-notary` | Signed, content-addressed execution receipts |
| **Revenue** | `smartscale` | Credit-card-calibrated measurement — the first sellable service |
| **Revenue** | `protogen` | MCP CAD services; bundles with SmartScale (measure → CAD) |
| **Revenue** | `regulatory-radar` | CSRD/TNFD compliance-as-a-service |
| **Revenue** | `taxcredit-engine` | Auditable 45Q/45V/45Y/48E/45X scenarios; 100 free calls/day, then $2/call |
| **Research** | `wavefunction-search` | Deterministic wavefunction-search experiment tools |
| **Enabler** | `narrative-engine` | Grant / investor / policy narrative generation |

## Layout

```
mcp-publish/<agent>/server.json   # MCP registry manifest (earth.viridis/*)
mcp-publish/<agent>/tools.json    # JSON-Schema tool definitions (one per action)
mcp-publish/<agent>/DEPLOY.md     # env, endpoints, how a caller uses it
contracts/<agent>.md              # public agent contract (capabilities, invariants)
gateway/                          # reference gateway for the hosted streamable-http fleet
deploy/glama/                     # single-install 18-agent / 117-tool aggregate bridge
docs/A2A_ECONOMY.md               # the full identity→trust→escrow thesis + composition demo
```

## Calling an agent

Every agent is a streamable-HTTP MCP server hosted behind
`https://mcp.viridisconservation.com/<path>/mcp` (paths in each `server.json`). Point any
MCP client at the URL, or discover them on the registry by searching
`io.github.jdhart81`. Each `tools.json` is the exact tool surface — one tool per
agent action, with typed input/output schemas.

## Status

**LIVE (2026-07-12).** The gateway hosts 18 healthy agents at
`https://mcp.viridisconservation.com` (`/healthz` = 18 ok). Official Registry
manifests use the `io.github.jdhart81/*` namespace; the newest revenue service is
`io.github.jdhart81/taxcredit-engine`. The as-shipped manifests are in `mcp-publish-github/`
(the `mcp-publish/` set holds the branded `earth.viridis` variants for the
round-1b rebrand + custom domain `mcp.viridis.earth`).

The trust and settlement rails remain free. SmartScale, ProtoGen, and
Tax Credit Engine use the gateway's freemium payment loop; Tax Credit Engine
provides 100 free calls/day and then returns a $2 quote redeemable through
`redeem_payment`. See `docs/A2A_ECONOMY.md`.

---

© 2026 Viridis LLC. The private fleet (agent cores, tests, orchestration) is
not included here by design.
