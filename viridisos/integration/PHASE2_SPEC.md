# PHASE 2 SPEC — ViridisOS-side Unification + Fleet Toll Conformance

**Handoff target:** OpenAI Sol. **Date:** 2026-07-19. **Depends on:** Phase 1 green (root/mark/toll).
**Scope decision (Justin, 2026-07-19):** unify on the ViridisOS side only; prove the fleet's live toll
already matches, read-only. **No fleet code is edited in Phase 2.**

**Your job, Sol:** implement the four stubs in `integration/certifier_bridge.py` so both acceptance suites
stay green:
```
python3 integration/tests/test_integration.py      # Phase 1 — must remain green
python3 integration/tests/test_phase2_bridge.py     # Phase 2 — make this green
bash run_all_tests.sh                                # existing 33 — must remain green
```
Additive only. Stdlib only. Do NOT edit any test, `certification/`, `runtime/`, `modules/`, or fleet code.

## Invariants (extend Phase 1's U-1..U-6)

- **P2-1 One root, behavior intact.** `unified_certifier(root)` returns a `Certifier(signer=root)`. Because
  `TrustRoot` wraps the same dev `HmacSigner` with the same `key_id`, every existing certification test
  still passes (U-5). Conservation certificates are now signed by the shared root.
- **P2-2 One format.** `certificate_to_envelope(cert)` maps a conservation `Certificate` into the Phase 1
  `Envelope` (profile `"conservation-claim"`) WITHOUT re-signing: `payload = asdict(cert.claim)`,
  `signature = cert.signature`, `key_id = cert.key_id`, `root_id = TrustRoot.root_id`, `mark = MARK`. This
  verifies under `verify_mark` because the Certifier signed `canonical(asdict(claim))` — identical bytes to
  `mark.canonical_bytes(asdict(claim))`.
- **P2-3 One root across profiles.** `agent_attestation(root, event)` issues an `"agent-attestation"`
  envelope under the same root; its `root_id` equals the conservation envelope's.
- **P2-4 Mark guards tamper.** Mutating any certified field invalidates `verify_mark` (inherited from U-3).
- **P2-5 Standard validator.** `conservation_validator(payload)` is True iff every required `claim.*` field
  from `STANDARD["required_certificate_fields"]` is present. It is the `validator` passed to `verify_mark`
  for conservation envelopes. (Deep recompute stays in `Certifier.verify`; the mark attests "was certified
  under the standard," a lighter check than full recompute — by design.)
- **P2-6 Toll conformance (read-only).** `integration.toll.compute_toll` protocol-margin bps/minor equals
  the fleet's published `esc-fee-v1` margin schedule (`new 200 / connect_onboarded 150 / connect_verified
  100`) for all tiers and sample amounts. The test hardcodes those values from the schedule — no fleet
  import, no fleet edit.

## What is deliberately NOT unified in Phase 2 (deviation, noted for Justin)

The fleet's card-rail cost has a `card_rail_fixed_minor: 30` term (Stripe's +30¢) on top of `290 bps`.
`integration.toll` models only the bps term. This is intentional: the +30 is **pass-through card
processing cost, not Viridis's take**, and it re-prices per rail (x402/USDC/ACH will change it — see the
schedule's `future` note). "One toll" unifies the **protocol margin** (the Viridis take); the rail-cost
term stays rail-specific and fleet-side. Conformance therefore asserts protocol-margin equality only.
If Justin wants total-fee parity too, add `CARD_RAIL_FIXED_MINOR = 30` to `toll.py` and fold it into
`card_rail_cost_minor` — flagged, not assumed.

## Next (Phase 3, after this is green)
Expose the unified surface as MCP tools (ViridisOS API on :8085 + fleet MCP-publish packages) and deploy.
Key-rotation hardening (`verify_mark` key_id check) and `compute_toll` input guards land in a pre-deploy
hardening pass.
