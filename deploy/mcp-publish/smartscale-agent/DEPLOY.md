# DEPLOY — smartscale-agent

Deterministic CR80 pixel-geometry scaling. Callers supply numeric card and
object pixel geometry; the public MCP does not receive images or run vision.

## Serve
```
cd smartscale-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridisconservation.com/smartscale/mcp`
(streamable-http).

## Environment
The SmartScale core requires no service-specific credentials. Billing and
state use the shared gateway configuration.

## How a calling agent uses it
Connect any MCP client to the server and call the tools in `tools.json`
(key tools: credit_card_photo_instructions / scale_objects_from_credit_card). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope — callers
never see an exception. State-changing calls may include a retry-safe
`request_id`.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py smartscale-agent`
2. Confirm version `0.9.4` is live and the tools manifest includes
   `payment_ref` and `request_id`.
3. Confirm the off-droplet backup and restore-drill gate.
4. Follow the shared click-path in `deploy/mcp-publish/README.md`.
