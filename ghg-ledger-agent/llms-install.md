# Installing Viridis GHG Ledger (for AI agents such as Cline)

Deterministic Scope 1/2/3 greenhouse-gas inventories from activity data, with factor lineage and a re-verifiable audit hash.

This is a **hosted remote MCP server** (Streamable HTTP). There is nothing to
download, build or run locally, and no API key, account or OAuth is needed to
connect, list tools or call free tools.

- Server URL: `https://mcp.viridisconservation.com/ghg-ledger/mcp`
- Transport: Streamable HTTP
- Auth: none

## Cline

Add this entry to `cline_mcp_settings.json` (Cline → MCP Servers → Configure),
merging it into any existing `mcpServers` object:

```json
{
  "mcpServers": {
    "viridis-ghg-ledger": {
      "type": "streamableHttp",
      "url": "https://mcp.viridisconservation.com/ghg-ledger/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Then check that the server shows as connected and call `calculate_inventory` with one line, e.g. `{"activities":[{"activity_type":"electricity","quantity":1000,"unit":"kWh","region":"US","year":2024}]}`, or the free `list_factor_packs`.

## Other clients

- Cursor (`~/.cursor/mcp.json` or `.cursor/mcp.json`):
  `{"mcpServers": {"viridis-ghg-ledger": {"url": "https://mcp.viridisconservation.com/ghg-ledger/mcp"}}}`
- VS Code (`.vscode/mcp.json`):
  `{"servers": {"viridis-ghg-ledger": {"type": "http", "url": "https://mcp.viridisconservation.com/ghg-ledger/mcp"}}}`
- Claude Code: `claude mcp add --transport http viridis-ghg-ledger https://mcp.viridisconservation.com/ghg-ledger/mcp`
- stdio-only clients:
  `{"mcpServers": {"viridis-ghg-ledger": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.viridisconservation.com/ghg-ledger/mcp"]}}}`

## Pricing

`calculate_inventory` includes 10 free calls per caller per UTC day, then $1.00 per call. `classify_activity`, `list_factor_packs`, `get_factor_pack`, `verify_result` and `describe_agent` are free.
Nothing is charged without a separate, explicit payment by the caller (card
checkout or the caller's own x402 wallet). See
[docs/HOSTED_MCP.md](../docs/HOSTED_MCP.md).

## Troubleshooting

- `payment_required`: the free daily allowance is used up; the response gives
  the price and how to pay. Free tools keep working.
- Connection refused or 404: check the URL ends in `/mcp` and the transport is
  Streamable HTTP, not SSE.

Self-hosting is optional: the server code is Apache-2.0 in this folder; see
[README.md](README.md).

Operated by ViridisNorth LLC. Contact: hartjustin6@gmail.com.
