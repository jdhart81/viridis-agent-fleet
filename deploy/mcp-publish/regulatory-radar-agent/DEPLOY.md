# DEPLOY — regulatory-radar-agent

CSRD/TNFD compliance-as-a-service; climate-stack door-opener.

## Serve
```
cd regulatory-radar-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridis.earth/regulatory-radar/mcp` (streamable-http).

## Environment
none (built-in regulation DB; wire a live feed before selling monitoring)

## How a calling agent uses it
Connect any MCP client to the server and call the tools in `tools.json`
(key tools: scan_regulations / assess_compliance). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope — callers
never see an exception.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py regulatory-radar-agent`
2. Fill the placeholders in `server.json` (repository.url, remote URL).
3. Follow the shared click-path in `deploy/mcp-publish/README.md`.
