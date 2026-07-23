# Hermes buyer access deployment — 2026-07-22

## Outcome

Hermes Agent operators can now connect their own Hermes runtime to Viridis's
public Agent Market MCP and use a keyless procedural skill to discover and buy
the five live x402 carbon and compliance services. Viridis does not install,
host, or operate Hermes.

## Published artifacts

- `integrations/viridis-paid-tools/SKILL.md`
- `integrations/viridis-paid-tools/agents/openai.yaml`
- `integrations/hermes-catalog/viridis-agent-market/manifest.yaml`
- `docs/integrations/HERMES_BUYER_QUICKSTART.md`
- `docs/QUICKSTART_FIRST_CALL.md`
- hosted `/quickstart` and `/llms.txt` links
- regression coverage in `deploy/gateway/test_hermes_buyer_access.py` and
  `deploy/gateway/test_wave9_activation.py`

GitHub publication: PR
[`jdhart81/viridis-agent-fleet#2`](https://github.com/jdhart81/viridis-agent-fleet/pull/2),
squash commit `2af7d6840a09f79aef1e2b5857da1286ccdbb72e`.

## Gates

- Fleet: **1318 passed / 0 failed / 33 of 33 suites**
- Gateway: **387 passed**
- Focused source-tree tests: **7 passed**
- Focused public-mirror tests: **7 passed**
- Skill validator: **valid**
- Buyer asset SHA comparison, local to droplet: **2 of 2 identical**

## Production cutover

The local tree contained unrelated in-progress Agent Market and security work.
To keep that work out of production, the candidate inherited the exact current
live gateway image and replaced only `quickstart.html` and `llms.txt`.

- Previous/live rollback image:
  `sha256:1bc384e412c559116b69d207cf7438f43e0ec7fdced55e5c521d8f4ea79dc3e2`
- Rollback tag: `viridis-stable:prev-2026-07-22-hermes`
- Candidate/live image:
  `sha256:6c2f2b9082fd180aa6da26e2834290029fa4f902117181c36bbfa538f0b44b1d`
- Candidate tag: `viridis-stable:candidate-2026-07-22-hermes`
- Disk before/after: 24 GB total, 5.4 GB used, 18 GB free (24% used)

The gateway and Agent Market containers were healthy after cutover.

## Live smokes

- `/healthz`: `status=ok`
- `/quickstart`: Hermes remote-connect commands and buyer-safety text present
- `/llms.txt`: buyer guide and raw skill links present
- raw GitHub skill: reachable from `main`
- `/network/mcp`: `network_status`, `search_agents`, `search_work`, and
  `list_security_attestations` discoverable
- unpaid `regulatory-radar` request: HTTP 402, x402 v2, `eip155:8453`, amount
  `10000` atomic USDC for a new wallet, correct Viridis receiver
- no paid request was signed or settled
- frozen v1 MCP rail SHA before/after:
  `ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770`

## Commercial telemetry after validation

- HTTP x402 settlements: 5 total
- self settlements: 4
- external settlements: 1
- distinct external payers: 1
- external revenue: 250,000 atomic USDC ($0.25)
- first external settlement:
  `0x29e3f2833c96da4d64c4d06f668901c93e97fd87146c6f1fb85181681200e9f5`

The unpaid deployment validation did not change any settlement or revenue
counter. The next commercial proof remains a second independent external payer.
