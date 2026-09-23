# agent-identity-registry-agent

**Role in the A2A economy:** identity. The passport + directory of the agent
economy — agents register a verifiable identity (content-addressed DID), advertise
capabilities and prices, and become discoverable. Supply-side complement to
demand-side intent routing (wavefunction-search).

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises.
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
| action | inputs | effect |
|---|---|---|
| `register` | agent_id, capabilities[], [name, endpoint, pubkey, pricing, reputation_hint] | create/update a registration (idempotent, versioned); mints DID |
| `resolve` | agent_id \| did | fetch a registration |
| `discover` | capabilities[], [limit] | find ACTIVE agents matching ALL tags, ranked |
| `revoke` | agent_id \| did | mark REVOKED (excluded from discovery, retained for audit) |
| `list` | [status] | all registrations |

## Identity model
`did:viridis:<first16 hex of sha256(agent_id|pubkey)>` — deterministic and
content-addressed, so the same (agent_id, pubkey) always resolves to the same DID.
Discovery uses AND semantics over capability tags and a deterministic sort
(match-count desc, reputation_hint desc, did asc).

## Invariants (R1–R8)
Deterministic DID; idempotent versioned register; discover returns only ACTIVE,
AND-matched; deterministic ordering; unknown → error; revoke terminal for
discovery but record retained; capabilities required non-empty; never raises.
See `src/core.py`.

## Deploy
Primary: MCP server. Secondary: FastAPI. Stdlib-only core. It is the hub the other
two novel A2A agents plug into: **identity → trust → escrow.**
