# PHASE 3 SPEC — MCP Tool Surface + Deploy

**Date:** 2026-07-19. **Depends on:** Phases 1, 2, 3a all green.

## 3a — Pre-deploy hardening  ✅ DONE (by Claude, verified)
`verify_mark` now enforces `env.key_id == root.key_id` (key-rotation guard); `compute_toll` rejects
non-integer / negative `amount_minor`. Locked by `tests/test_phase3_hardening.py` (6/6). All prior suites
remain green.

## 3b — The unified MCP tool surface  (Sol builds this)

**Job:** implement `call_tool()` in `integration/mcp_tools.py` so `tests/test_phase3_mcp.py` goes green.
The `MANIFEST` and tool schemas are already written; you implement the dispatcher only.

**Definition of done (from the ViridisOS package root):**
```
python3 integration/tests/test_phase3_mcp.py         -> "N passed, 0 failed"
python3 integration/tests/test_integration.py        -> still 27 passed
python3 integration/tests/test_phase2_bridge.py      -> still 14 passed
python3 integration/tests/test_phase3_hardening.py   -> still 6 passed
bash run_all_tests.sh                                 -> still TOTAL: 33 passed
```

**Contract for `call_tool(name, args, root=None)`** — pure, never raises, returns a dict:
- `viridis_bind_did` → `{"did": root.bind_did(args["agent_id"], args["pubkey"])}`
- `viridis_compute_toll` → `compute_toll(args["amount_minor"], args["payee_tier"])`; on `ValueError`
  return `{"error": "<message>"}`
- `viridis_agent_attestation` → `{"envelope": <asdict of agent_attestation(root, args["event"])>}`
- `viridis_verify_mark` → `{"valid": <bool>}`. Rebuild the Envelope from `args["envelope"]` via
  `_envelope_from_dict`. Choose the validator by `args.get("profile")`: `"conservation-claim"` →
  `conservation_validator`; anything else → an accept-all structural validator `lambda p: isinstance(p, dict)`.
- unknown `name` (not in `_TOOL_NAMES`) → `{"error": "unknown tool: <name>"}`
- any missing/bad arg → `{"error": "<message>"}` (catch and return, never raise)

Use `root or _DEFAULT_ROOT` for tools that need a root. Additive only; edit ONLY `mcp_tools.py`.

**HARD RULES:** stdlib only, no installs, no network. Do not edit tests, `certification/`, `runtime/`,
`modules/`, `api/`, or fleet code.

## 3c — Deploy  (NOT a Sol task — needs Justin's go + infra/secrets)

The MCP surface runs on the **dev stubs** today. Real deployment requires the production swaps from
`HANDOFF_NOTES.md`, each behind a stable interface (no core rewrite):
1. **Signer:** dev `HmacSigner` → L1 VERIFY **K3 signer** (VW3 path). Inject into `TrustRoot`.
2. **Canon resolver:** fixture index → live `viridis-canon` + Zenodo ledger (retracted theorems auto-BLOCK).
3. **Certificate registry:** in-memory/JSON → DATA plane (Supabase `eldfngwmgyebevoxqxwm`).
4. **Transport:** wrap `mcp_tools.call_tool` + `api/service.dispatch` in an MCP server; publish alongside
   the fleet's `deploy/mcp-publish-github/` packages; deploy to the droplet (persistent deploy key).

**Open blockers/decisions for Justin (surface before 3c):**
- **SRPT still blocks the Mutualist module** (`10.5281/zenodo.SRPT-PENDING`) — correct A-1 behavior; wire
  the real DOI at SRPT publish. Restoration/Afforestation/Harmonization are LIVE and deployable now.
- **Deploy path:** (A) ship a *staging/preview* MCP on dev stubs to validate the surface end-to-end, or
  (B) wait and deploy the real trust authority once the K3 signer + live resolver + Supabase are wired.
- Key custody for the production root (who holds the K3 key).
