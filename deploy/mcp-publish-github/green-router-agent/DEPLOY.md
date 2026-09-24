# Publish green-router

Remote: `https://mcp.viridisconservation.com/green-router/mcp`

After the matching gateway build is live and healthy:

```bash
mcp-publisher validate deploy/mcp-publish-github/green-router-agent/server.json
mcp-publisher publish deploy/mcp-publish-github/green-router-agent/server.json
```

Publishing mutates the official registry and requires the owner account; do not publish before live health and version checks pass.
