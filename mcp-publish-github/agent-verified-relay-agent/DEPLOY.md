# Publish agent-verified-relay (Viridis Verified)

Remote: `https://mcp.viridisconservation.com/verified/mcp`

After the matching gateway build is live and healthy (healthz shows 22 agents,
verified v0.1.0):

```bash
mcp-publisher validate deploy/mcp-publish-github/agent-verified-relay-agent/server.json
mcp-publisher publish deploy/mcp-publish-github/agent-verified-relay-agent/server.json
```

Also publish per the submission pipeline: Smithery (`hartjustin6/agent-verified-relay`)
and the Glama aggregate rebuild (regen manifest → Sync → Build & Release).
PulseMCP and mcp.so pick it up automatically from the official registry.

Worked first call (the listing example — keep it in all registry copy):

```bash
curl -s https://mcp.viridisconservation.com/verified/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"register_service",
       "arguments":{"url":"https://YOUR-MCP-SERVER.example.com/mcp","provider":"you"}}}'
```

Publishing mutates the official registry and requires the owner account; do not
publish before live health and version checks pass.
