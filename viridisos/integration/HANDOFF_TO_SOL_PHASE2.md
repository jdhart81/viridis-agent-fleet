# Handoff to Sol — Phase 2 Kickoff Prompt

Attach the **Viridis Core docs 2.0** folder (NOT "Agents to deploy" — Phase 2 is ViridisOS-side only).
Copy the block below into Sol.

---

```
Phase 2 of a well-specified build. Work only inside ViridisOS/integration/. Pure Python stdlib —
do NOT install anything. Phase 1 is already complete and green; do not change it.

WHERE (package root: ViridisOS/, contains certification/, runtime/, modules/, integration/)
Read first, in order:
  1. ViridisOS/integration/PHASE2_SPEC.md            (the spec — invariants P2-1..P2-6)
  2. ViridisOS/integration/certifier_bridge.py       (4 stubs — implement these)
  3. ViridisOS/integration/tests/test_phase2_bridge.py   (acceptance suite — READ, never edit)
  4. ViridisOS/certification/certifier.py, claim.py, standard.py   (context — do not edit)

GOAL
Implement the four functions in integration/certifier_bridge.py:
  unified_certifier(root, resolver=None)  -> Certifier(signer=root)
  certificate_to_envelope(cert)           -> Envelope (profile "conservation-claim", no re-sign)
  agent_attestation(root, event)          -> Envelope (profile "agent-attestation")
  conservation_validator(payload)         -> bool (all required claim.* STANDARD fields present)
Follow PHASE2_SPEC.md exactly; the docstrings in the stub file state each contract.

DEFINITION OF DONE (run from the ViridisOS package root)
  python3 integration/tests/test_phase2_bridge.py     -> "6 passed, 0 failed"
  python3 integration/tests/test_integration.py       -> still "27 passed, 0 failed"
  bash run_all_tests.sh                                -> still "TOTAL: 33 passed, 0 failed"

HARD RULES
- Additive only. Edit ONLY integration/certifier_bridge.py. Touch no test, no certification/, runtime/,
  modules/, or fleet code.
- Stdlib only. No installs, no network, no DB.
- Do NOT re-sign in certificate_to_envelope — reuse cert.signature (the Certifier already signed the
  canonical claim under the shared root; re-signing will break verify_mark).
- root_id comes from TrustRoot.root_id; key_id from the cert.

WHEN DONE
- Paste the three result lines above.
- In <=4 bullets, say what each function does. Flag any ambiguity and what you assumed.
```

---

## Notes for Justin (not part of the prompt)
- No Agents folder needed — Phase 2 conformance hardcodes the fleet's published `esc-fee-v1` margins, so
  Sol never touches the fleet repo.
- The toll-conformance test already passes against the Phase 1 `toll.py`; Sol only implements the 4
  bridge functions (~20 lines).
- When Sol reports back, say "done" and I'll run all three suites + review against P2-1..P2-6 before we
  move to Phase 3 (MCP tools + deploy).
