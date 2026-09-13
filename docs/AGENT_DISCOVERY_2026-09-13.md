# Viridis services for agent buyers

Verified September 13, 2026: 29 healthy native fleet agents and 11 paid HTTP routes. These are service counts, not customer or usage counts.

Start with the [free selector](https://mcp.viridisconservation.com/.well-known/agent-adoption.json), [live priced catalog](https://mcp.viridisconservation.com/x402/catalog), [OpenAPI input contracts](https://mcp.viridisconservation.com/openapi.json), [A2A Agent Card](https://mcp.viridisconservation.com/.well-known/agent-card.json), or [machine guide](https://mcp.viridisconservation.com/llms.txt).

## Find the operation for your job

| Operation | USDC list price | Canonical HTTP endpoint |
|---|---:|---|
| regulatory-radar/scan_regulations | 0.25 | https://mcp.viridisconservation.com/x402/regulatory-radar/scan_regulations |
| regulatory-radar/monitor_changes | 0.25 | https://mcp.viridisconservation.com/x402/regulatory-radar/monitor_changes |
| taxcredit-engine/calculate_tax_credit | 2.00 | https://mcp.viridisconservation.com/x402/taxcredit-engine/calculate_tax_credit |
| ghg-ledger/calculate_inventory | 1.00 | https://mcp.viridisconservation.com/x402/ghg-ledger/calculate_inventory |
| quantity-takeoff/calculate_takeoff | 0.50 | https://mcp.viridisconservation.com/x402/quantity-takeoff/calculate_takeoff |
| disclosure-compiler/compile_disclosure | 2.00 | https://mcp.viridisconservation.com/x402/disclosure-compiler/compile_disclosure |
| hive/solve | 5.00 | https://mcp.viridisconservation.com/x402/hive/solve |
| security-preflight/security_preflight | 1.00 | https://mcp.viridisconservation.com/x402/security-preflight/security_preflight |
| security-preflight/scan_source | 1.00 | https://mcp.viridisconservation.com/x402/security-preflight/scan_source |
| security-preflight/screen_injection | 1.00 | https://mcp.viridisconservation.com/x402/security-preflight/screen_injection |
| maxwell-defense/rehearse_defense | 1.00 | https://mcp.viridis-security.com/x402/maxwell-defense/rehearse_defense |

Prices are per operation. The fresh unpaid quote is authoritative; introductory eligibility may affect supported routes. No price discount applies to Maxwell, source scans or injection screening.

## Maxwell Defense Rehearsal

[Product](https://mcp.viridis-security.com/maxwell-defense) · [Service contract](https://mcp.viridis-security.com/maxwell-defense/service.json)

MCP endpoint: `https://mcp.viridis-security.com/maxwell-defense/mcp`; tool: `rehearse_defense`.

Models a proof-of-work policy and latency from supplied workload limits, with a local SHA-256 microbenchmark. It does not activate runtime protection, certify security or measure energy savings.

Quote-only request (no payment headers or wallet):

```sh
curl --request POST 'https://mcp.viridis-security.com/x402/maxwell-defense/rehearse_defense' \
  --header 'Content-Type: application/json' \
  --data '{"client_hashes_per_second":100000,"client_p95_budget_ms":250,"backend_cost_ms":2000,"peak_requests_per_second":100}'
```

HTTP 402 returns payment terms. Payment requires separate buyer authorization; discovery does not debit a wallet.

## External discovery evidence

Official MCP Registry entries are checked by name, active/latest status and remote endpoint. Directory listings, search rank, paid execution and useful delivery are separate measurements. Bazaar indexed 4 of 11 paid fleet routes at the September 13 audit. Glama and MCP.so retained stale summary/tool-detection content. No universal agent search engine or ranking guarantee is claimed.

The hosted service is the execution layer. This repository publishes integration metadata and examples; the Maxwell managed-protection implementation is not released here.
