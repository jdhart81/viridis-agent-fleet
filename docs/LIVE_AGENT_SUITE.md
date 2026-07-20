# Live Viridis x402 agent suite

This owned-repository discovery page is maintained from Viridis's live public
route, price, and settlement telemetry. The isolated growth worker may refresh
this file through GitHub's Contents API; it cannot create issues, modify other
paths, or write to third-party repositories.

Five deterministic tools chain into one workflow:

| Step | Agent | List price |
|---|---|---:|
| Measure | quantity-takeoff | $0.50 |
| Account | ghg-ledger | $1.00 |
| Disclose | disclosure-compiler | $2.00 |
| Claim | taxcredit-engine | $2.00 |
| Scan | regulatory-radar | $0.25 |

No signup or API key is required. A caller receives HTTP 402, signs the exact
Base-USDC authorization, and receives the deterministic result only after
successful settlement. The first paid call from a new wallet is currently
$0.01; subsequent calls use list price.

- Agent suite: https://mcp.viridisconservation.com/agents
- Free dry-run: https://mcp.viridisconservation.com/quickstart
- Agent-readable catalog: https://mcp.viridisconservation.com/llms.txt
- Machine catalog: https://mcp.viridisconservation.com/x402/catalog
