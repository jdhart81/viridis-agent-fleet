# DEPLOY — smartscale-agent

Fastest fleet-only first dollar: CR80 credit-card-calibrated measurement. Pure-math MCP path needs NO vision deps.

## Serve
```
cd smartscale-agent
pip install "mcp[cli]"                      # only dependency for MCP serving
python adapters/mcp_server.py               # smoke: describe + health
python adapters/mcp_server.py --serve       # stdio MCP server
```
Hosted remote target: `https://mcp.viridis.earth/smartscale/mcp` (streamable-http).

## Environment
Optional for full SaaS: SUPABASE_URL, SUPABASE_ANON_KEY, STRIPE_API_KEY, AWS_S3_BUCKET (MCP measurement tools run without any of them)

## How a calling agent uses it
Connect any MCP client to the server and call the tools in `tools.json`
(key tools: credit_card_photo_instructions / scale_objects_from_credit_card). Every tool returns the fleet-standard JSON envelope:
`{"status": "ok", "data": ...}` or a structured error envelope — callers
never see an exception.

## Before publish
1. `python3 deploy/mcp-publish/smoke_all.py smartscale-agent`
2. Fill the placeholders in `server.json` (repository.url, remote URL).
3. Follow the shared click-path in `deploy/mcp-publish/README.md`.
