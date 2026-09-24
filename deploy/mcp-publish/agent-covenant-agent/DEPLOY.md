# DEPLOY — agent-covenant-agent

Deny-by-default authority leases: the safety envelope every real-authority agent needs. The audit chain is the product.

## Serve
```
cd agent-covenant-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridis.earth/covenant/mcp` (streamable-http).

## Environment
none (stdlib core; in-memory state)

## How a calling agent uses it
Connect any MCP client and call the tools in `tools.json`
(key tools: grant_covenant / check_act / revoke_covenant). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py agent-covenant-agent`
2. Fill the placeholders in `server.json` (repository.url, remote URL).
3. Follow the shared click-path in `deploy/mcp-publish/README.md`.
