# agent-trust-oracle-agent

**Role in the A2A economy:** trust. Answers "can this agent be trusted with
authority, money, or tools?" with a bounded, decay-weighted reputation score and
tamper-evident trust attestations. The commercial embodiment of the Viridis
Security thesis.

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises.
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
| action | inputs | effect |
|---|---|---|
| `record_outcome` | agent_id, kind, [weight, counterparty, note] | log a behavior outcome; update reputation |
| `score` / `query` | agent_id | current score + tier (neutral 0.5 prior if unknown) |
| `attest` | agent_id, [claim] | issue a signed reputation attestation (hash-chained) |
| `verify_attestation` | agent_id, attestation_id | validate an attestation |
| `history` | agent_id | outcome log + current score/tier |

Outcome kinds: `success, delivered, dispute_won` (positive); `failure,
undelivered, dispute_lost, timeout` (negative); `security_incident` (heavy penalty).

## Scoring model
Beta-smoothed, time-decayed success/failure counts → score in [0,1]. Prior
strength gives unknown agents a neutral 0.5. Half-life (default 30 days) means
recent behavior dominates. Tiers: TRUSTED ≥0.85, RELIABLE ≥0.65, NEUTRAL ≥0.40,
CAUTION ≥0.20, else UNTRUSTED. Framed thermodynamically: reputation is
decay-weighted log-odds of good behavior (Adversarial Landauer lineage).

## Invariants (T1–T8)
Score bounded [0,1]; unknown → 0.5; monotone in evidence; time decay;
tamper-evident attestation chain + verification; deterministic tiers; never
raises on bad input. See `src/core.py`.

## Deploy
Primary: MCP server. Secondary: FastAPI. Stdlib-only core. Composes upstream with
ShenDao/OTA signals and downstream with agent-escrow-agent (dispute outcomes feed
reputation).
