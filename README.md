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

## Boundary
This repo contains agent cores, MCP adapters, tests, standards and self-host tooling. The hosted service layer (gateway, payment and settlement, seats, signing authority, operations, telemetry and customer data) is proprietary and is not in this repo. Please don't open PRs that add it.

"Viridis", "Viridis Conservation" and the Viridis marks are trademarks of Viridis LLC; see `TRADEMARKS.md`.
