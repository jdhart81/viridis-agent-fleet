# DEPLOY — agent-compute-ledger-agent

Compute-is-carbon ledger: J, gCO2e, Landauer efficiency, verifiable attestations.

## Serve
```
cd agent-compute-ledger-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridis.earth/compute-ledger/mcp` (streamable-http).

## Environment
none (stdlib core; in-memory state)

## How a calling agent uses it
Connect any MCP client to the server and call the tools in `tools.json`
(key tools: record_work / footprint / attest). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope — callers
never see an exception.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py agent-compute-ledger-agent`
2. Fill the placeholders in `server.json` (repository.url, remote URL).
3. Follow the shared click-path in `deploy/mcp-publish/README.md`.
