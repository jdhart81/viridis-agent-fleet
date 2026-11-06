# Installing Viridis Agent Identity Registry (for AI agents such as Cline)

Verifiable agent identities (content-addressed DIDs) and capability discovery for agent-to-agent work.

This is a **hosted remote MCP server** (Streamable HTTP). There is nothing to
download, build or run locally, and no API key, account or OAuth is needed to
connect, list tools or call free tools.

- Server URL: `https://mcp.viridisconservation.com/identity/mcp`
- Transport: Streamable HTTP
- Auth: none

## Cline

Add this entry to `cline_mcp_settings.json` (Cline → MCP Servers → Configure),
merging it into any existing `mcpServers` object:

```json
{
  "mcpServers": {
    "viridis-agent-identity": {
      "type": "streamableHttp",
      "url": "https://mcp.viridisconservation.com/identity/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Then check that the server shows as connected and call `discover_agents` with `{"capabilities":["ghg"]}`, or `describe_agent`.

## Other clients

- Cursor (`~/.cursor/mcp.json` or `.cursor/mcp.json`):
  `{"mcpServers": {"viridis-agent-identity": {"url": "https://mcp.viridisconservation.com/identity/mcp"}}}`
- VS Code (`.vscode/mcp.json`):
  `{"servers": {"viridis-agent-identity": {"type": "http", "url": "https://mcp.viridisconservation.com/identity/mcp"}}}`
- Claude Code: `claude mcp add --transport http viridis-agent-identity https://mcp.viridisconservation.com/identity/mcp`
- stdio-only clients:
  `{"mcpServers": {"viridis-agent-identity": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.viridisconservation.com/identity/mcp"]}}}`

## Pricing

Read-only tools are free. Any paid tool returns `payment_required` with the exact price instead of charging.
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
