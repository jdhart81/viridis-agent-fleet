# Publish security-preflight

Remote: `https://mcp.viridisconservation.com/security-preflight/mcp`

After the matching gateway build is live and healthy:

```bash
mcp-publisher validate deploy/mcp-publish-github/security-preflight-agent/server.json
mcp-publisher publish deploy/mcp-publish-github/security-preflight-agent/server.json
```

Publishing mutates the official registry and requires the owner account; do not
publish before live signer, health, version, x402 quote, and claim-boundary
checks pass.
