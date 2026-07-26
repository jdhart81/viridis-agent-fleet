# Returning Buyer Exact-Quote Release — 2026-07-26

## Outcome

Returning x402 buyers can now construct the first unpaid preflight correctly
from the machine-readable continuation contract. Eligible repeat and
cross-route offers explicitly say:

- which header carries the payer hint;
- that its value comes from the caller's public signing address;
- whether the route requires that hint for an exact first quote; and
- that the hint does not authorize payment.

This removes an avoidable corrective 402 for returning wallets. It does not
change any price, introductory-pricing eligibility rule, settlement behavior,
payment ceiling, or private-key boundary.

The fixed-price Hive route correctly advertises that a payer hint is not
required for an exact quote. Intro-eligible deterministic routes advertise
that it is required.

## Buyer safety

The public buyer skill, Hermes guide, and first-call quickstart tell buyers to
send only their public signing address in `X402-Payer-Address`. A private key
must never be sent in that header, a prompt, a tool argument, or a log. The
live unpaid 402 remains the only authoritative payment requirement, and every
repeat purchase still requires a fresh mandate and fresh signature.

## Verification

| Gate | Result |
|---|---|
| Focused HTTP x402, A2A, activation, and Hermes tests | 90 passed |
| Canonical isolated fleet | 1,571 passed, 0 failed, 34/34 suites |
| GitHub draft PR security baseline | passed |
| Production-checkout isolated fleet | 1,572 passed, 0 failed, 34/34 suites |
| Production deployment subset | 591 passed |
| Backup integrity and scratch restore | passed, 34 persisted namespaces |
| Current-source snapshot compatibility | passed, zero errors |
| Copied-state candidate | health `ok`, persistence available |
| Copied-state Hive | wired, 3 solvers, provider ready |
| Live returning-wallet unpaid preflight | first 402 quoted 250,000 atomic USDC |
| Controlled restart marker `esc_000038` | survived; audit chain valid |
| Post-restart Docker and public health | healthy / `ok` |

The first environment-matched test attempt incorrectly sourced Docker's env
file as a shell script; one valid value contains spaces, so that launcher
failed closed before cutover. The authoritative rerun read only the existing
`OPENAI_API_KEY` into the test subprocess without printing it. A direct
multi-suite pytest attempt also hit the repository's known shared `src`
namespace collision; the authoritative 591-test deployment subset used the
required per-suite isolation runner.

The first Compose promotion command omitted the explicit project name. It
created a separate `droplet` container, network, and empty volume rather than
touching the running `viridis-fleet` project. Public production remained on
the prior healthy container and original volume. The empty project was
removed, its absence was verified, and the real cutover used
`project=viridis-fleet` plus the protected interpolation env file.

## Backup and image

- production backup:
  `/data/backups/viridis_state-20260726T173617Z.db`;
- off-droplet backup:
  `production-backups/2026-07-26/returning-buyer-exact-quote/`;
- backup SHA-256:
  `cfdf7a0929f9ce215ed48e0e10c0991150116b954825847436fd6d9932b1f3c8`;
- manifest SHA-256:
  `9c3cb1051ecfb6e6b233c4437b12531a20b833232b9a57da0a43f444182082fe`;
- backup size: `565,248` bytes;
- off-host linux/amd64 build image:
  `sha256:df79e8b15e9172683691f9749195e8268d03bd0ab95bb5193a412cb7eae034ac`;
- archive SHA-256:
  `b69bf2eb24ec6f493fb9d471913469b5575decb354b18026d4ba72ffa833adbf`;
- loaded and running image:
  `sha256:e096df0f626e86410c8e3d1d44988e404e4c3c6f70df0388aa16a9da1566f031`;
- running container:
  `030fefaf3aa9a96aac0c215ec5c2f155ee1acd7a0927889d0360350e5160c8d9`;
- rollback tag:
  `viridis-stable:prev-2026-07-26-returning-buyer`; and
- rollback image:
  `sha256:32be1995fb23a9187ed1ac803eb35a5696606f498983fc422af75b4f96dba588`.

Running source hashes:

- `x402_http.py`:
  `a381151cff9a13035c623a4a55e471045233e1b455e23566045a1d805d98f708`;
- public buyer `SKILL.md`:
  `91bd4f0206df384b104a075b78329dccf4b53879be020cf5f8182c1d04103ea3`.

Only the gateway was recreated. Agent Market and Caddy retained their
multi-hour uptimes. The production state volume remained
`viridis-fleet_gateway_state`. Production disk was 37% used with 15 GB
available.

## Public source

- draft PR: `https://github.com/jdhart81/viridis-agent-fleet/pull/28`;
- release commit:
  `935da8ef8db15cc81a44f93de1793e2149db856b`; and
- security baseline: passed.

The PR remains draft and unmerged. This release did not merge PR #27 or #28,
close PRs #20-#25, publish a Registry version, or authorize consolidation.

## Commercial boundary

No paid request was made and no money moved. The live proof used only an
unpaid 402 preflight and did not disclose the returning wallet.

- x402 settlements: 7 total, 4 self, 3 external;
- distinct external payers: 3;
- external revenue: 270,000 atomic USDC (`$0.27`);
- repeat external purchases: 0;
- paid Hive settlements: 0;
- A2A tasks: 1 input-required, 0 completed;
- active subscriptions / MRR: 0 / `$0`; and
- subscription page views / checkouts: 11 / 0.

The next commercial proof is still one arm's-length repeat purchase. This
release makes that path cleaner; it does not claim that the repeat purchase
has happened.
