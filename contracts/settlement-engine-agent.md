# Viridis Settlement Engine

Progressive settlement for outcome-based capital. For any agreement that settles on an officially published series
(ISO electricity prices, election counts, restoration survival, canopy, soil carbon, grid intensity) the engine reports,
from the published part alone, what is already known, what the remainder must do for an outcome to settle, which strikes
are decided by arithmetic plus the series' declared physical bounds, and produces immutable settlements that any third
party can recompute from the evidence hashes they carry.

The serving path is Python stdlib and `Decimal`: no inference, no network, no keys, no trading. Model estimates are
returned under a separate, versioned `model` block and never decide anything. Observations enter through ingestion
adapters as data with a source URL and the source document's SHA-256.

This engine computes settlements on supplied data; it does not provide accounting, assurance, legal, financial, or
investment advice, and a settlement is not a payment.

## MCP

```bash
python3 adapters/mcp_server.py
python3 adapters/mcp_server.py --serve
```

Tools: `register_series`, `ingest`, `period_status`, `required_remainder`, `decided_strikes`, `explain`, `list_series`,
`compile_contract`, `get_contract`, `settle_contract`, `verify_settlement`, `describe_agent`.

Hosted route (proposed): `https://mcp.viridisconservation.com/settlement-engine/mcp`.
Pricing (proposed, Justin sets): facts, decided-strike detection, explanations and verification free; `compile_contract`
$1.00 and `settle_contract` $5.00 through the fleet payment-credit gate; enterprise terms for a carried share of outcome
value on restoration contracts verified through VergeCommon D-Score.

## Test

```bash
python3 -m unittest discover -s tests -v
```
