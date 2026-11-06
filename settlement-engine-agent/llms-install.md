# Installing Viridis Settlement Engine (for AI agents such as Cline)

Progressive settlement for outcome-based capital: what an officially published series (ISO electricity prices, election counts, restoration survival, canopy, soil carbon) has already decided, what the remainder must do, and recomputable settlements of outcome contracts on it.

Self-host, free: `python3 settlement-engine-agent/adapters/mcp_server.py --serve` (stdio MCP, `pip install mcp`).

Hosted (when the route is live): `https://mcp.viridisconservation.com/settlement-engine/mcp`, Streamable HTTP, no auth to connect; `compile_contract` and `settle_contract` are the paid tools.

```json
{
  "mcpServers": {
    "viridis-settlement-engine": {
      "type": "streamableHttp",
      "url": "https://mcp.viridisconservation.com/settlement-engine/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```
