# Growth-worker funding-truth release

**Released:** 2026-07-26 UTC
**Outcome:** Live and verified
**Messages sent:** None
**Money moved:** None

## Business outcome

The distribution worker no longer describes an Agent Market listing as paid
work merely because it is open and carries a positive USD budget.

Only work whose catalog record has the exact independently verified funding
state `VERIFIED` can enter a fleet snapshot or outbound message. Missing,
unknown, and `UNVERIFIED` funding states fail closed. The current live catalog
contains three open records and all three are `UNVERIFIED`, so none of their
IDs, titles, or advertised budgets now appears in growth-worker copy.

The truthful current classification is **unfunded inventory**, not paid work,
demand, revenue, or a customer commitment.

The live six-agent x402 suite also exceeded the safe Discord length once the
unverified work block was removed and full route descriptions returned. The
renderer now automatically switches to concise route lines when necessary,
while preserving every exact live agent name, price, required URL, intro
offer, and external-settlement proof. It still refuses output above the
1,900-character safety ceiling.

## Verification

| Gate | Result |
|---|---:|
| Growth-agent suite | 33 passed |
| Local full fleet | 1,528 passed, 0 failed, 34/34 suites |
| Candidate local live-catalog smoke | `dry_run`, `send_attempted=false` |
| Candidate server live-catalog smoke | `dry_run`, `send_attempted=false` |
| Production startup decision | `no_cleared_target`, `send_attempted=false` |
| Production-checkout gateway | 439 passed |
| Production-checkout full fleet | 1,528 passed, 0 failed, 34/34 suites |
| Growth-state integrity | `ok`, 25 events, 7 attempts, 7 results |
| Live catalog funding states | 3 records; only `UNVERIFIED` |

The production-checkout test shell initially reported six gateway health
failures because it had no provider-readiness marker for the newly wired Hive.
The focused gateway suite passed 439/439 and the full fleet passed 1,528/1,528
with the explicit non-secret `OPENAI_API_KEY=test-only` test marker. No model
request was made. This was an environment-only test precondition, not a
runtime or release regression.

Both candidate smokes used deterministic copy with the model switch off. The
result contained all six exact live prices and no current Agent Market work
ID, title, or budget. No cooldown, credential, or policy gate was bypassed.

## Production and rollback

Production image:

`sha256:dc515253970ac972ccf0582d320f63341d1f6cab9640ad6d3da7c67a970b7dc8`

Off-host build image:

`sha256:2e66ab40d7212ea027f1fee6a907a8c61cc910ed34a6adce9b9f51398b597d2b`

The image ID normalized during `docker load`; the transferred archive checksum
and all runtime source hashes match.

Rollback:

- tag: `viridis-growth-agent:prev-2026-07-26-funding-truth`
- image:
  `sha256:6ceddc01ff5b34569ef3b9da7d0289f8037c8f27a8f0d864b4808f0792d37773`

Transferred image archive SHA-256:

`fd7f9ec9ff130cbc290791a5d332201d9ba5375e43664414ccb9fd4240ab96dd`

Runtime source hashes:

- `/app/main.py`:
  `d83b0547bff6a6f9eae59bbd7fe0bbfa6b127a623c299887811e34f3e6567a48`
- `/app/growth_agent.py`:
  `71ede7fd6d2bbd127b5741552fab9aa9509d5d433be97fe68ff7ea29d0acd108`
- `/app/targets.json`:
  `6d10c97768b48eab230e36aab1f346c392b251a37d6249cf69fd820521b9fffe`

Transactional growth-state backup:

- droplet:
  `/state/backups/viridis_growth-pre-funding-truth-20260726T073224Z.db`
- off-droplet:
  `production-backups/2026-07-26/viridis_growth-pre-funding-truth-20260726T073224Z.db`
- SHA-256:
  `a96c193d97fc7e5b2d885275b916435f5612d3336a29a70aed38d5e626907514`
- SQLite integrity: `ok`

Only `growth-agent-growth-agent-1` was recreated. The gateway, Agent Market,
Caddy, payment rails, and all their state volumes were untouched. The growth
state volume was retained.

## Honest commercial baseline

Live truth remains:

- 3 external settlements from 3 distinct external payers;
- 270,000 atomic USDC / `$0.27` external revenue;
- 0 repeat external purchases;
- 0 paid Hive jobs;
- 0 independently useful paid Agent Market deliveries;
- 3 open but unfunded Agent Market records;
- 0 active subscriptions; and
- `$0` MRR.

Commercial truth improved. Demand and revenue did not.
