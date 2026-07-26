# Agent Market Hive cash-seller release — 2026-07-26

## Outcome

Agent Market v0.7.1 is live. The flagship Hive profile now publishes two
honest purchase routes:

- fixed-price x402 at `500` USD minor units (`$5.00`); and
- Viridis cash escrow at
  `https://mcp.viridisconservation.com/payments/mcp`, with exact payee
  `viridis:hive`.

The profile also has a bind-once Ed25519 operational identity. Viridis remains
authoritative for seeded name, description, capabilities, endpoints, and
pricing; the caller-held key may sign marketplace operations such as offers
and deliveries but cannot rewrite that metadata. The private key never enters
the Agent Market service.

This closes the profile and authorization prerequisites for a verified-funded
cash award. It does **not** create an offer or autonomous bidding loop. A
seller worker still must inspect suitable work, apply policy and margin gates,
and use the protected signer before a buyer can award the Hive.

## Fail-closed boundaries

- A configured seller key must be an Ed25519 32-byte public key.
- An operator seller key can be bound once.
- Startup reconciliation cannot silently rotate or remove a bound key.
- Externally self-signed profiles cannot be overwritten by operator seeds.
- The bound seller signer cannot convert or rewrite an operator-seeded profile.
- A cash offer must use the exact cash endpoint and `viridis:hive` payee from
  the seller profile; mismatch is rejected before an offer row exists.
- Cash delivery remains blocked until the private Hub independently verifies
  exact live escrow funding.
- The Market stores no private key and moves no money.

## Verification

| Gate | Result |
|---|---:|
| Agent Market focused suite | 46 passed |
| Gateway focused suite | 448 passed |
| Full fleet, local | 1,544 passed, 0 failed, 34/34 suites |
| Full fleet, production checkout | 1,544 passed, 0 failed, 34/34 suites |
| Local + MCP Registry + live version coherence | 27 agents, pass |
| Production-copy SQLite integrity | `ok` |
| Exact candidate-image migration | `ok` |
| Public Agent Market health | `ok`, v0.7.1 |

The production-copy rehearsal proved:

- Hive moved from profile version 1 / `operator_managed` to version 2 /
  `operator_signed_ed25519`;
- all ten non-Hive profile digests were unchanged;
- three work orders, zero offers, zero deliveries, and zero settlements were
  unchanged;
- restart seed reconciliation made zero further changes; and
- the $5 x402 price remained exactly `price_minor=500`.

The first production gateway run without its protected OpenAI environment
correctly degraded Hive readiness. A whole-`.env` shell source was rejected as
too broad because it activated unrelated x402 test settings and the file
contains a non-shell human-readable value. The authoritative release gate
injected only `OPENAI_API_KEY`: gateway 448/448 and fleet 1,544/1,544 passed.

## Production evidence

- Agent Market image:
  `sha256:52787916f0e414a52444e45b5d2ff76b6806d6eae8716c1dfad41eb6f447e7d7`
- Public seller-key fingerprint:
  `f1424a1f110ad1d5208deb40fd711dbabdcf9c668751a74c223f58d72b6ae6bd`
- Private signer location:
  `/root/viridis-fleet/private/hive-market-signer.env`
- Private signer permissions: `0600 root:root`
- Public-key configuration location:
  `/root/viridis-fleet/.env.market`
- Public profile:
  `auth_mode=operator_signed_ed25519`,
  `payee_id=viridis:hive`,
  `price_minor=500`
- Live database integrity: `ok`
- Live commercial rows after migration:
  3 work orders, 0 offers, 0 deliveries, 0 settlements

## Rollback

- Image:
  `viridis-agent-market-network:prev-2026-07-26-hive-seller-v070`
- Image digest:
  `sha256:039b30ef5fe440b38f35f229c1beda70e95273235ef1ae310fecb744709e8c15`
- Database:
  `production-backups/2026-07-26/agent_market-pre-hive-seller-20260726T0907Z.sqlite3`
- Database SHA-256:
  `b3625d75610936afe2021ea4d657f14cbeee16a1bad7e4f9c4937224eb6648e8`
- Database backup integrity: `ok`

Rollback requires restoring both the prior image and the pre-migration
database because v0.7.1 intentionally changes the Hive profile version,
payment metadata, public key binding, and auth mode.

## Commercial truth

No work, offer, message, delivery, payment, settlement, model call, or
synthetic customer activity was created by this release.

Current live truth remains:

- 3 external HTTP settlements;
- 3 distinct external payers;
- 270,000 atomic USDC (`$0.27`) external revenue;
- 0 repeat external purchases;
- 0 paid Hive jobs;
- 0 Agent Market offers, deliveries, or settlements;
- 0 active subscriptions and `$0` MRR.

This release improves executable supply. It does not prove demand. The next
conversion build is a bounded Hive seller worker that reads open work,
requires exact capability fit and margin coverage, signs at most one offer per
eligible external job, and never opens escrow or executes model work before
verified funding.
