# Viridis GHG Ledger

Deterministic greenhouse-gas inventory calculations for explicit Scope 1, 2,
and 3 activity data. The serving path uses Python stdlib, `Decimal`, and one
bundled factor pack—no inference, network lookup, paid API, or guessed factor.

The v0.1.0 pack deliberately covers a focused MVP: selected US stationary and
mobile fuels, two refrigerants, US/eGRID and UK electricity, and starter Scope
3 Categories 1, 5, and 6. Anything outside the exact activity/region/year pack
returns `indeterminate` and is excluded from totals.

Every result includes gas/direct-CO2e resolution, Scope and category rollups,
location- and market-based Scope 2, an ESRS E1-shaped summary, the specific
factor sources used, an authenticated lineage block, `audit_sha256`, a notary
payload, and an integer-gram offset-clearinghouse dry-run weave.

This engine calculates supplied data; it does not provide accounting,
assurance, filing, lifecycle-analysis, legal, or regulatory advice.

## MCP

```bash
python3 adapters/mcp_server.py
python3 adapters/mcp_server.py --serve
```

Tools: `calculate_inventory`, `classify_activity`, `list_factor_packs`,
`get_factor_pack`, `verify_result`, and `describe_agent`.

Hosted route: `https://mcp.viridisconservation.com/ghg-ledger/mcp`.
Pricing: 100 free inventory calculations per UTC day, then $1.00 each through
the fleet payment-credit gate. Classification, factor reads, and verification
remain free.

## Test

```bash
python3 -m unittest discover -s tests -v
```
