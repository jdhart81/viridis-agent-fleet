# Growth repeat-buyer release — 2026-07-26

## Outcome

The production growth worker now renders a bounded repeat-buyer call to action
only when live external settlement proof exists. It tells a returning buyer to
put their public signing address in `X402-Payer-Address` on the unpaid preflight
to receive the exact returning-wallet quote on the first 402. It also states
that the hint does not authorize payment and that a private key must never be
sent.

No message was sent during this release. The worker remains inside the existing
target cooldowns, `GROWTH_AGENT_DRY_RUN=1`, and
`GROWTH_OPENAI_ENABLED=0`. Disabling model generation while sends are disabled
prevents API spend without a revenue opportunity.

## Verification

- Growth-agent tests: 34 passed.
- Full fleet: 1,572 passed, 34/34 suites clean.
- Local and production copied-state candidates returned `status: dry_run`,
  `send_attempted: false`, and the exact repeat-buyer guidance.
- The copied audit database remained byte-for-byte unchanged:
  `a96c193d97fc7e5b2d885275b916435f5612d3336a29a70aed38d5e626907514`.
- Production worker image:
  `sha256:72a3f073e0e2da80af2b2c5393ef2bcfe10c76fad98d387b262068c31b1e0c41`.
- Source hash in the running image:
  `25ea78f10e938dd9f7cdb0d25265de81dd54bf3d0938b3532e00b8b990a5100b`.
- Image archive:
  `22bdf0514cc8f8736343743453a6555c412ffc8e7c02e2b8676387478ba3d8ed`.
- Rollback image:
  `sha256:dc515253970ac972ccf0582d320f63341d1f6cab9640ad6d3da7c67a970b7dc8`,
  tagged `viridis-growth-agent:prev-2026-07-26-repeat-buyer`.
- Production state backup:
  `/data/backups/viridis_growth-20260726T181242Z.db`.
- Backup SHA-256:
  `a96c193d97fc7e5b2d885275b916435f5612d3336a29a70aed38d5e626907514`.
- Off-host backup:
  `production-backups/2026-07-26/repeat-buyer-growth-release/`.
- Controlled restart retained 26 audit rows and 7 historical send attempts.
- Public fleet health remained `ok`; the gateway and Agent Market retained
  their uptime and healthy state.
- Root disk remained at 37% used with 15 GB available.

## Cost note

The first production start inherited `GROWTH_OPENAI_ENABLED=1`. Its dry-run
cycle failed over to deterministic copy and conservatively recorded a
`50,000` micro-USD ($0.05) reserve. That audit row was retained. Model
generation was then disabled, the worker was recreated, and subsequent dry-run
cycles used deterministic copy without adding an LLM result or send attempt.

## Publication state

The source and tests are locally committed as `9a7ea17` on the draft PR #28
worktree. GitHub publication is pending repair of the expected `jdhart81`
Keychain-backed `gh` login; no plaintext token or environment token was used.
