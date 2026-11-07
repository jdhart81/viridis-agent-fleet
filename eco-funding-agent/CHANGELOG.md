# Changelog

## Unreleased

- Live on the Viridis fleet since 2026-11-07 at `https://mcp.viridisconservation.com/eco-funding/mcp` (free rail).
- Fleet adapter: inside a fleet tree, tools are wrapped with `fleet_utils.mcp_errors.flag_error_results`, so error envelopes reach MCP clients with `isError` (fleet contract C4). Standalone this is a no-op. No change to any output or to `vef-method/0.1.0`.
- `deploy/fleet/MOUNT.md` now records the shipped layout (`eco-funding-agent/`, no x402 catalog entry).

## 0.1.0 (2026-11-07)

First working version (private repository).

- Valuation core `vef-method/0.1.0`: D-Score (MEE manuscript), power-law rarefaction for T, GSIP soil index (v0.1 convention), ECA over verified habitat with HDFM links, complexity score K = D* x ECA, and an intelligence-bound complexity-capacity term (conjecture) with compute parity.
- Sealed reproducible receipts (`vef-receipt/0.1`) and offline verification; read-only VergeCommon public-record binding.
- Pool schema `vef-pool/0.1` and an integer-exact simulator for milestone and outcome-linked releases.
- MCP server with five read-only tools over stdio and Streamable HTTP; `llms.txt` and `AGENTS.md`.
- Tests for all seven invariants, D-Score golden reproduction of Run 7, docs vocabulary checks and a method-version pin.
- Hardening after an independent adversarial review:
  - Determinism: every entry point pins the decimal context, and canonical formatting no longer depends on the caller's context. Magnitudes are kept inside the double range so receipts survive plain JSON. Strings are NFC-normalized.
  - Receipts: the receipt shape is exact; there is a top-level explanation; the seal kind is checked.
  - Pools: rules reward improvement only. Receipt-backed rules need `site_id` and `calendar`, and each receipt is single-use and bound to the period of its `observed_at`.
  - Labels: the explain label is derived from content, not from a caller-supplied flag.
  - Invariant 5 and 6 scanners: an AST scan of all Python, wider patterns, and mutation self-tests. A suite-wide socket guard blocks outbound connections.
- Viridis fleet admission (AA1–AA7):
  - A gateway adapter (`adapters/mcp_server.py`, compatible with mcp 1.28.1 and 2.x) and a fleet core with `describe`, `health`, `process` and `next_steps` edges.
  - `agent.yaml` declares the agent a free rail and records its revenue model and thesis connection.
  - Registry `server.json` and `tools.json`, a mount kit and a quickstart snippet.
  - A gateway emulation check over HTTP, and `tests/test_fleet_admission.py`.
