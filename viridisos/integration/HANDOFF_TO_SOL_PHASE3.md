# Handoff to Sol — Phase 3b Kickoff Prompt

Attach **Viridis Core docs 2.0**. Copy the block below into Sol.

---

```
Phase 3b of a well-specified build. Work only inside ViridisOS/integration/. Pure Python stdlib —
do NOT install anything. Phases 1, 2, 3a are complete and green; do not change them.

WHERE (package root: ViridisOS/, contains certification/, runtime/, modules/, integration/)
Read first, in order:
  1. ViridisOS/integration/PHASE3_SPEC.md              (section 3b — the contract)
  2. ViridisOS/integration/mcp_tools.py                (MANIFEST written; implement call_tool only)
  3. ViridisOS/integration/tests/test_phase3_mcp.py    (acceptance suite — READ, never edit)

GOAL
Implement ONLY the call_tool(name, args, root=None) function in integration/mcp_tools.py per the
contract in PHASE3_SPEC.md §3b. It is a pure dispatcher over the already-built primitives
(bind_did, compute_toll, agent_attestation, verify_mark). It must NEVER raise — return
{"error": "..."} on unknown tool or bad args. Use `root or _DEFAULT_ROOT`.

DEFINITION OF DONE (run from the ViridisOS package root)
  python3 integration/tests/test_phase3_mcp.py        -> "N passed, 0 failed"
  python3 integration/tests/test_integration.py       -> still 27 passed
  python3 integration/tests/test_phase2_bridge.py     -> still 14 passed
  python3 integration/tests/test_phase3_hardening.py  -> still 6 passed
  bash run_all_tests.sh                                -> still TOTAL: 33 passed

HARD RULES
- Additive only. Edit ONLY integration/mcp_tools.py. Touch no test, no certification/, runtime/,
  modules/, api/, or fleet code.
- Stdlib only. No installs, no network, no DB.
- call_tool must be pure and total (no exceptions escape). Rebuild envelopes via _envelope_from_dict.

WHEN DONE
- Paste the five result lines above.
- In <=4 bullets, describe the dispatch. Flag any ambiguity and what you assumed.
```

---

## Notes for Justin (not part of the prompt)
- This is the last *build* step. After it's green, 3c is **deploy**, which is not a Sol task — it needs
  the production swaps (K3 signer, live canon resolver, Supabase registry) and your go. I'll put the
  deploy decisions in front of you then (staging-on-stubs preview vs. wait-for-real-authority; root key
  custody; SRPT still blocks Mutualist).
- Expected effort: ~25 lines, one function.
