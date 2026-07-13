# Glama — claim + Dockerfile setup

Glama approved and listed **viridis-agent-fleet**
(https://glama.ai/mcp/servers/jdhart81/viridis-agent-fleet). To appear in
Glama **search results**, the server must pass Glama's automated safety/quality
checks, which run a Dockerfile you provide on the admin page. This directory is
that Dockerfile plus the bridge it runs.

## What this is

`fleet_bridge.py` is a stdio MCP server backed by the generated
`fleet_manifest.json`; calls forward to `mcp.viridisconservation.com`. It
re-exposes all fleet tools namespaced `<agent>__<tool>` (e.g. `escrow__open_escrow`,
`surety__slash_bond`). Glama builds the Docker image, runs it, connects over
stdio, and inspects the real tool surface — no private agent cores are exposed.

Bonus: this is also a genuine **"install the whole fleet in one line"** for
Claude Desktop / Cursor:

```json
{ "mcpServers": { "viridis-fleet": {
  "command": "docker",
  "args": ["run","-i","--rm","ghcr.io/jdhart81/viridis-fleet-bridge"] } } }
```

Release target 2026-07-13: 19 agents and an expected 131-tool aggregate (the
prior 117 tools, six GHG Ledger tools, four Compute Ledger v0.2.0 tools, and
four Provenance v0.2.0 tools). Call forwarding includes
`escrow__list_escrows`, `surety__list_bonds`,
`taxcredit-engine__calculate_tax_credit`, and
`ghg-ledger__calculate_inventory`. Regenerate `fleet_manifest.json` from the
live 19-agent fleet before the Glama build to turn this expected count into the
released aggregate.

## Steps (the two account actions are yours — Justin)

1. **Claim the server** — open
   https://glama.ai/mcp/servers/jdhart81/viridis-agent-fleet, go to admin
   settings, click **Claim** (author verification via your GitHub `jdhart81`).
2. **Provide the Dockerfile** — on
   https://glama.ai/mcp/servers/jdhart81/viridis-agent-fleet/admin/dockerfile,
   paste the contents of `deploy/glama/Dockerfile` (below). Glama notes it does
   **not** need to live in the repo, but it also now does — committed so the
   build context (`fleet_bridge.py`) is present if Glama builds from source.

## Dockerfile (paste this)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "mcp>=1.2"
COPY fleet_bridge.py /app/fleet_bridge.py
COPY fleet_manifest.json /app/fleet_manifest.json
ENV VIRIDIS_BASE=https://mcp.viridisconservation.com
CMD ["python3", "/app/fleet_bridge.py"]
```

## Known-good Glama admin build configuration

When Glama's admin uses its base-image/build-step form rather than the checked-in
Dockerfile, use these values exactly:

- Base image: `debian:trixie-slim`
- Build step: `["uv pip install --system --break-system-packages mcp"]`
- Command: `["mcp-proxy","--","python3","deploy/glama/fleet_bridge.py"]`

If the base-image pull fails with `context deadline exceeded`, retry the build;
that error occurs before the fleet bridge is evaluated.

If Glama's build context is the repo root, use build-context path
`deploy/glama/` (where `Dockerfile` + `fleet_bridge.py` live), or set the
Dockerfile `COPY` to `deploy/glama/fleet_bridge.py`.

## Notes

- Rails are free; the four priced services (smartscale, protogen,
  taxcredit-engine, ghg-ledger) offer 100 free calls/day then paid — GHG Ledger
  charges $1.00 per inventory calculation — and the bridge surfaces that in
  each tool's namespaced description.
- If an endpoint is momentarily down, the bridge skips it and still starts
  (per-endpoint timeout), so the quality check never hangs on one agent.
