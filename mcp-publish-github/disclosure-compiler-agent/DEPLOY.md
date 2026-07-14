# Publish disclosure-compiler

Remote: `https://mcp.viridisconservation.com/disclosure-compiler/mcp`

After the matching gateway build is live and healthy:

```bash
mcp-publisher validate deploy/mcp-publish-github/disclosure-compiler-agent/server.json
mcp-publisher publish deploy/mcp-publish-github/disclosure-compiler-agent/server.json
```

Official registry identity: `io.github.jdhart81/disclosure-compiler` v0.1.0.

Smithery target: public listing `hartjustin6/disclosure-compiler`, repository
`https://github.com/jdhart81/viridis-agent-fleet`, homepage
`https://mcp.viridisconservation.com`, remote
`https://mcp.viridisconservation.com/disclosure-compiler/mcp`, and pricing copy:
“10 free disclosure drafts/day, then $2.00 per draft via redeem_payment. B2B
energy, climate, and compliance seats are available when Stripe Checkout is
configured.” The Continue button requires a second click in a separate action
after the form loses focus.

Publishing mutates the official registry and requires the owner account; do
not publish before production health, version, pricing, and live tool-list
checks pass. Glama remains the one aggregate fleet server; regenerate its
manifest from the live fleet only after the 21-agent gateway is green:

```bash
python3 scripts/generate_live_glama_manifest.py --expected-count 21
```

Then sync `https://github.com/jdhart81/viridis-agent-fleet` in Glama until its
Last commit matches the pushed SHA, run a green Build, and use Build & Release.
Known-good admin configuration: base `debian:trixie-slim`, build step
`["uv pip install --system --break-system-packages mcp"]`, command
`["mcp-proxy","--","python3","deploy/glama/fleet_bridge.py"]`.

## Safe public-repository handoff

Do not reuse `_public-repo-viridis-agent-fleet`: that checkout is stale and
contains unrelated dirty files. After the live manifest is regenerated, use a
fresh temporary clone and verify it is at the current `origin/main` before
copying anything:

```bash
git clone --depth=1 https://github.com/jdhart81/viridis-agent-fleet.git /private/tmp/viridis-agent-fleet-disclosure-20260713
git -C /private/tmp/viridis-agent-fleet-disclosure-20260713 status --short --branch
git -C /private/tmp/viridis-agent-fleet-disclosure-20260713 rev-parse HEAD
```

Copy only these release artifacts into that fresh clone:

- this package's `server.json`, `tools.json`, and `DEPLOY.md` to
  `mcp-publish-github/disclosure-compiler-agent/`;
- `deploy/glama/fleet_bridge.py` and the newly live-generated
  `deploy/glama/fleet_manifest.json` to the same paths in the public repo;
- `deploy/public-repo-payload/contracts/disclosure-compiler-agent.md` to
  `contracts/disclosure-compiler-agent.md`;
- apply `deploy/public-repo-payload/disclosure-compiler-README-snippet.md` to
  the public `README.md` without replacing unrelated current content.

Review the fresh clone's diff, commit those explicit files, push `main`, and
record the resulting SHA before starting the Glama admin sync. No command in
this handoff performs those external mutations automatically.
