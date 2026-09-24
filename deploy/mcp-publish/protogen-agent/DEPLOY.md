# DEPLOY — protogen-agent

CAD services; bundle with SmartScale as measure->CAD.

## Serve
```
cd protogen-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridis.earth/protogen/mcp` (streamable-http).

## Environment
none for the MCP CAD tools

## How a calling agent uses it
Connect any MCP client to the server and call the tools in `tools.json`
(key tools: create_cad_workspace / generate_cad_design / export_cad_design). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope — callers
never see an exception.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py protogen-agent`
2. Fill the placeholders in `server.json` (repository.url, remote URL).
3. Follow the shared click-path in `deploy/mcp-publish/README.md`.
