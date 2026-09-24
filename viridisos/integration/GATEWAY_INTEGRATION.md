# ViridisOS → Fleet MCP Gateway Integration

**Point:** ViridisOS is not a separate server. It mounts into the existing fleet gateway
(`Agents to deploy/_public-repo-viridis-agent-fleet/gateway/viridis_mcp_gateway.py`) as one more agent,
served at `/viridisos/mcp` next to `/identity/mcp`, `/escrow/mcp`, etc.

## What's ready
`ViridisOS/adapters/mcp_server.py` — the fleet-convention MCP adapter (FastMCP + the same stdlib shim the
fleet agents use). It exposes 7 tools, each delegating to the tested `integration.mcp_server.dispatch_tool`
(one shared TrustRoot + live-canon module registry). Smoke-verified with no `mcp` package installed:
```
python3 adapters/mcp_server.py            # lists 7 tools + live module states
python3 adapters/mcp_server.py --serve    # stdio MCP server (needs `mcp`)
```
Tools: `viridis_list_modules`, `viridis_certify`, `viridis_certify_envelope`, `viridis_verify_mark`,
`viridis_bind_did`, `viridis_agent_attestation`, `viridis_compute_toll`.

## Wire it in (one line in the gateway)
The gateway maps `mount -> agent dir` in its `MOUNTS` dict. Add:
```python
MOUNTS = {
    "identity":  "agent-identity-registry-agent",
    ...
    "viridisos": "viridisos",        # <-- ViridisOS package co-located at fleet ROOT/viridisos/
}
```
The gateway loads `<dir>/adapters/mcp_server.py` and mounts its `mcp` object at `/viridisos/mcp`, and it
appears in `GET /` (directory) and the ARD catalog automatically.

## The one deploy decision (co-locate vs federate)
ViridisOS lives in a different top-level folder than the fleet, and its adapter imports the whole ViridisOS
package (`certification/`, `runtime/`, `modules/`, `viridis_platform`, `integration/`). So the gateway can
serve it two ways:

1. **Co-locate + mount (recommended — matches "use the server we have").** Ship the ViridisOS package into
   the fleet deploy as `ROOT/viridisos/` (git submodule or copy at build), add the one `MOUNTS` line above,
   and add a `deploy/mcp-publish-github/viridisos/` manifest mirroring the other agents. ViridisOS is then
   served by the existing gateway process — one server, one `/healthz`, one directory, one deploy.
2. **Federated member (like EnergyAI).** ViridisOS runs its own endpoint; the fleet just lists it under
   `federated_members` + the ARD catalog. Use this only if you want ViridisOS on separate infra.

Recommendation: **co-locate + mount** — it's exactly the "we already have an MCP server" path and keeps the
7 ViridisOS tools discoverable alongside the 20 fleet agents in one gateway.

## Not done here (needs your hand)
- I have **not** edited `viridis_mcp_gateway.py` — it's live, 635-test fleet code. The one-line `MOUNTS`
  change + co-location is a deploy action for you (or a scoped Sol task with the fleet folder attached).
- Production authority still requires the K3 signer swap (see `DEPLOY_STAGING.md`); until then the mark is
  preview-only whether served standalone or via the gateway.
