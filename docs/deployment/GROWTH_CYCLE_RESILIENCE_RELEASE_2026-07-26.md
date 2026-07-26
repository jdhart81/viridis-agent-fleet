# Growth-worker cycle resilience release

**Released:** 2026-07-26 UTC
**Outcome:** Live and verified
**Messages sent:** None
**Money moved:** None

## Business outcome

The isolated fleet distribution worker now survives expected live-read
failures without terminating its long-running scheduler.

Previously, a transient gateway or Agent Market read failure raised
`GrowthError` out of `main.py`. Docker's `unless-stopped` policy eventually
restarted the worker, but the cycle lost its structured result and the
container could churn during an upstream outage.

The scheduler now converts expected operational failures into:

```json
{
  "status": "cycle_failed",
  "error_type": "GrowthError",
  "send_attempted": false
}
```

The worker then waits for its normal interval and retries. Unexpected
programming exceptions still raise, so the boundary does not hide code
defects. Posting failures remain governed by the existing append-before-send
attempt log and are not reclassified by this change.

## Current distribution decision

The current production dry run used deterministic copy with the model switch
off. It returned `send_attempted=false`.

No target is eligible:

- owned Discord channels: cooldown until 2026-08-07 UTC;
- owned GitHub live-suite document: cooldown until 2026-08-03 UTC;
- owned Smithery listings: cooldown until 2026-08-19 or 2026-08-20 UTC;
- CDP Discord: policy not cleared;
- third-party x402 ecosystem listing: policy not cleared.

No cooldown or policy boundary was bypassed. No model call, outbound attempt,
message, listing update, payment, or customer activity was created.

## Verification

| Gate | Result |
|---|---:|
| Growth-agent suite | 30 passed |
| Local full fleet | 1,525 passed, 0 failed, 34/34 suites |
| Production-checkout full fleet | 1,525 passed, 0 failed, 34/34 suites |
| Candidate unreachable-upstream smoke | `cycle_failed`, `send_attempted=false`, exit 0 |
| Candidate kill-switch smoke | `disabled`, no network or send |
| Post-promotion unreachable-upstream smoke | `cycle_failed`, `send_attempted=false` |
| Production startup decision | `no_cleared_target`, `send_attempted=false` |
| Growth-state integrity | `ok`, 25 events, 7 attempts, 7 results |

The startup cycle preserved the append-only database byte semantics at the
logical level: 25 total events, seven send attempts, and seven matching send
results before and after promotion.

## Production and rollback

Production image:

`sha256:6ceddc01ff5b34569ef3b9da7d0289f8037c8f27a8f0d864b4808f0792d37773`

Rollback:

- tag: `viridis-growth-agent:prev-2026-07-26-cycle-resilience`
- image:
  `sha256:e9645fc490b74740534aabe160e5e5aa688789f769956ccf3a973c484ad95f55`

Transferred image archive SHA-256:

`9f1f8a8d22721b0f66ff31eef1061fc47b60f75c0bf4fce8603f7b2fcd517ccf`

Runtime source hashes:

- `/app/main.py`:
  `d83b0547bff6a6f9eae59bbd7fe0bbfa6b127a623c299887811e34f3e6567a48`
- `/app/growth_agent.py`:
  `f6639de840457902893390d8909da0d4544fc2f3e06c76c98ceefad6fd91ea63`
- `/app/targets.json`:
  `6d10c97768b48eab230e36aab1f346c392b251a37d6249cf69fd820521b9fffe`

Transactional growth-state backup:

- droplet:
  `/state/backups/viridis_growth-pre-cycle-resilience-20260726T0724Z.db`
- off-droplet:
  `production-backups/2026-07-26/viridis_growth-pre-cycle-resilience-20260726T0724Z.db`
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
- 0 active subscriptions; and
- `$0` MRR.

Reliability of the distribution loop improved. Demand and revenue did not.
