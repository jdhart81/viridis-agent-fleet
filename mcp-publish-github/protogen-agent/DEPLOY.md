# Publish protogen

Remote: `https://mcp.viridisconservation.com/protogen/mcp`

After the matching gateway build is live and healthy:

```bash
mcp-publisher validate deploy/mcp-publish-github/protogen-agent/server.json
mcp-publisher publish deploy/mcp-publish-github/protogen-agent/server.json
```

Publishing mutates the official registry and requires the owner account; do not publish before live health and version checks pass.
