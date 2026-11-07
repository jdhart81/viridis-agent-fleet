# Codex prompt: mount viridis-eco-funding on the Viridis gateway

> **Superseded (2026-11-07).** The mount is live: fleet-service PR #68 and the production
> overlay release in PR #69. The vendored folder is `eco-funding-agent/`, and there is no
> x402 catalog metadata entry. `MOUNT.md` is the current record; this prompt is kept as history.

Paste into a Codex session that runs in `jdhart81/viridis-fleet-service`, on Justin's Mac with the Keychain GitHub login (see that repo's AGENTS.md "GitHub access baseline").

---

Goal: mount `jdhart81/viridis-eco-funding` (latest `main`) at `/eco-funding/mcp` on the gateway as a **declared free rail**, satisfying Agent Admission Invariants AA1–AA7. Work on branch `mount-eco-funding`, open a PR, and do not merge or deploy without Justin's approval through the normal fleet release gate (`deploy/droplet/FLEET_RELEASE_GATE.md`).

1. Run `gh auth status`, and check it again with Keychain access if the first result is inconclusive.
2. Vendor the agent: `git clone --depth 1 https://github.com/jdhart81/viridis-eco-funding /tmp/vef && rsync -a --exclude .git /tmp/vef/ viridis-eco-funding/`.
3. Apply every edit in `viridis-eco-funding/deploy/fleet/MOUNT.md` §1–§5:
   - MOUNTS, AGENT_SEO, catalog metadata and the docstring line in `deploy/gateway/viridis_mcp_gateway.py`;
   - the `FREE_RAILS` entry in `deploy/gateway/test_admission_invariants.py`;
   - the Dockerfile `COPY viridis-eco-funding/ viridis-eco-funding/`;
   - the deck.html and Glama `fleet_bridge.py` ROLE maps;
   - a regenerated `deploy/glama/fleet_manifest.json`;
   - the count-pinned release tests, re-baselined.

   Do **not** add `eco-funding` to `PRICE_MINOR`, any x402, escrow or settlement wiring, or any payment surface. This agent is a free rail and must never move money.
4. Add `viridis-eco-funding/deploy/fleet/QUICKSTART_SNIPPET.md` to `docs/QUICKSTART_FIRST_CALL.md` (AA7).
5. Verify:
   - `pytest deploy/gateway/test_admission_invariants.py -q` and the full gateway suite;
   - `cd viridis-eco-funding && python -m pytest -q`, which needs Python 3.11 or later and runs standard-library only;
   - `python viridis-eco-funding/deploy/fleet/gateway_check.py` using the gateway's `mcp==1.28.1` environment.
6. Commit, push the branch and open the PR. In the PR body, list the AA1–AA7 evidence and state that the agent is read-only, a free rail, and moves no money.
7. After Justin approves and the release gate deploys it, smoke-test the live endpoint:
   - `curl -s https://mcp.viridisconservation.com/health | jq '.agents["eco-funding"]'`, which must report `status: ok`;
   - the quickstart curl, which must return `status: ok`, `next_steps`, and "conjecture" in the explanation.

   Only then queue AA6: `mcp-publisher validate|publish viridis-eco-funding/deploy/fleet/server.json`, Glama Sync, and the Smithery listing, all with the owner's accounts.
