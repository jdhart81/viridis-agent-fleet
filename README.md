# Viridis Agent Fleet: open-source agents for the agent economy

Deterministic, auditable MCP agents: trust and settlement rails (identity, trust, escrow, metering, arbitration, notary, surety, provenance, covenant, offsets, compute-ledger), a free conservation-valuation rail ([eco-funding](eco-funding-agent/README.md): ecological complexity with re-runnable receipts), and priced-grade services (tax credits, GHG accounting, construction takeoff, measurement, compliance). Every core is pure Python with no LLM in the serving path, and every result is content-addressed so anyone can re-verify it.

**Licensed Apache-2.0.** Run any agent yourself, fork it, embed it.

## Run an agent locally (free, forever)
```bash
pip install -r requirements-dev.txt
python3 agent-escrow-agent/adapters/mcp_server.py          # stdio MCP
python3 run_fleet_tests.py                                 # every agent's invariant tests
```

## Or use the hosted fleet
`https://mcp.viridisconservation.com` runs all agents as one managed MCP service:

| | Self-hosted (this repo) | Hosted by Viridis |
|---|---|---|
| Agent logic & verification | ✅ identical | ✅ identical |
| Viridis-signed receipts & notary chain | – | ✅ |
| Shared trust/reputation network data | – | ✅ |
| Maintained rule packs (tax, GHG factors, regs) | snapshot | ✅ kept current |
| Payments (x402, card), seats, SLA | – | ✅ |

Free tier: 10 calls/day per service; the rails (identity, escrow, metering…) are free forever. Verification is always free.

## Registry servers with their own docs

Every registered MCP server has a page with its tools and every input, a real example request and response, client config, authentication and pricing, and how the hosted endpoint relates to this repository:

