# Publish agent-compute-ledger

Remote: `https://mcp.viridisconservation.com/compute-ledger/mcp`

After the matching gateway build is live and healthy:

```bash
mcp-publisher validate deploy/mcp-publish-github/agent-compute-ledger-agent/server.json
mcp-publisher publish deploy/mcp-publish-github/agent-compute-ledger-agent/server.json
```

Publishing mutates the official registry and requires the owner account; do not publish before live health and version checks pass.
