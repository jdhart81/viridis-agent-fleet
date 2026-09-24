# MCP Publish Packages — Viridis Agent Fleet
> Generated 2026-07-09 by `scripts/generate_mcp_manifests.py` (schemas are
> introspected from the adapters — re-run after any adapter change).
> Smoke: `python3 deploy/mcp-publish/smoke_all.py` (10/10 clean at generation).

Each package contains:
- `server.json` — MCP registry manifest (remote/streamable-http **template**)
- `tools.json` — one JSON-Schema tool per core action
- `DEPLOY.md` — agent-specific env, endpoints, and usage

## The publish click-path (identical for every agent — Energy AI proved it)

**Nothing below happens automatically. Every step is yours.**

1. **Host the server.** Each adapter is a stdio FastMCP server
   (`python adapters/mcp_server.py --serve`). For a hosted remote, wrap it in
   streamable-http (FastMCP supports `transport="streamable-http"`) and deploy
   behind `https://mcp.viridis.earth/<path>/mcp` — same Worker/host pattern as
   Energy AI's registry entry. `pip install "mcp[cli]"` on the host.
2. **Fill the template.** In `server.json`: set `repository.url` to the real
   repo and confirm the `remotes[0].url` you actually deployed.
3. **Verify the namespace** (once per domain): `earth.viridis/*` requires DNS
   or HTTP verification of viridis.earth — `mcp-publisher login dns` (or
   `http`). Already done once for Energy AI; reuse that setup.
4. **Validate + publish:**
   ```
   mcp-publisher validate server.json
   mcp-publisher publish server.json
   ```
5. **Confirm the listing** at registry.modelcontextprotocol.io, then run one
   end-to-end tool call against the hosted URL from any MCP client.

Publish order (leverage): identity → trust → escrow → metering → arbitration
→ compute-ledger → smartscale → protogen → regulatory-radar → narrative.
The first three are the rails; the settlement extensions compose with them
(`scripts/a2a_settlement_stack_demo.py` is the proof); SmartScale is the
first sellable service on top.

## Hard rule honored
These packages were prepared **to the click** — no account, registry, DNS,
or payment surface was touched in their creation.