| Registry name | Remote endpoint | Docs | Live status |
|---|---|---|---|
| `io.github.jdhart81/agent-arbitration` | `https://mcp.viridisconservation.com/arbitration/mcp` | [docs/servers/agent-arbitration.md](docs/servers/agent-arbitration.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-arbitration)](https://mcptry.com/servers/io.github.jdhart81/agent-arbitration) |
| `io.github.jdhart81/agent-compute-ledger` | `https://mcp.viridisconservation.com/compute-ledger/mcp` | [docs/servers/agent-compute-ledger.md](docs/servers/agent-compute-ledger.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-compute-ledger)](https://mcptry.com/servers/io.github.jdhart81/agent-compute-ledger) |
| `io.github.jdhart81/agent-covenant` | `https://mcp.viridisconservation.com/covenant/mcp` | [docs/servers/agent-covenant.md](docs/servers/agent-covenant.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-covenant)](https://mcptry.com/servers/io.github.jdhart81/agent-covenant) |
| `io.github.jdhart81/agent-erc8004-bridge` | `https://mcp.viridisconservation.com/erc8004/mcp` | [docs/servers/agent-erc8004-bridge.md](docs/servers/agent-erc8004-bridge.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-erc8004-bridge)](https://mcptry.com/servers/io.github.jdhart81/agent-erc8004-bridge) |
| `io.github.jdhart81/agent-escrow` | `https://mcp.viridisconservation.com/escrow/mcp` | [docs/servers/agent-escrow.md](docs/servers/agent-escrow.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-escrow)](https://mcptry.com/servers/io.github.jdhart81/agent-escrow) |
| `io.github.jdhart81/agent-hive-orchestrator` | `https://mcp.viridisconservation.com/hive/mcp` | [docs/servers/agent-hive-orchestrator.md](docs/servers/agent-hive-orchestrator.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-hive-orchestrator)](https://mcptry.com/servers/io.github.jdhart81/agent-hive-orchestrator) |
| `io.github.jdhart81/agent-identity-registry` | `https://mcp.viridisconservation.com/identity/mcp` | [docs/servers/agent-identity-registry.md](docs/servers/agent-identity-registry.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-identity-registry)](https://mcptry.com/servers/io.github.jdhart81/agent-identity-registry) |
| `io.github.jdhart81/agent-market-network` | `https://mcp.viridisconservation.com/network/mcp` | [docs/servers/agent-market-network.md](docs/servers/agent-market-network.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-market-network)](https://mcptry.com/servers/io.github.jdhart81/agent-market-network) |
| `io.github.jdhart81/agent-metering` | `https://mcp.viridisconservation.com/metering/mcp` | [docs/servers/agent-metering.md](docs/servers/agent-metering.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-metering)](https://mcptry.com/servers/io.github.jdhart81/agent-metering) |
| `io.github.jdhart81/agent-notary` | `https://mcp.viridisconservation.com/notary/mcp` | [docs/servers/agent-notary.md](docs/servers/agent-notary.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-notary)](https://mcptry.com/servers/io.github.jdhart81/agent-notary) |
| `io.github.jdhart81/agent-offset-clearinghouse` | `https://mcp.viridisconservation.com/offsets/mcp` | [docs/servers/agent-offset-clearinghouse.md](docs/servers/agent-offset-clearinghouse.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-offset-clearinghouse)](https://mcptry.com/servers/io.github.jdhart81/agent-offset-clearinghouse) |
| `io.github.jdhart81/agent-provenance` | `https://mcp.viridisconservation.com/provenance/mcp` | [docs/servers/agent-provenance.md](docs/servers/agent-provenance.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-provenance)](https://mcptry.com/servers/io.github.jdhart81/agent-provenance) |
| `io.github.jdhart81/agent-surety` | `https://mcp.viridisconservation.com/surety/mcp` | [docs/servers/agent-surety.md](docs/servers/agent-surety.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-surety)](https://mcptry.com/servers/io.github.jdhart81/agent-surety) |
| `io.github.jdhart81/agent-trust-oracle` | `https://mcp.viridisconservation.com/trust/mcp` | [docs/servers/agent-trust-oracle.md](docs/servers/agent-trust-oracle.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-trust-oracle)](https://mcptry.com/servers/io.github.jdhart81/agent-trust-oracle) |
| `io.github.jdhart81/agent-verified-relay` | `https://mcp.viridisconservation.com/verified/mcp` | [docs/servers/agent-verified-relay.md](docs/servers/agent-verified-relay.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-verified-relay)](https://mcptry.com/servers/io.github.jdhart81/agent-verified-relay) |
| `io.github.jdhart81/disclosure-compiler` | `https://mcp.viridisconservation.com/disclosure-compiler/mcp` | [docs/servers/disclosure-compiler.md](docs/servers/disclosure-compiler.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/disclosure-compiler)](https://mcptry.com/servers/io.github.jdhart81/disclosure-compiler) |
| `io.github.jdhart81/eco-funding` | `https://mcp.viridisconservation.com/eco-funding/mcp` | [docs/servers/eco-funding.md](docs/servers/eco-funding.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/eco-funding)](https://mcptry.com/servers/io.github.jdhart81/eco-funding) |
| `io.github.jdhart81/ghg-ledger` | `https://mcp.viridisconservation.com/ghg-ledger/mcp` | [docs/servers/ghg-ledger.md](docs/servers/ghg-ledger.md) · [ghg-ledger-agent/README.md](ghg-ledger-agent/README.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/ghg-ledger)](https://mcptry.com/servers/io.github.jdhart81/ghg-ledger) |
| `io.github.jdhart81/green-router` | `https://mcp.viridisconservation.com/green-router/mcp` | [docs/servers/green-router.md](docs/servers/green-router.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/green-router)](https://mcptry.com/servers/io.github.jdhart81/green-router) |
| `io.github.jdhart81/maxwell-defense` | `https://mcp.viridis-security.com/maxwell-defense/mcp` | [docs/servers/maxwell-defense.md](docs/servers/maxwell-defense.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/maxwell-defense)](https://mcptry.com/servers/io.github.jdhart81/maxwell-defense) |
| `io.github.jdhart81/narrative-engine` | `https://mcp.viridisconservation.com/narrative-engine/mcp` | [docs/servers/narrative-engine.md](docs/servers/narrative-engine.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/narrative-engine)](https://mcptry.com/servers/io.github.jdhart81/narrative-engine) |
| `io.github.jdhart81/neurogenesis` | `https://mcp.viridisconservation.com/neurogenesis/mcp` | [docs/servers/neurogenesis.md](docs/servers/neurogenesis.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/neurogenesis)](https://mcptry.com/servers/io.github.jdhart81/neurogenesis) |
| `io.github.jdhart81/protogen` | `https://mcp.viridisconservation.com/protogen/mcp` | [docs/servers/protogen.md](docs/servers/protogen.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/protogen)](https://mcptry.com/servers/io.github.jdhart81/protogen) |
| `io.github.jdhart81/quantity-takeoff` | `https://mcp.viridisconservation.com/quantity-takeoff/mcp` | [docs/servers/quantity-takeoff.md](docs/servers/quantity-takeoff.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/quantity-takeoff)](https://mcptry.com/servers/io.github.jdhart81/quantity-takeoff) |
| `io.github.jdhart81/regulatory-radar` | `https://mcp.viridisconservation.com/regulatory-radar/mcp` | [docs/servers/regulatory-radar.md](docs/servers/regulatory-radar.md) · [regulatory-radar-agent/README.md](regulatory-radar-agent/README.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/regulatory-radar)](https://mcptry.com/servers/io.github.jdhart81/regulatory-radar) |
| `io.github.jdhart81/security-preflight` | `https://mcp.viridis-security.com/security-preflight/mcp` | [docs/servers/security-preflight.md](docs/servers/security-preflight.md) · [security-preflight-agent/README.md](security-preflight-agent/README.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/security-preflight)](https://mcptry.com/servers/io.github.jdhart81/security-preflight) |
| `io.github.jdhart81/settlement-engine` | `https://mcp.viridisconservation.com/settlement-engine/mcp` | [docs/servers/settlement-engine.md](docs/servers/settlement-engine.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/settlement-engine)](https://mcptry.com/servers/io.github.jdhart81/settlement-engine) |
| `io.github.jdhart81/smartscale` | `https://mcp.viridisconservation.com/smartscale/mcp` | [docs/servers/smartscale.md](docs/servers/smartscale.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/smartscale)](https://mcptry.com/servers/io.github.jdhart81/smartscale) |
| `io.github.jdhart81/subscriptions` | `https://mcp.viridisconservation.com/subscriptions/mcp` | [docs/servers/subscriptions.md](docs/servers/subscriptions.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/subscriptions)](https://mcptry.com/servers/io.github.jdhart81/subscriptions) |
| `io.github.jdhart81/taxcredit-engine` | `https://mcp.viridisconservation.com/taxcredit-engine/mcp` | [docs/servers/taxcredit-engine.md](docs/servers/taxcredit-engine.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/taxcredit-engine)](https://mcptry.com/servers/io.github.jdhart81/taxcredit-engine) |
| `io.github.jdhart81/verdigraph` | `https://mcp.viridisconservation.com/verdigraph/mcp` | [docs/servers/verdigraph.md](docs/servers/verdigraph.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/verdigraph)](https://mcptry.com/servers/io.github.jdhart81/verdigraph) |
| `io.github.jdhart81/viridisos` | `https://mcp.viridisconservation.com/viridisos/mcp` | [docs/servers/viridisos.md](docs/servers/viridisos.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/viridisos)](https://mcptry.com/servers/io.github.jdhart81/viridisos) |
| `io.github.jdhart81/wavefunction-search` | `https://mcp.viridisconservation.com/wavefunction/mcp` | [docs/servers/wavefunction-search.md](docs/servers/wavefunction-search.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/wavefunction-search)](https://mcptry.com/servers/io.github.jdhart81/wavefunction-search) |
| `io.github.jdhart81/wu-wei-router` | `https://mcp.viridisconservation.com/wu-wei-router/mcp` | [docs/servers/wu-wei-router.md](docs/servers/wu-wei-router.md) | [![mcptry](https://mcptry.com/badge/io.github.jdhart81/wu-wei-router)](https://mcptry.com/servers/io.github.jdhart81/wu-wei-router) |

Connecting any hosted server (Claude, ChatGPT, VS Code, APIs), payments and ownership: [docs/HOSTED_MCP.md](docs/HOSTED_MCP.md).

## For agents
Agents and LLM tools can start from [llms.txt](llms.txt), a generated index of every agent, and [AGENTS.md](AGENTS.md), the rules for using and changing the fleet.

## Part of the Viridis open-source commons

Building agents for conservation or energy work? [VergeCommon](https://github.com/jdhart81/verge-common) and [EnergyAI MCP](https://github.com/jdhart81/energyai-mcp) also expose MCP tools, and [ViridisOS](https://github.com/jdhart81/viridisos) serves its decision functions to agents over MCP.

This project is one of a connected set of open tools from Viridis. Each stands on its own; together they run from field evidence to checked decisions.

**Conservation commons**

- [VergeCommon](https://github.com/jdhart81/verge-common): community conservation co-ops with consent-based land mapping, field evidence and group decisions
- [Dendritic Forest Management (DFM)](https://github.com/jdhart81/hdfm-framework): compare forest-retention options around roads and waterways, with traceable inputs and portable reports
- [Global Soil Intelligence Project (GSIP)](https://github.com/global-soil-intelligence/gsip): contribute soil observations and explore open soil maps with explicit uncertainty

**Verifiable science**

- [Viridis Canon](https://github.com/jdhart81/viridis-canon): machine-checked Lean 4 mathematics for ecological decisions, with a DOI for every result
- [ViridisOS](https://github.com/jdhart81/viridisos): open reference runtime for DOI-backed decision modules and recomputable results
- [Viridis Research](https://github.com/jdhart81/viridis-research): the nightly public research record, each claim labeled by what a verifier actually checked
- [ProofLens](https://github.com/jdhart81/prooflens): see what a Lean statement means before reading the proof

**Agent tools**

- **Viridis Agent Fleet** (this repository): open-source MCP agents with deterministic, auditable cores
- [EnergyAI MCP](https://github.com/jdhart81/energyai-mcp): energy-planning estimates and incentive sources for AI agents

Browse every project on the [Viridis profile](https://github.com/jdhart81). If this one is useful to you, a star helps other people find it.

## Boundary
This repo contains agent cores, MCP adapters, tests, standards and self-host tooling. The hosted service layer (gateway, payment and settlement, seats, signing authority, operations, telemetry and customer data) is proprietary and is not in this repo. Please don't open PRs that add it.

"Viridis", "Viridis Conservation" and the Viridis marks are trademarks of Viridis LLC; see `TRADEMARKS.md`.
