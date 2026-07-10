# DEPLOY — agent-escrow-agent

Settlement rail: exactly-once state machine + audit chain. NO fund custody - wire a Stripe/x402 rail adapter before real money; state machine only records intent.

## Serve
```
cd agent-escrow-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridis.earth/escrow/mcp` (streamable-http).

## Environment
PAYMENT_RAIL_* (only when a custody adapter is added; none for the state-machine service)

## How a calling agent uses it
Connect any MCP client to the server and call the tools in `tools.json`
(key tools: open_escrow / fund_escrow / release_escrow). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope — callers
never see an exception.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py agent-escrow-agent`
2. Fill the placeholders in `server.json` (repository.url, remote URL).
3. Follow the shared click-path in `deploy/mcp-publish/README.md`.
