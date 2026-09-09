# Discover and choose a Viridis service

Agents can inspect the [paid catalog](https://mcp.viridisconservation.com/x402/catalog), [OpenAPI schema](https://mcp.viridisconservation.com/openapi.json), [A2A card](https://mcp.viridisconservation.com/.well-known/agent-card.json), and [machine guide](https://mcp.viridisconservation.com/llms.txt). The official MCP Registry advertises the remote Security server under `io.github.jdhart81/security-preflight`, metadata version 1.3.0.

POST a buyer objective to `https://mcp.viridisconservation.com/adopt`. Without required input it identifies the relevant service and missing fields. With valid supplied input it prepares a quote plan. This free endpoint does not execute tools or authorize payment. Inspect the actual unpaid HTTP 402 challenge and set your spending limit before a purchase.

| Buyer task | Service |
|---|---|
| Check MCP manifest and tool authority | Security Preflight |
| Review inline source for vulnerability indicators | VulnCanon source scan |
| Screen text/messages for injection markers | Injection screening |
| Compute construction material quantities | Quantity Takeoff |
| Calculate an emissions inventory | GHG Ledger |
| Prepare a climate disclosure draft | Disclosure Compiler |
| Estimate supported clean-energy tax credits | TaxCredit Engine |
| Review applicable curated regulations | Regulatory Radar scan |
| Review dated regulatory deadlines | Regulatory Radar monitor |
| Obtain a bounded reviewed synthesis | Hive |

Each catalog entry describes the job, expected outcome and limitations. These are scoped services, not security certification, tax/legal advice or guaranteed correctness. The [Security buyer guide](STATIC_SECURITY_BUYER_QUICKSTART.md) covers prices, limits, privacy and a capped purchase.

## Discovery regression checks

`python3 scripts/agent_search_audit.py` performs 24 fixed, free intent checks plus catalog, OpenAPI and Bazaar merchant-inventory checks. It uses no model, wallet or payment. Its JSON output separates local route selection from external indexing; neither proves demand or revenue. This is a bounded regression set, not a comprehensive language benchmark. `config/agent_search_cases.json` is the versioned query set.

The 9 September release corrected message-oriented prompt-injection requests that previously selected the manifest checker. All 24 cases passed after production restart. All ten service contracts passed their audit. Bazaar indexed four of ten services at that readback; missing entries and external ranking remain separate work. We do not manufacture paid calls to improve rankings.

The routing patch in `docs/deployment/patches/agent-search-routing-20260909.patch` applies to the recorded production routing source, not the older reference gateway in this public repository. It was deployed as a one-file overlay preserving intervening fleet updates. Private Security engines, accounting ledgers and customer records are not included.
