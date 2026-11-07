# Mounting viridis-eco-funding in the Viridis agent gateway

**Status: live since 2026-11-07** at `https://mcp.viridisconservation.com/eco-funding/mcp`
(gateway repository `jdhart81/viridis-fleet-service`: mounted in PR #68, released to
production by the overlay kit in PR #69). This file records what the mount consists of, so
a re-vendor or a rebuild reproduces it.

Gateway: `deploy/gateway/viridis_mcp_gateway.py`, `mcp==1.28.1`. `tests/test_fleet_admission.py`
checks AA1–AA4, AA7 and fleet contract C4 here; `deploy/fleet/gateway_check.py` emulates the
mount under `mcp==1.28.1` and under mcp 2.x.

## 0. Vendor the agent

The fleet's open-core layout puts every hosted agent in a `*-agent/` folder at the
repository root, so the vendored copy is `eco-funding-agent/`, with a `VENDORED_FROM.json`
recording this repository's commit. Re-vendor with
`git -C <viridis-eco-funding> archive <sha> | tar -x -C eco-funding-agent`.

The adapter, `eco-funding-agent/adapters/mcp_server.py`, defines module-level `mcp` (FastMCP)
and `agent` (`describe()`, `health()`, `async process()`). It imports only the
standard-library package in `src/viridis_eco_funding`, so it adds no pip dependencies. Inside
a fleet tree it wraps its tools with `fleet_utils.mcp_errors.flag_error_results`, so error
envelopes reach MCP clients with `isError` (fleet contract C4); standalone that is a no-op.

## 1. Mount and discovery (AA1)

In `deploy/gateway/viridis_mcp_gateway.py`:

```python
# MOUNTS
    "eco-funding":      "eco-funding-agent",

# AGENT_SEO
    "eco-funding": {
        "desc": "Ecological complexity valuation for agents: D-Score x verified connected habitat -> sealed, re-runnable receipts, plus pledge-pool release simulation. Read-only, free rail; intelligence-bound term labelled conjecture.",
        "queries": ["Value the biodiversity and habitat connectivity of a conservation site",
                    "Verify a reproducible ecological valuation receipt",
                    "Simulate milestone and outcome-linked releases for a conservation pledge pool",
                    "D-Score biodiversity index for a woodland or hedgerow project"]},
```

Do **not** add an entry to `_X402_DISCOVERY_METADATA`. That table describes x402-routed paid
tools only, and eco-funding is a free rail.

Add the module docstring line `https://<host>/eco-funding/mcp      eco-funding-agent (free rail)`
and the Eco-Funding section in `deploy/gateway/llms.txt`.

## 2. Economic decision (AA2): free rail

Do **not** add it to `PRICE_MINOR`. In `deploy/gateway/test_admission_invariants.py`, add it to `FREE_RAILS`:

```python
    "eco-funding":    "verification is the network effect: free re-runnable receipts are shared trust references",
```

This is free by doctrine, for the same reason verification is free across the fleet. It must also stay free because this agent's Invariant 5 rules out money movement. It is never gated, metered for payment, or wired to escrow.

## 3. Revenue model on record (AA3)

`eco-funding-agent/agent.yaml` already carries `revenue_model` and `thesis_connection`.

## 4. Network edges (AA4)

Success envelopes teach these edges:
- `value_site` → `notary.commit` (timestamp the receipt seal; digests only), `regulatory-radar.build_evidence_pack`, `ghg-ledger.calculate_inventory`, `eco-funding.verify_receipt`, `eco-funding.simulate_pool`
- `verify_receipt` → `notary.verify`, `eco-funding.simulate_pool`

There are deliberately no edges to escrow, settlement or payments. Pools are modelled only, and any real pool needs legal review before money moves.

## 5. Shipping surfaces (AA5)

- `deploy/gateway/Dockerfile`: `COPY eco-funding-agent/ eco-funding-agent/`, next to the other agent COPY lines.
- `deploy/gateway/deck.html`, `const ROLE = {...}`: `"eco-funding":"rails · conservation valuation"`.
- `deploy/glama/fleet_bridge.py`, ROLE, and `deploy/glama/fleet_manifest.json` (paste `deploy/fleet/tools.json` → `tools`).
- The autoseal golden fixture (`value_site` on `examples/data/woodland_site.json`) and the count-pinned release tests.
- `deploy/mcp-publish/` and `deploy/mcp-publish-github/`: `eco-funding-agent/{server.json,tools.json}`.

## 6. Distribution (AA6), after the live health check passes

1. Public repository: `https://github.com/jdhart81/viridis-eco-funding` (public).
2. Public fleet repository `jdhart81/viridis-agent-fleet`: the `eco-funding-agent/` folder, so `llms.txt` lists it.
3. Each of these waits for the maintainer's explicit approval:
   - Official registry: `mcp-publisher validate deploy/fleet/server.json && mcp-publisher publish deploy/fleet/server.json` (owner account, `io.github.jdhart81` namespace).
   - Glama: Sync → Build & Release.
   - Smithery: per-agent listing.

## 7. Quickstart (AA7)

Add `deploy/fleet/QUICKSTART_SNIPPET.md` to `docs/QUICKSTART_FIRST_CALL.md`.

## Verify

```bash
curl -s https://mcp.viridisconservation.com/healthz | jq '.agents["eco-funding"]'
python deploy/fleet/gateway_check.py   # local emulation; the live call is in QUICKSTART_SNIPPET.md
```
