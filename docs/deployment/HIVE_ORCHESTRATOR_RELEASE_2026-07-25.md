# Agent Hive Orchestrator release

**Released:** 2026-07-25 MDT / 2026-07-26 UTC

**Outcome:** Live, public, and active/latest in the official MCP Registry

**Money moved:** None

## Product

`agent-hive-orchestrator-agent` v0.1.0 is live at:

`https://mcp.viridisconservation.com/hive/mcp`

The six-tool MCP surface hires three OpenAI-backed solver workers through the
fleet's exact shared trust, covenant, escrow, metering, and compute-ledger
instances. Reviewer and author remain distinct, covenant denial occurs before
escrow creation, accepted contributions settle and post compute work, rejected
contributions dispute/refund, and the final audit remains content-addressed.

The production health and two read-only MCP calls verified:

- 27 live agents and no mount errors;
- Hive health `ok`, `rails_mode=wired`, and all five shared dependencies ready;
- three registered solver workers and provider readiness;
- six published Hive tools;
- $5.00 per model-backed solve; read-only tools and unpaid preflight are free,
  but execution has no free tier.

No live solve, provider request, customer job, payment, signature, or outreach
was generated during release verification.

## Commercial guardrail

The production profile uses the pinned `gpt-5-mini-2025-08-07` model and
enforces the cost limit before provider access or job mutation:

- at most four subtasks;
- redundancy at most three;
- at most 12 solver attempts and 12 cross-reviews;
- solve output capped at 2,048 tokens and review output at 256 tokens;
- conservative provider-cost ceiling below $0.18 per solve;
- solver settlements capped at $3.00 per solve;
- list price $5.00, leaving at least $1.82 contribution margin, or 36.4%,
  before fixed infrastructure, taxes, refunds, and payment fees.
- machine-enforced contribution-margin floor: 35%.

The estimate pessimistically treats every input character as one token and
uses OpenAI's published GPT-5 mini rates of $0.25 per million input tokens and
$2.00 per million output tokens:
`https://developers.openai.com/api/docs/models/gpt-5-mini`.

Provider-backed free solves were disabled after the release audit showed that
even a bounded promotion could incur API cost with no covering revenue.
Read-only inspection and unpaid quote/preflight remain free. Internal
monitoring must not invoke the provider.

## Release gates

- Hive package: 41 passed.
- Real-rail composition proof: 21/21 invariants.
- Gateway: 431 passed.
- Glama/distribution: 25 passed.
- Full fleet on the production source snapshot: 1,503 passed, 0 failed,
  0 errors, 34/34 suites clean.
- Local + official Registry + live coherence: 27 agents, pass.
- Live distribution generation: 27 agents plus one infrastructure surface,
  210 tools; Hive contributes six.
- Candidate image health: 27 agents, Hive wired, three workers, provider ready,
  exact $5/no-provider-backed-free-solve contract.
- Post-cutover image health: same result, no mount errors.

Nightkeeper requires no separate allowlist. It discovers non-underscore agent
directories in the stable root, and the Hive test path is explicitly present
in `pyproject.toml`; the next nightly run therefore includes the new agent.

## Recovery proof

Pre-release database backup:

- container path:
  `/data/backups/viridis_state-20260726T000007Z.db`;
- SHA-256:
  `3e559a2cf42b374e6608629f41cadb9b778b677c62d1d98bb8007244e2594e61`;
- size: 544,768 bytes;
- SQLite integrity: `ok`;
- pre-release state rows: 32;
- offsite copy:
  `backups/offsite/2026-07-25-hive-release/`;
- compatibility check: all 32 rows load with zero adapter errors;
- scratch restore:
  `/data/restore-drills/viridis_state-20260726T000007Z-hive-release.db`;
- measured restore-drill RTO: one second.

The post-release snapshot has 33 rows because Hive is now a registered
persistence surface.

Image recovery:

- live/candidate image:
  `sha256:19e9c3fbc9be23410d66cfa71950b454a4e285ebe47c13e8b971b829a3cccac9`;
- rollback tag:
  `viridis-stable:rollback-pre-hive-20260725`;
- rollback image:
  `sha256:064c7e513516f04438ef69f7ec59bb50df83e01000374242fffa048c93a0934c`.

Source recovery archives are stored under `/root/release-backups/` on the fleet
host. The staged release bundle SHA-256 is
`a0b01c07e6ed12269d5c3c80b38f6ac6e429ded601ac29553280a74a9cc62d3e`.

## Public and Registry receipts

- Public pull request:
  `https://github.com/jdhart81/viridis-agent-fleet/pull/18`
- Merged source commit:
  `dca3ce8830e6aa6abb3ed02502cbf4747a174a4a`
- Post-merge security baseline:
  `https://github.com/jdhart81/viridis-agent-fleet/actions/runs/30181202756`
- Official MCP Registry publication:
  `https://github.com/jdhart81/viridis-agent-fleet/actions/runs/30181217797`
- Official identity:
  `io.github.jdhart81/agent-hive-orchestrator`
- Published version: `0.1.0`
- Registry state: active/latest

## Revenue boundary

Release verification left strict commercial truth unchanged:

- seven strict settlements;
- four self settlements;
- three external settlements from three distinct external payers;
- zero repeat external purchases;
- 270,000 atomic USDC, or $0.27, external revenue;
- $0 MRR.

The Hive is now a sellable and discoverable product. Deployment and Registry
visibility are not customer demand, repeat purchase, or signed revenue.
