# DEPLOY — agent-provenance-agent

Birth certificates + bloodlines; founding-cohort scarcity by construction; cascading recall containment.

## Serve
```
cd agent-provenance-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridis.earth/provenance/mcp` (streamable-http).

## Environment
none (stdlib core; in-memory state)

## How a calling agent uses it
Connect any MCP client and call the tools in `tools.json`
(key tools: register_genesis / lineage / recall). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py agent-provenance-agent`
2. Fill the placeholders in `server.json` (repository.url, remote URL).
3. Follow the shared click-path in `deploy/mcp-publish/README.md`.
