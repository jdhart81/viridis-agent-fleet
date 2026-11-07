# settlement-engine — publish notes

Hosted remote: `https://mcp.viridisconservation.com/settlement-engine/mcp` (Streamable HTTP; live since 2026-11-06 23:17Z).
Paid tools: `compile_contract`, `settle_contract` ($1.00 via x402 USDC on Base at `/x402/settlement-engine/<tool>`, or fleet credits/seats). All other tools free.
Registry name: `io.github.jdhart81/settlement-engine` (same namespace and OIDC method as the other fleet servers).
Publish: run the `Publish Settlement Engine MCP` workflow (workflow_dispatch) after the manifest is on `main`; it validates then publishes this `server.json`.
