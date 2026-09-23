# ViridisOS MCP — Staging Deploy Runbook

**Posture:** staging preview on dev stubs (Justin, 2026-07-19). The server runs the unified tool surface
+ the live modules against the real canon. The mark is **not yet externally unforgeable** (dev HMAC signer)
— this is a preview to validate the surface, clearly labeled non-authoritative until the K3 swap.

## What ships
- **Server:** `integration/mcp_server.py` — MCP (JSON-RPC 2.0) over stdio. Zero dependencies (stdlib).
- **Tools exposed (7):**
  - `viridis_bind_did`, `viridis_compute_toll`, `viridis_agent_attestation`, `viridis_verify_mark`
  - `viridis_list_modules`, `viridis_certify`, `viridis_certify_envelope`
- **Modules (live canon):** restoration · afforestation · harmonization = **READY**; mutualist = **BLOCKED**
  (SRPT-PENDING — correct A-1 behavior, ships blocked).

## Run locally
```bash
cd ViridisOS
python3 integration/mcp_server.py      # speaks JSON-RPC on stdin/stdout
# smoke:
python3 integration/tests/test_phase3c_server.py     # -> 13 passed, 0 failed
```

Register with an MCP client (stdio transport), e.g.:
```json
{
  "mcpServers": {
    "viridisos": { "command": "python3", "args": ["integration/mcp_server.py"], "cwd": "<abs path>/ViridisOS" }
  }
}
```

## Deploy to the droplet (Justin runs these — live infra)
Uses the persistent deploy key (`secrets/viridis_conservation_deploy`; droplet `deploy@192.241.131.123`).
```bash
# from a machine with the key
scp -r ViridisOS deploy@192.241.131.123:/opt/viridisos-mcp        # or: git pull on the droplet
ssh -i <key> deploy@192.241.131.123 'cd /opt/viridisos-mcp && python3 integration/tests/test_phase3c_server.py'
# wrap in the existing MCP-publish pattern (deploy/mcp-publish-github/<agent>/) and register the
# "viridisos" server alongside the fleet's 20 agents in the gateway directory.
```
No Stripe / money rails are touched by this server. Do not wire live payment execution in staging.

## Graduating staging -> production authority (the pre-deploy gate)
Swap three stubs behind their stable interfaces (no core rewrite), then re-run the full ladder:
1. **Signer:** dev `HmacSigner` -> L1 VERIFY **K3 signer** (VW3). `ROOT = TrustRoot(signer=<k3>)` in
   `mcp_server.py`. **This is the gate that makes the mark real** — until then, treat every certificate as
   preview-only.
2. **Canon resolver:** already live (reads `canon_fingerprint_index.json`). For production, point at the
   `viridis-canon` git + Zenodo ledger so retractions auto-BLOCK. (Interface unchanged.)
3. **Certificate registry:** in-memory -> DATA plane (Supabase `eldfngwmgyebevoxqxwm`) for durable
   issuance + revocation.
4. **Root key custody:** decide who holds the K3 root key before it signs anything public.

## Full ladder (all green as of 2026-07-19)
| Suite | Checks |
|---|---|
| Phase 1 — root/mark/toll | 27 |
| Phase 2 — Certifier + mark envelopes | 14 |
| Phase 3a — hardening | 6 |
| Phase 3b — MCP tool surface | 10 |
| Phase 3c — MCP server (staging) | 13 |
| Existing ViridisOS | 33 |
| **Total** | **103** |
