# DEPLOY — agent-identity-registry-agent

The hub: other agents register verifiable DIDs and are discovered by capability. Publish FIRST - trust and escrow reference identities.

## Serve
```
cd agent-identity-registry-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridis.earth/identity/mcp` (streamable-http).

## Environment
none (stdlib core; in-memory state - add a persistence adapter before production scale)

## How a calling agent uses it
Connect any MCP client to the server and call the tools in `tools.json`
(key tools: register_agent / discover_agents). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope — callers
never see an exception.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py agent-identity-registry-agent`
2. Fill the placeholders in `server.json` (repository.url, remote URL).
3. Follow the shared click-path in `deploy/mcp-publish/README.md`.
