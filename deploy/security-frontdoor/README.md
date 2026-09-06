# Security Preflight front door

These public pages belong at `https://mcp.viridis-security.com/security-preflight` on the existing Viridis Security deployment.

- MCP: `/security-preflight/mcp`
- Paid HTTP: `/x402/security-preflight/security_preflight`
- Free change check: `/security-preflight/watch`
- Redacted assessment receipt: `/security-preflight/receipts/{receipt_id}`
- Machine service contract: `/security-preflight/service.json`
- OpenAPI: `/security-preflight/openapi.json`

The gateway routes the bounded Preflight API paths to the shared fleet core. It sets `X-Viridis-Security-Origin: https://mcp.viridis-security.com` and preserves payment signatures. The backend accepts only that fixed owned alias; it never derives a payable URL from arbitrary Host or Forwarded headers. Legacy requests retain their original resource binding. Other fleet services keep their existing URLs.

The existing Injection Detector `/mcp`, signup, billing, Canon, Maxwell, and main Security app routes remain separate. Serve `/security-preflight` explicitly from `security-preflight.html` so its sibling assets directory cannot create a redirect loop.

Releases require an exact running-image check, original configuration and file backups, a localhost rehearsal, both MCP tool listings, valid unpaid quote binding, free watch checks, production readback, restart verification, and rollback. A static-only rehearsal is not a production gate. No customer payment is part of deployment verification.

Before reloading a file bind mount, compare the file hash inside the container with the intended host file. A prior atomic file replacement can leave the running container on an older inode. If they differ, restart to rebind, verify the hashes match, then reload and repeat the public MCP checks.
