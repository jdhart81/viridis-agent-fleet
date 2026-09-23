# DEPLOY — agent-trust-oracle-agent

Reputation rail: decay-weighted scores + hash-chained attestations. Consumes settlement outcomes from escrow/metering.

## Serve
```
cd agent-trust-oracle-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridis.earth/trust/mcp` (streamable-http).

## Environment
none (stdlib core; in-memory state)

## How a calling agent uses it
Connect any MCP client to the server and call the tools in `tools.json`
(key tools: score_agent / record_outcome / attest). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope — callers
never see an exception.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py agent-trust-oracle-agent`
2. Fill the placeholders in `server.json` (repository.url, remote URL).
3. Follow the shared click-path in `deploy/mcp-publish/README.md`.
