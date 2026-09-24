# BUILD SPEC — Root/Mark/Toll Unification (ViridisOS × Agent Fleet)

**Handoff target:** OpenAI Sol (external coding agent).
**Author:** Claude (Viridis). **Date:** 2026-07-19.
**Goal in one line:** make conservation certificates (ViridisOS L3) and agent attestations (fleet
identity/provenance) resolve to **one trust root**, carry **one mark**, and settle under **one toll** —
without rewriting either system.

**Your job, Sol:** the bones are laid in `integration/` (stub modules + a failing acceptance suite).
Implement the three modules so the suite prints `N passed, 0 failed`. Run it from the ViridisOS package
root: `python3 integration/tests/test_integration.py` (pure stdlib, no pytest, matches house style). Do
**not** modify the acceptance tests, the existing `certification/`, `runtime/`, or the fleet agents.
Additive only. Pure Python stdlib — no installs.

---

## Context (read once, then work from the interfaces below)

- ViridisOS L3 already exists: `certification/certifier.py` (`Certifier.issue/verify`),
  `certification/attestation.py` (`Signer` Protocol + dev `HmacSigner`), `certification/claim.py`
  (`Claim`, `Certificate`), `certification/standard.py` (`STANDARD` dict).
- The `Certifier` already accepts an **injectable `signer`** — that is the seam for the shared root.
- Fleet identity issues DIDs `did:viridis:<first16 hex of sha256(agent_id|pubkey)>`
  (`agent-identity-registry-agent/src/core.py`, invariant R1). Provenance issues content-addressed genesis
  certificates (`agent-provenance-agent/src/core.py`, V1). Both already live in the `viridis` namespace.
- The fleet toll is a **bps schedule** (`gateway/escrow_custody.py`): `card_rail_cost_bps = 290`
  (pass-through), `margin_bps` tiers `{new:200, connect_onboarded:150, connect_verified:100}` (the Viridis
  take), floor 50 bps over rail cost. EC9's flat fee was retired 2026-07-19 (EC10).

## Invariants (spec-invariance contract — implement to these exactly)

- **U-1 One root.** A single `TrustRoot` signs both profiles. Any certificate/attestation exposes
  `root_id` and `key_id`; both profiles verify under the same root instance. No second signing authority.
- **U-2 Two profiles, one format.** `profile ∈ {"conservation-claim", "agent-attestation"}`. Both share the
  envelope `{ payload, profile, root_id, key_id, signature, mark }`. The payload differs per profile; the
  envelope and its verification do not.
- **U-3 One mark.** `mark == "Certified by ViridisOS"` is valid **iff** (a) the envelope's standard-validity
  check passes for its profile AND (b) the signature verifies under the shared root. A self-signed or
  standard-invalid envelope MUST fail `verify_mark`. The mark is the only enforceable claim — guard it.
- **U-4 One toll.** `compute_toll(amount_minor, payee_tier)` returns the Viridis protocol take in minor
  units using the fleet bps schedule, applied **exactly once** per settled value. Pass-through card cost is
  reported separately, never folded into the protocol margin. Both the ViridisOS settlement path and the
  fleet path MUST get identical output for identical inputs (single source of truth).
- **U-5 Additive & backward-compatible.** Existing `Certifier.issue/verify` behavior is unchanged when the
  shared root is injected as its `signer`. All current suites (`tests/`, fleet suites) still pass.
- **U-6 Deterministic.** No wall-clock in signatures beyond the caller-supplied timestamp; same inputs →
  same bytes → same signature (mirrors A-2 recompute-verifiability).

## Modules to implement (bones are stubbed in `integration/`)

### `integration/trust_root.py`
```
class TrustRoot:
    root_id: str = "viridis-root-v1"
    def __init__(self, signer: Signer | None = None)   # defaults to HmacSigner (dev); prod swaps to K3
    @property
    def key_id(self) -> str
    def sign(self, payload: bytes) -> str
    def verify(self, payload: bytes, signature: str) -> bool
    def bind_did(self, agent_id: str, pubkey: str) -> str   # returns did:viridis:<16hex> (fleet R1 formula)
```
Notes: `TrustRoot` satisfies the existing `Signer` Protocol so it drops straight into `Certifier(signer=...)`.
`bind_did` must reproduce the fleet's DID exactly: `"did:viridis:" + sha256(f"{agent_id}|{pubkey}").hexdigest()[:16]`.

### `integration/mark.py`
```
MARK = "Certified by ViridisOS"
@dataclass(frozen=True)
class Envelope:
    payload: dict
    profile: str            # "conservation-claim" | "agent-attestation"
    root_id: str
    key_id: str
    signature: str
    mark: str = ""
def issue_envelope(root: TrustRoot, profile: str, payload: dict) -> Envelope
def verify_mark(root: TrustRoot, env: Envelope, validator: Callable[[dict], bool]) -> bool
def canonical_bytes(payload: dict) -> bytes   # reuse runtime.provenance.canonical
```
`issue_envelope` signs `canonical_bytes(payload)`, stamps `mark=MARK`, sets `root_id/key_id` from `root`.
`verify_mark` returns True iff `env.mark == MARK` AND `validator(env.payload)` AND
`root.verify(canonical_bytes(env.payload), env.signature)` AND `env.root_id == root.root_id`.

### `integration/toll.py`
```
CARD_RAIL_COST_BPS = 290
MARGIN_BPS = {"new": 200, "connect_onboarded": 150, "connect_verified": 100}
MIN_MARGIN_OVER_RAIL_BPS = 50
def compute_toll(amount_minor: int, payee_tier: str) -> dict
    # returns {"protocol_margin_minor", "protocol_margin_bps", "card_rail_cost_minor", "total_fee_minor"}
    # protocol_margin_bps = max(MARGIN_BPS[tier], MIN_MARGIN_OVER_RAIL_BPS); ceil-bps rounding
```
Use ceil-bps: `-(-amount_minor * bps // 10000)` (matches `escrow_custody._ceil_bps`). Unknown tier → error/raise.

## Acceptance criteria (the failing tests you must turn green)
`integration/tests/test_integration.py` covers: U-1 both profiles verify under one root; U-2 envelope shape;
U-3 mark valid only when standard-valid AND root-signed (forged + standard-invalid both rejected); U-4 both
paths identical + margin applied once + ceil rounding; the cross-profile chain (a `did:viridis` agent issues
a conservation envelope that validates). Run: `cd ViridisOS && python3 -m pytest integration/tests -q`.

## Out of scope (do NOT do)
- No real K3 / production key custody — keep the dev `HmacSigner` behind `TrustRoot` (prod swap is a later task).
- No changes to canon resolution, module engines, fleet gateway payment code, or Stripe.
- No network calls, no new dependencies, no DB. Stdlib only.

## Deviations surfaced (decide if they matter to you, Justin)
1. Toll is bps-tiered (EC10), not flat 1%. Spec reuses the real schedule; the "~1%" is the `connect_verified`
   100bps tier. If you want a single flat protocol rate instead, say so and I'll simplify `toll.py`.
2. Fleet DIDs already use the `viridis` namespace, so `bind_did` unifies cleanly with no migration.
