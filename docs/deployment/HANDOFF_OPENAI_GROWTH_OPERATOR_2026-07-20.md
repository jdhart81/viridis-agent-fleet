# OpenAI growth operator handoff — 2026-07-20

**Status:** deployed and active
**Scope:** isolated growth worker only; gateway and all money paths unchanged
**Authorization:** Justin approved a mid-cost OpenAI model and deployment to the
Viridis droplet to help the MCP services earn revenue and expand network effects

## Outcome

The existing policy-cleared growth worker now has a narrowly scoped OpenAI
copywriting and target-prioritization layer. It reads only the public fleet
health snapshot and the existing local target allowlist. It cannot access or
modify Stripe, CDP, x402 settlement, escrow, bonds, Connect, participant state,
prices, or the gateway build.

The provider is fail-safe: if OpenAI is disabled, unavailable, over budget, or
returns copy that fails exact fact validation, the worker uses the existing
deterministic template. Posting continues to use the pre-existing adapter and
append-only write-before-send log.

## Model and dependency

- Model: `gpt-5.6-terra`.
- Official Agents SDK: `openai-agents==0.18.3`.
- Audited wheel SHA-256:
  `c6ed971fdeb34d39a9931787bd3960c1e84dc5d7345705794cc5cab8a1158d07`.
- Execution: Responses API through the Agents SDK; one agent turn, no tools,
  tracing disabled, API retries disabled, structured Pydantic output.
- Default output cap: 700 tokens; absolute configured cap: 900 tokens.
- Exact live facts are injected as ground truth and validated after generation:
  all five route names/prices, payment and intro language, URLs, and external
  settlement proof. Invalid or contradictory copy is never sent.

## Isolation and cost controls

- Master switch: `GROWTH_AGENT_ENABLED`.
- Model sub-switch: `GROWTH_OPENAI_ENABLED`; default off/fail-closed.
- Scoped credential: `GROWTH_OPENAI_API_KEY` in the growth container only.
- Model allowlist: exactly `gpt-5.6-terra`.
- Monthly hard cap: `GROWTH_OPENAI_MONTHLY_BUDGET_USD=20.00`.
- Per-call reserve: `GROWTH_OPENAI_MAX_CALL_RESERVE_USD=0.05`.
- Usage and calculated cost are durably logged in micro-US-dollars. Calls stop
  before the monthly cap could be exceeded; deterministic copy remains usable.
- Runtime inspection: zero Stripe/CDP/x402 variable names, no generic
  `OPENAI_API_KEY`, and no payment/gateway source files in the image.
- Deployment secret file is root-owned mode `0600`. The local saved key file is
  also mode `0600` and excluded from the test/deploy archive.

## Verification

- Focused growth suite: **18 passed / 0 failed**.
- Local fleet gate: **1223 passed / 0 failed / 31/31 suites**.
- Droplet fleet gate from checksum-verified isolated tree:
  **1223 passed / 0 failed / 31/31 suites**.
- Gateway suite remains **368 passed**.
- Nine touched growth source/config/test files match local and droplet by
  SHA-256. The same nine files are byte-identical in the public mirror.
- Candidate image:
  `sha256:c7b46c2030401b0f39e48e6edbc2535a3e0dea44facc6e660c1c7d611479394c`.
- Rollback tag: `viridis-growth-agent:prev-2026-07-20-openai` →
  `sha256:493f85fd55768cf309efbafe1d8f317709ff6183fc3824c6598c3766c2261284`.
- Gateway image is unchanged:
  `sha256:edabff21fbfc1265ab56d2340b6be332767b9d88fa3291ba15174083ee5ffdac`.
- Frozen MCP-v1 x402 SHA is unchanged:
  `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`.

## Production smokes and first action

1. The real-model no-post smoke selected the owned GHG Ledger Smithery target,
   preserved every exact price and live claim, made no send attempt, and cost
   **$0.010840**.
2. After the one-time activation, the first live model call cost **$0.010435**.
3. Target: `smithery-ghg-ledger` / `hartjustin6/ghg-ledger`.
4. Model/log timestamp: `2026-07-20T19:29:16.176661+00:00`.
5. Send result timestamp: `2026-07-20T19:29:24.876024+00:00`.
6. Attempt id: `95a0e716-a3cb-436b-9f6c-dc1f63453690`.
7. Content SHA-256:
   `cf8a4a087a106dabd548e23f088102c80143d869720c268dc0a9f9c06d7d0894`.
8. Smithery receipt: `updated: true`. A public unauthenticated GET returned the
   same 1,736-character description and the same SHA-256.
9. Append-only ordering is `llm_result` row 4, `send_attempt` row 5, then
   successful `send_result` row 6.
10. After revoking the two unused Platform keys, a final no-post model smoke
    cost **$0.008968**, returned valid grounded copy, and made no send attempt.
    Production month-to-date OpenAI spend is **$0.030243**.

The published copy presents the five-agent `measure → account → disclose →
claim → scan` workflow, exact prices, Base-USDC/x402 mechanics, the `$0.01`
new-wallet intro, the live external-buyer proof, and both conversion URLs.

## Unchanged boundaries

- No gateway rebuild or restart.
- No payment, settlement, custody, bond, Connect, participant, or legal-gate
  change.
- No price or promotional-policy change.
- No new posting target. Only owned Smithery listings remain eligible; CDP
  Discord and third-party GitHub remain excluded.
- No autonomous money spending or Bazaar self-settlement was added.

## Key hygiene note

Key cleanup is complete after Justin's explicit approval:

- The never-used duplicate `Codex` key was revoked.
- The unrelated, never-used `Growth/Revenue Operator` key whose plaintext was
  displayed during the authenticated inventory check was revoked.
- The used production `Codex` key remained active throughout and passed a real
  no-post `gpt-5.6-terra` smoke after both revocations.

The dashboard now shows one active `Codex` key. It is the only OpenAI key
deployed to the growth service. No plaintext key is present in source, an image,
or this handoff.
