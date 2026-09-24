# Fleet Error-Envelope Dialects

_Compiled by Nightkeeper, Night 63 (2026-07-19), closing the N61→N63 pin-sweep.
Mapped incrementally across N54-N63 as each stable agent's non-dict input
guard was probed and pinned. Four dialects coexist across the 22-agent A2A +
revenue-service stable. All four are rich (structured, non-raising) and
contract-compliant — **do not unify them**; the churn cost exceeds any
fitness gain. This doc exists so future agent spawns pick a dialect
deliberately instead of drifting into a fifth._

## The rule for new agents

**Use Dialect 1.** It is the majority pattern among the revenue-facing
services and the one PB/PG/x402 client code already expects first.

## Dialect 1 — `input_data` inline-return

- **Field:** `field="input_data"`
- **Constraint message:** `"...must be a dict"`
- **Shape:** validated inline at the top of `process()`, returns a dict
  literal directly (no shared `_err` helper).
- **Agents:** narrative-engine, regulatory-radar, smartscale, protogen.

## Dialect 2 — `input` / `dict` via shared `_err()` (the A2A primitives)

- **Field:** `field="input"`
- **Constraint:** `constraint="dict"`
- **Message:** `"input must be an object"`
- **Shape:** `if not isinstance(input_data, dict): return self._err(...)` —
  a shared `AgentCore._err()` helper stamps `error_type`, `field`, `value`
  (the bad input's `type(...).__name__`), `constraint`, `message`, and
  `timestamp`.
- **Agents:** the full A2A trust chain — identity-registry, trust-oracle,
  escrow, metering, arbitration, compute-ledger, verified-relay, covenant,
  provenance, offset-clearinghouse — plus erc8004-bridge, notary, surety.
  This is the dialect the N54-N63 pin-sweep targeted; as of tonight all 13
  members of this family have a full-envelope regression pin (not just a
  shallow `status=="error"` check).

## Dialect 3 — `input` / `object` raise-path

- **Field:** `field="input"`
- **Constraint:** `constraint="object"`
- **Shape:** validation raises a `ValidationError`-style exception that a
  wrapper catches and converts to the envelope, rather than an inline
  `isinstance` check.
- **Agents:** taxcredit-engine, ghg-ledger, subscriptions, quantity-takeoff,
  disclosure-compiler.

## Dialect 4 — wavefunction's validation-gate errors-list

- **Shape:** a `errors: [...]` list rather than a single `field`/`constraint`
  pair — wavefunction-search validates multiple independent gate conditions
  per call and reports all violations at once instead of failing fast on
  the first one.
- **Agents:** wavefunction-search (sole member; the gate pattern is specific
  to its multi-condition routing logic and is not a candidate for reuse).

## Pin-sweep status (as of Night 63)

All Dialect 2 members (the A2A core, 13 agents) now carry a
`tests/test_nondict_guard.py` pinning the full envelope shape
(`field`/`value`/`constraint`/`message`/`timestamp`), captured via runtime
probe before each test was written. Dialects 1, 3, and 4 were pinned earlier
in the N54-N60 window with envelope shapes matching their own dialect. The
sweep that started with N61's queue is closed.
