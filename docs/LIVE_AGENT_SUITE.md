# Live Viridis x402 agent suite

Distribution readback: September 8, 2026. Prices and settlement counts were checked against live public fleet telemetry.

Start with Security Preflight: check your own MCP manifest and policy.
Static supplied-artifact assessment with a signed, redacted receipt; it does not test or certify a deployed runtime.
Buyer walkthrough: https://mcp.viridis-security.com/security-preflight/quickstart

1. Inspect a free quote with the published buyer client; no wallet is loaded.
2. Use your own inputs and explicitly authorize one capped Base USDC purchase.
3. Save the result privately and decide whether the findings are useful.
4. Attach the free change check to your release workflow. Unchanged inputs reuse the baseline; a relevant change needs a fresh quote and buyer authorization.

Live list prices (the buyer's fresh x402 quote governs):
- quantity-takeoff/calculate_takeoff — $0.50
- ghg-ledger/calculate_inventory — $1.00
- disclosure-compiler/compile_disclosure — $2.00
- taxcredit-engine/calculate_tax_credit — $2.00
- regulatory-radar/scan_regulations — $0.25
- regulatory-radar/monitor_changes — $0.25
- hive/solve — $5.00
- security-preflight/security_preflight — $1.00
Eligible introductory quotes may be $0.01; inspect your quote before signing.

Regulatory Radar remains the climate/compliance entry path:
https://mcp.viridisconservation.com/quickstart
Full fleet: https://mcp.viridisconservation.com/agents

Observed external settlements: 4 from 4 distinct payer wallets.
These are fleet-wide payments, not evidence of Security purchases, buyer acceptance, usefulness, or repeat adoption.
