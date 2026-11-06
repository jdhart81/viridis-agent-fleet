# Installing Viridis Regulatory Radar (for AI agents such as Cline)

Climate and ESG regulation screening: applicable rules, effective dates, deadlines and compliance gaps by jurisdiction and sector, with source URLs.

This is a **hosted remote MCP server** (Streamable HTTP). There is nothing to
download, build or run locally, and no API key, account or OAuth is needed to
connect, list tools or call free tools.

- Server URL: `https://mcp.viridisconservation.com/regulatory-radar/mcp`
- Transport: Streamable HTTP
- Auth: none

## Cline

Add this entry to `cline_mcp_settings.json` (Cline → MCP Servers → Configure),
merging it into any existing `mcpServers` object:

```json
{
  "mcpServers": {
    "viridis-regulatory-radar": {
      "type": "streamableHttp",
      "url": "https://mcp.viridisconservation.com/regulatory-radar/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Then check that the server shows as connected and call `scan_regulations` with `{"jurisdiction":"california","sector":"manufacturing"}`.

## Other clients

- Cursor (`~/.cursor/mcp.json` or `.cursor/mcp.json`):
  `{"mcpServers": {"viridis-regulatory-radar": {"url": "https://mcp.viridisconservation.com/regulatory-radar/mcp"}}}`
- VS Code (`.vscode/mcp.json`):
  `{"servers": {"viridis-regulatory-radar": {"type": "http", "url": "https://mcp.viridisconservation.com/regulatory-radar/mcp"}}}`
- Claude Code: `claude mcp add --transport http viridis-regulatory-radar https://mcp.viridisconservation.com/regulatory-radar/mcp`
- stdio-only clients:
  `{"mcpServers": {"viridis-regulatory-radar": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.viridisconservation.com/regulatory-radar/mcp"]}}}`

## Pricing

`scan_regulations`, `assess_compliance`, `monitor_changes` and `build_evidence_pack` include 10 free calls per caller per UTC day over MCP, then $0.25 per call. `describe_agent` is free. Results are screening only, not legal advice.
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
