# Live Viridis x402 agent suite

This file is maintained by the isolated Viridis growth worker from live public route, price, and settlement telemetry.

Live x402 carbon + compliance agent workflow on Base: measure → account → disclose → claim → scan

• quantity-takeoff — $0.50: Embodied carbon quantity takeoff from a bill of materials or explicit construction geometry, producing auditable material quantities for carbon accounting. The measure step pairs with the Viridis GHG inventory and sustainability disclosure engines.
• ghg-ledger — $1.00: Deterministic greenhouse gas inventory API for auditable Scope 1, 2, and 3 accounting from explicit activity records. The accounting step pairs with Viridis embodied-carbon takeoff, disclosure, and tax-credit engines.
• disclosure-compiler — $2.00: CSRD / IFRS S2 (TCFD-aligned) sustainability disclosure compiler from supplied company facts and optional verified emissions data. The disclose step pairs with Viridis GHG inventory, regulation-scan, and clean-energy tax-credit engines.
• taxcredit-engine — $2.00: Auditable US clean-energy tax-credit calculator from explicit credit-specific facts. The claim step pairs with the Viridis GHG inventory and sustainability disclosure engines for a chainable compliance workflow.
• regulatory-radar — $0.25: Energy and climate compliance regulation scan across a curated 14-regulation database, with jurisdiction, urgency, and effective-date signals. The scan step pairs with Viridis GHG inventory, sustainability disclosure, and clean-energy tax-credit engines.

No signup or API key. A caller receives HTTP 402, settles Base USDC, and gets the deterministic result.
First paid call from a new wallet is $0.01.
Live external proof: 1 settlement(s) from 1 distinct payer(s).

Free dry-run: https://mcp.viridisconservation.com/quickstart
Agent suite: https://mcp.viridisconservation.com/agents
