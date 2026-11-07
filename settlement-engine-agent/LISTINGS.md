# Directory listing copy — Viridis Settlement Engine

Hosted: `https://mcp.viridisconservation.com/settlement-engine/mcp` (Streamable HTTP, no auth to connect; `compile_contract` and `settle_contract` $1.00 via x402/USDC on Base or fleet credits; everything else free). Self-host: `settlement-engine-agent/` in this repository. Support/contact for listings: the fleet's listed support address.

## One line (≤ 120 chars)
Settle outcome contracts on officially published data — what is already decided, what the remainder must do, recomputable.

## Short (≤ 280 chars)
Progressive settlement for outcome-based capital. Register any officially published series (ISO power prices, election counts, restoration survival), see what the published part has already decided, what the remainder must do, and settle contracts with evidence hashes anyone can recompute.

## Long
The Viridis Settlement Engine is the arithmetic layer for agreements that settle on an official series published a piece at a time: ISO electricity prices (ERCOT today, PJM/MISO next), election counts, restoration milestones (stems alive, canopy, soil carbon), grid intensity. For each registered series it reports, from the published observations alone, the published share and aggregate, the exact value the remaining slots must average (or sum to, or hit) for a strike to settle YES, and which strikes are **decided by arithmetic plus the series' declared physical bounds** — never by a model. Model estimates are returned separately and never decide anything.

Paid tools compile a content-addressed Verified Outcome Contract (series, strike, rule, closing time) and settle it at an explicit time: YES, NO or UNDECIDED with every observation hash used. A decided strike settles before closure; an incomplete, undecided series at closure is UNDECIDED, never a guess. Settlements are immutable, and `verify_settlement` recomputes any of them for free.

No forecasting, no trading, no keys, no LLM in the serving path. Deterministic Python with `Decimal` arithmetic; 10 invariants in the core docstring; tests and mutation checks in the repository.

Tools: `register_series`, `ingest`, `period_status`, `required_remainder`, `decided_strikes`, `explain`, `list_series`, `get_contract`, `verify_settlement`, `describe_agent` (free); `compile_contract`, `settle_contract` (paid).

Live series today: ERCOT North / Houston / West real-time average price, weekly and monthly Kalshi contract periods, refreshed every 15 minutes from ERCOT's NP6-905-CD postings.

## Tags / categories
settlement · outcome-contracts · pay-for-success · energy · ERCOT · electricity prices · elections · restoration · verification · deterministic · x402

## Example prompts (what a calling agent would ask)
- "What must the rest of the week average for ERCOT North to settle above $30?"
- "Is the ERCOT Houston monthly >$40 contract already decided by the published intervals?"
- "Settle this pay-for-success restoration milestone on the verified survival counts."
- "Verify this settlement from its evidence hashes."

## Client config
```json
{"mcpServers": {"viridis-settlement-engine": {"type": "streamableHttp", "url": "https://mcp.viridisconservation.com/settlement-engine/mcp"}}}
```

## Where to submit (Justin's clicks)
Claude directory · ChatGPT app/connector directory · Smithery · Glama · PulseMCP · mcp.so · the fleet's own `/agents` page (already live).
