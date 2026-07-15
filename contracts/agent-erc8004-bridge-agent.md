# agent-erc8004-bridge-agent

The MCP-native bridge to **ERC-8004** — the on-chain agent identity /
reputation / validation standard (Ethereum Foundation + Google + Coinbase;
mainnet Feb 2026; 170k+ registered agents).

## Why it exists (mission invariance)

The 2026-07-10 offering review found ERC-8004 commoditizes standalone
identity/trust registries. Per fleet doctrine, new agents must strengthen the
existing loop, not add islands: this bridge is **demand-side** — it makes the
world's largest agent-identity network resolvable, scorable, and bindable from
any MCP client, and every resolved agent is a candidate counterparty for the
fleet's escrow / metering / covenant / offset rails.

## Contract (fleet-standard)

- `async process(dict) -> dict` — dispatches on `action`; **never raises**;
  structured error envelope on bad input.
- `async health() -> dict`, `def describe() -> dict`;
  `describe().name == health().agent`.
- Stdlib-only core. State is in-memory; durability is provided by the
  gateway StateStore (PS1–PS8).

## Actions

| action | what it does |
|---|---|
| `import_registration` | ERC-8004 Identity record → canonical bridge record + deterministic DID `did:viridis:erc8004:<chain>:<token>` (idempotent) |
| `resolve` | by bridge DID or (chain_id, token_id) |
| `import_feedback` | Reputation Registry records, idempotent per feedback_id |
| `score` | decay-weighted trust score [0,1] + tier (neutral 0.5 prior) |
| `bind` | order-independent, content-addressed fleet-DID ↔ ERC-8004 binding |
| `export_attestation` | **unsigned** Validation-Registry-shaped payload for the caller's own signer |
| `verify` | recompute content hash, detect tampering |
| `list` | all imported registrations |

## Invariants — B1–B8

B1 deterministic/distinct DIDs · B2 idempotent import · B3 bounded,
prior-anchored, monotone, recency-weighted scoring · B4 content-addressed
exports with tamper detection · B5 **no key custody, no chain writes, key
material refused on sight** · B6 never raises · B7 total resolution ·
B8 symmetric bindings. One test per invariant in `tests/test_core.py`.

## Custody note

This agent holds no keys and writes to no chain — by invariant, not by
configuration. Anchoring an exported attestation is the caller's act with the
caller's signer.
