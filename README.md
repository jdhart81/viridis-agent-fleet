# Viridis Agent Fleet: open-source agents for the agent economy

Deterministic, auditable MCP agents: trust and settlement rails (identity, trust, escrow, metering, arbitration, notary, surety, provenance, covenant, offsets, compute-ledger) and priced-grade services (tax credits, GHG accounting, construction takeoff, measurement, compliance). Every core is pure Python with no LLM in the serving path, and every result is content-addressed so anyone can re-verify it.

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

## Independent tool-list baseline
[Dominion Observatory](https://dominionobservatory.com), an independent service that watches MCP tool manifests for changes, signed a baseline of the hosted network endpoint `https://mcp.viridisconservation.com/network/mcp` on 5 November 2026 ([issue #122](https://github.com/jdhart81/viridis-agent-fleet/issues/122)):

- 23 tools, captured 2026-11-05T02:31:15Z
- Signed (Ed25519, key `capture-a46fe710c055398f3b6f43a1`) over each tool's `name`, `description` and `inputSchema`, sorted by name; SHA-256 `6eb8564d1975f2601773a3384360a528ab2b6426d5739080d1d221145820c0b6`
- Public record: [Dominion capture history](https://dominionobservatory.com/api/drift?server=https%3A%2F%2Fmcp.viridisconservation.com%2Fnetwork%2Fmcp), verification key: [capture-jwks.json](https://dominionobservatory.com/.well-known/capture-jwks.json)

Anyone can compare a fresh `tools/list` from the endpoint against that record. The `annotations` and `outputSchema` fields are outside the signature. The baseline is a dated observation by a third party, not a claim about tool safety, behaviour or current availability.

## Registry servers with their own docs

Each registered MCP server has a README with its tools, inputs and outputs, an example, client config and pricing:

| Registry name | Remote endpoint | Docs |
|---|---|---|
| `io.github.jdhart81/security-preflight` | `https://mcp.viridis-security.com/security-preflight/mcp` | [security-preflight-agent/README.md](security-preflight-agent/README.md) |
| `io.github.jdhart81/regulatory-radar` | `https://mcp.viridisconservation.com/regulatory-radar/mcp` | [regulatory-radar-agent/README.md](regulatory-radar-agent/README.md) |
| `io.github.jdhart81/ghg-ledger` | `https://mcp.viridisconservation.com/ghg-ledger/mcp` | [ghg-ledger-agent/README.md](ghg-ledger-agent/README.md) |

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
