# Handoff to Sol — Kickoff Prompt

Copy everything in the block below into Sol as the opening message. It is self-contained; Sol should not
need anything else.

---

```
You are implementing a small, well-specified build in an existing Python codebase. Work only inside the
`ViridisOS/integration/` directory. Pure Python standard library — do NOT install anything.

WHERE
- Package root: ViridisOS/   (contains certification/, runtime/, modules/, integration/)
- Your work is confined to: ViridisOS/integration/
- Read first, in order:
    1. ViridisOS/integration/BUILD_SPEC.md   (the full spec — invariants U-1..U-6, exact interfaces)
    2. ViridisOS/integration/trust_root.py   (stub — implement)
    3. ViridisOS/integration/mark.py         (stub — implement)
    4. ViridisOS/integration/toll.py         (stub — implement)
    5. ViridisOS/integration/tests/test_integration.py   (the acceptance suite — READ, never edit)

GOAL
Unify ViridisOS conservation certificates and the agent-fleet attestations under ONE trust root, ONE
mark ("Certified by ViridisOS"), and ONE toll (the fleet bps fee schedule). Concretely: implement the
three stub modules (trust_root.py, mark.py, toll.py) to satisfy the invariants in BUILD_SPEC.md.

DEFINITION OF DONE
Run from the ViridisOS package root:
    python3 integration/tests/test_integration.py
Done == it prints "17 passed, 0 failed" and exits 0.

HARD RULES
- Additive only. Do NOT modify test_integration.py, certification/, runtime/, modules/, or any fleet code.
- Stdlib only. No pip installs, no new dependencies, no network calls, no database.
- Deterministic: same inputs -> same bytes -> same signature. No wall-clock in signatures.
- Keep the dev HmacSigner behind TrustRoot; do NOT add real key custody (that is a later task).
- Reuse existing helpers: runtime.provenance.canonical for canonical bytes; the ceil-bps formula
  -(-amount*bps//10000) for toll rounding (matches gateway/escrow_custody.py).
- bind_did MUST reproduce the fleet formula exactly:
    "did:viridis:" + sha256(f"{agent_id}|{pubkey}").hexdigest()[:16]

WHEN DONE
- Confirm the suite is green (paste the final "17 passed, 0 failed" line).
- Confirm the existing suites still pass:  bash run_all_tests.sh   (from ViridisOS/)
- Summarize in <=5 bullets what each of the three modules now does. Do not restate the spec.
- Flag any place the spec was ambiguous and what you assumed. Change nothing outside integration/.
```

---

## Notes for Justin (not part of Sol's prompt)

- Absolute path on this machine: `Viridis Core docs 2.0/ViridisOS/`. If Sol runs in its own checkout,
  make sure `certification/`, `runtime/`, and `modules/` are present alongside `integration/` — the
  imports depend on them.
- Expected effort: ~30–40 lines of real implementation across the three files. The signing seam
  (`Certifier(signer=...)`) already exists, so no changes to `certification/` are needed.
- If you'd rather Sol also wire `TrustRoot` into a live `Certifier` demo (issue a real conservation
  certificate through the shared root), add this line to the prompt's GOAL: "Then add
  `integration/demo.py` showing a Certifier issuing a certificate whose signer is the shared TrustRoot,
  and an agent attestation under the same root." I left it out to keep the first pass minimal.
