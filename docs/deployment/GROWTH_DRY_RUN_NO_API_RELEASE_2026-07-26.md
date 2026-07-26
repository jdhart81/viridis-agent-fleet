# Growth dry-run no-API release — 2026-07-26

## Outcome

`GrowthAgent.run_once(dry_run=True)` now bypasses the OpenAI copywriter in code,
not only through deployment configuration. A dry-run always uses deterministic
grounded copy and reports:

```json
{"mode": "deterministic", "reason": "dry_run_no_api"}
```

This prevents provider cost on a preview that cannot produce revenue, even if
`GROWTH_OPENAI_ENABLED` drifts on. Dry-run also continues to skip sends,
outbound logging, and outcome mutation.

Production retains both defense layers:

- `GROWTH_AGENT_DRY_RUN=1`
- `GROWTH_OPENAI_ENABLED=0`

## Verification

- Growth-agent tests: 35 passed.
- Full fleet: 1,573 passed, 34/34 suites clean.
- Local and production candidates deliberately set OpenAI enabled with a
  sentinel key. Both returned `dry_run_no_api`, made no send attempt, and left
  copied audit state byte-for-byte unchanged.
- Live first cycle: `dry_run_no_api`, `send_attempted=false`.
- Controlled restart cycle: `dry_run_no_api`, `send_attempted=false`.
- Production audit state remained 26 rows, 7 historical send attempts, and 10
  historical LLM-result rows before and after promotion/restart.
- Public fleet health remained `ok`.
- Gateway, Agent Market, and Caddy retained uptime.

## Release artifacts

- Production image:
  `sha256:e1e7346fd3a79d1a41533084f02d8da9197b0c0236bede2b68dd2837b4bfa3b9`.
- Runtime `growth_agent.py` SHA-256:
  `450af2694f1ccedfc324a419befd3650fc8ad8e46737c4a55a5c7720a2f22268`.
- Runtime `targets.json` SHA-256:
  `6d10c97768b48eab230e36aab1f346c392b251a37d6249cf69fd820521b9fffe`.
- Image archive SHA-256:
  `5b4589ca0720a226f752a00bd7ab5a2e63f5218c10f36d9e026a571331a3c333`.
- Rollback image:
  `sha256:72a3f073e0e2da80af2b2c5393ef2bcfe10c76fad98d387b262068c31b1e0c41`,
  tagged `viridis-growth-agent:prev-2026-07-26-dry-run-no-api`.
- Production backup:
  `/data/backups/viridis_growth-20260726T184554Z.db`.
- Backup SHA-256:
  `94cfd84129dac9b0b3f6423ceccc4e0be98e220f294ed0b38740cab28a893dea`.
- Off-host backup:
  `production-backups/2026-07-26/growth-dry-run-no-api-release/`.
- Root disk after release: 39% used, 15 GB available.

## Commercial boundary

No message, payment, model request, customer job, or synthetic conversion was
created. The deployment only removed a possible cost path while dry-run is
active.
