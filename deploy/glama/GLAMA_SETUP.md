# Glama — claim + Dockerfile setup

Glama approved and listed **viridis-agent-fleet**
(https://glama.ai/mcp/servers/jdhart81/viridis-agent-fleet). To appear in
Glama **search results**, the server must pass Glama's automated safety/quality
checks, which run a Dockerfile you provide on the admin page. This directory is
that Dockerfile plus the bridge it runs.

## What this is

`fleet_bridge.py` is a stdio MCP server that connects to the live hosted fleet
(17 agents on `mcp.viridisconservation.com`), lists their tools, and re-exposes
all **112 tools** namespaced `<agent>__<tool>` (e.g. `escrow__open_escrow`,
`surety__slash_bond`). Glama builds the Docker image, runs it, connects over
stdio, and inspects the real tool surface — no private agent cores are exposed.

Bonus: this is also a genuine **"install the whole fleet in one line"** for
Claude Desktop / Cursor:

```json
{ "mcpServers": { "viridis-fleet": {
  "command": "docker",
  "args": ["run","-i","--rm","ghcr.io/jdhart81/viridis-fleet-bridge"] } } }
```

Verified 2026-07-12: 17/17 agents reachable, 112 tools aggregated, call
forwarding confirmed (`escrow__list_escrows` → live escrows,
`surety__list_bonds` → live bonds).

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
ENV VIRIDIS_BASE=https://mcp.viridisconservation.com
CMD ["python3", "/app/fleet_bridge.py"]
```

If Glama's build context is the repo root, use build-context path
`deploy/glama/` (where `Dockerfile` + `fleet_bridge.py` live), or set the
Dockerfile `COPY` to `deploy/glama/fleet_bridge.py`.

## Notes

- Rails are free; the two services (smartscale, protogen) offer 100 free
  calls/day then paid — the bridge surfaces that in each tool's namespaced
  description.
- If an endpoint is momentarily down, the bridge skips it and still starts
  (per-endpoint timeout), so the quality check never hangs on one agent.
