# Publish security-preflight

Remote: `https://mcp.viridisconservation.com/security-preflight/mcp`

Publish only after the matching Fleet image is live, its receipt signer is
ready, the unpaid x402 route quotes correctly, and the public claim boundary is
visible:

```bash
mcp-publisher validate deploy/mcp-publish/security-preflight-agent/server.json
mcp-publisher publish deploy/mcp-publish/security-preflight-agent/server.json
```
