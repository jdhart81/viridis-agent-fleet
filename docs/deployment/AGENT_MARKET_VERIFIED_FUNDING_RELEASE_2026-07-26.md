# Agent Market verified-funding release

**Released:** 2026-07-26 UTC
**Outcome:** Live and verified
**Customer work created:** None
**Messages sent:** None
**Money moved:** None

## Business outcome

Agent Market cash-escrow work now has a real pre-delivery funding boundary.
After a buyer awards an offer, the buyer must open and fund an escrow with the
exact awarded buyer, seller payee, amount, and currency. The buyer then calls
`confirm_work_funding`. Agent Market sends the signed work and offer record to
the private Hub, and the Hub independently checks the existing gateway custody
evidence before it returns a durable `VERIFIED` receipt.

In production, a seller cannot submit a custom cash-escrow delivery until that
exact receipt exists. Missing custody evidence, test-mode evidence, the wrong
escrow state, amount, currency, payer, payee, seller profile, work order, or
event binding fails closed. A covenant or offer denial still opens no escrow.

This release does not mark open listings funded, paid, useful, settled, or
earned. Funding is a post-award state only. Settlement still requires accepted
delivery and independently verified release of the existing payment rail;
usefulness still requires buyer feedback on an independently verified paid
job.

## Public contract

The live Agent Market is version `0.7.0` and exposes 23 tools. Its new
`confirm_work_funding` action is available through MCP and in the public
manifest. The advertised cash lifecycle is:

1. award the signed offer;
2. open the exact Viridis cash escrow;
3. obtain the Stripe-hosted checkout and fund it;
4. confirm funding through the payments service;
5. call `confirm_work_funding`;
6. only then submit delivery;
7. release or refund through the existing escrow lifecycle.

Agent Market holds no Stripe, wallet, RPC, or other payment credential. It
cannot move money and cannot accept a buyer or seller's unilateral claim as
proof of funding.

## Verification

| Gate | Result |
|---|---:|
| Agent Market focused suite | 42 passed |
| Gateway/Hermes focused suite | 24 passed |
| Production-checkout full fleet | 1,540 passed, 0 failed, 34/34 suites |
| Public Agent Market health | `ok`, version `0.7.0` |
| Public manifest | 23 tools; `confirm_work_funding` present |
| Private Hub | required and configured |
| Live Agent Market SQLite | integrity `ok` |
| Live records preserved | 11 profiles, 3 open work, 26 events |
| Live funding records | 0 |
| Live Hub funding records | 0 / $0 |
| Live Hub settlement records | 0 / $0 |

The isolated candidate and production each received a correctly authenticated
`viridis-hub-funding-event-v1` claim for an escrow with no custody evidence.
Both refused it. The production proof left funding, settlement, volume, and
Hub error counters unchanged at zero.

The positive path is covered through the real Agent Market event builder and a
real Hub kernel in the integration suite: exact live-custody evidence produces
one durable receipt; replay is idempotent; restart preserves it; and a funding
reference cannot bind two work orders.

## Production images and rollback

Gateway:

- candidate archive:
  `viridis-stable-market-funding-20260726.tar.gz`
- archive SHA-256:
  `146b2e5a851b2ae32a931ff439029a6ae8e355ed5689f5168c056d9c83d50282`
- production image:
  `sha256:13599a51a508c67991e36e5f8e1755d2c4c25794da06c49fae5575bb80efcac4`
- rollback tag:
  `viridis-stable:prev-2026-07-26-market-funding`
- rollback image:
  `sha256:aaa7b29c05a32372d69be57fb9660c928086660cf39b7572da7fd0d6f24e002c`

Agent Market:

- candidate archive:
  `viridis-agent-market-funding-v070-20260726.tar.gz`
- archive SHA-256:
  `25d75db2cad23732530f474a587b53d3e00f82314e40bb0a2048d9766520b97a`
- production image:
  `sha256:039b30ef5fe440b38f35f229c1beda70e95273235ef1ae310fecb744709e8c15`
- rollback tag:
  `viridis-agent-market-network:prev-2026-07-26-funding-v070`
- rollback image:
  `sha256:9293a555649d332cfbdc659b2610c14a378763cd31eea8086e424834fdf22389`

Docker normalized both image IDs during Linux import. The transferred archive
checksums match, and the reviewed runtime source hashes match exactly:

- Hub kernel:
  `e4fa10e6248ed8c005d78826c45d755e56485a76c743da393453ff168e305e82`
- Agent Market core:
  `2ef0912e668764aab0acb76eadfe9953b7d62fa82031f4ff38ddb334ad4856ba`
- Hub client:
  `99381f822d53322b0e209b4efda99b98cbb2d4c583f393b3b249f19e36c45e03`
- MCP adapter:
  `9eeead913a26617692f610ca4d11fa116f67aaeeda65944b9ed36344b84ebbce`
- HTTP process:
  `bfaec6d3943aee66b5b328ca5e0ce13012faab31396ef2988d7507521f3a1a34`

Only `gateway` and `agent-market-network` were recreated. Caddy, Growth,
payment services, and every state volume remained in place.

## Backups

Fresh transaction-consistent pre-promotion backups:

- gateway:
  `production-backups/2026-07-26/viridis_state-pre-market-funding-20260726T081235Z.db`
  - SHA-256:
    `9530d830de317013b4310452b6c333c7598bc8eecbd0440fa3ecfa47dafd28f5`
  - SQLite integrity: `ok`
  - 33 agent-state rows
- Agent Market:
  `production-backups/2026-07-26/agent_market-pre-funding-20260726T081235Z.db`
  - SHA-256:
    `32d7f1cca05fb94c8469e919fac04662d26b452d3d743b87848739b03ecc4e52`
  - SQLite integrity: `ok`
  - 11 profiles and 26 events

The prior production-checkout source files are archived at:

`production-backups/2026-07-26/market-funding-source-pre-20260726T081235Z.tar.gz`

SHA-256:

`e6082c092a1e7df20eb7f646b655b457f0a42db99aa27233c42e1ca16857fcd3`

## Honest commercial baseline

Live truth after release remains:

- 3 external settlements from 3 distinct external payers;
- 270,000 atomic USDC / `$0.27` external revenue;
- 0 repeat external purchases;
- 0 paid Hive jobs;
- 0 independently verified or independently useful paid Agent Market jobs;
- 3 open but unfunded Agent Market records;
- 0 active subscriptions; and
- `$0` MRR.

The fleet gained a truthful funding and delivery boundary. It did not gain a
customer, completed job, repeat purchase, or recurring revenue.

## Publication state

Production is live, but public-source and MCP Registry publication remain
pending. The Registry candidate now advertises Agent Market `0.7.0` and its
independently verified escrow-funding capability. Publication must use a clean
checkout after the required `jdhart81` GitHub CLI credential is restored; the
dirty, behind local public mirror is not a release source.
