# Quickstart repeat-buyer release — 2026-07-26

## Outcome

The public `/quickstart` now tells both new and returning buyers to put their
public signing address in `X402-Payer-Address` on the unpaid preflight so the
first 402 reflects that wallet's exact price eligibility. It also states that
the header is an unsigned quote hint, never authorizes payment, and must never
contain a private key.

This aligns the human quickstart with the machine-readable 402 contract, the
Viridis paid-tools skill, the Hermes buyer guide, and the growth worker.

## Gates

- Quickstart and Hermes page tests: 11 passed.
- Full fleet: 1,572 passed, 34/34 suites clean.
- Production copied-state candidate: healthy, x402 enabled, SQLite integrity
  `ok`, and exact repeat-buyer copy present.
- Public post-promotion health: `ok`, x402 enabled.
- Public `/quickstart`: exact repeat-buyer copy present.
- Controlled restart retained all 34 `agent_state` rows.
- Gateway runtime remained healthy after restart.
- Agent Market, Caddy, and the growth worker retained uptime during the
  one-service gateway promotion.

## Release artifacts

- Production image:
  `sha256:6e9828e6302bf38957731d5f695202749f4e6732ddb915b06ca43ea618dd6695`.
- Quickstart runtime SHA-256:
  `7138c498a5e76f19028c74ea60ea55ecb48abf1b25acdc34cb86f065a62c00be`.
- x402 runtime SHA-256:
  `a381151cff9a13035c623a4a55e471045233e1b455e23566045a1d805d98f708`.
- Image archive SHA-256:
  `55bf7ef882c66ce9655fd32249f47a9d445fda03b78e9df9109dccc115337c3a`.
- Rollback image:
  `sha256:e096df0f626e86410c8e3d1d44988e404e4c3c6f70df0388aa16a9da1566f031`,
  tagged `viridis-stable:prev-2026-07-26-quickstart-repeat-buyer`.
- Production backup:
  `/data/backups/viridis_state-20260726T183125Z.db`.
- Backup SHA-256:
  `1b7300022d6b0ac65764f03204ee24328ab86fea95263e2599e8c99ceb3d4df5`.
- Off-host backup:
  `production-backups/2026-07-26/quickstart-repeat-buyer-release/`.
- Root disk after release: 38% used, 15 GB available.

## Publication state

The quickstart source and regression gate are locally committed as `fd78295`
on the draft PR #28 worktree. GitHub publication remains pending the official
device approval for the expected `jdhart81` Keychain-backed login.
