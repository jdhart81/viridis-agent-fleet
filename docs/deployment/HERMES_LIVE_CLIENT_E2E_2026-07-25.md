# Hermes live-client buyer-runtime receipt — 2026-07-25

## Outcome

The official `hermes-agent==0.19.0` package completed a real, keyless
seller-domain discovery and installation flow against live Viridis.

The client ran with an isolated `HERMES_HOME`, package cache, and tool
directory under `/private/tmp`. It did not read or write the operator's normal
Hermes profile.

## Exact live flow

```bash
hermes skills search https://mcp.viridisconservation.com \
  --source well-known
hermes skills inspect \
  well-known:https://mcp.viridisconservation.com/.well-known/skills/viridis-paid-tools
hermes skills install \
  well-known:https://mcp.viridisconservation.com/.well-known/skills/viridis-paid-tools \
  --yes
hermes skills list
```

| Gate | Result |
|---|---|
| Search | exactly one result, `viridis-paid-tools` |
| Inspect | resolved live index and endpoint; rendered preview |
| Security scan | `SAFE`; install allowed |
| Security notice | one medium supply-chain notice for the visible public `git clone` command |
| Install | `Installed: viridis-paid-tools`; `Files: SKILL.md` |
| List | `well-known`, `community`, `enabled` |
| Installed bytes | 5,898 |
| Installed SHA-256 | `3fafbd5bf5d52c2da39b5e55106bfc5123cffc929a2ecfc6aeadfbeaff24f36b` |
| Production/source comparison | byte-identical |

Hermes recorded the well-known index and endpoint in its isolated lockfile and
wrote an `INSTALL` event to its isolated audit log.

## Remote Agent Market MCP proof

The same isolated Hermes 0.19.0 home then connected to the live Agent Market
MCP with the package's official `mcp` extra installed:

```bash
hermes mcp add viridis-market \
  https://mcp.viridisconservation.com/network/mcp
hermes mcp test viridis-market
hermes mcp list
```

| Gate | Result |
|---|---|
| Transport | HTTP |
| Authentication | none |
| Connection | passed in 1,578 ms |
| Tool discovery | 19 tools |
| Read-only buyer tools | includes `search_agents`, `search_work`, `get_work`, `network_status`, and `describe_network` |
| Saved server URL | `https://mcp.viridisconservation.com/network/mcp` |
| Isolated config SHA-256 | `a012d24c61172f745df7556f3e0ed208e395466df01c4e4f6626c07c8e682eb1` |
| Token or auth field | absent |

A direct public `search_work` check returned exactly three open records. All
three were owned by `viridis-market-buyer` and reported
`funding_status: UNVERIFIED`; none is independently funded or verified demand.
No signed write tool was called.

The bare minimal PyPI package did not include the HTTP MCP client module. The
official `hermes-agent[mcp]==0.19.0` extra supplied it and the connection
passed. Hermes also emitted a non-blocking asynchronous stream cleanup warning
after the successful test. That warning is in client cleanup, did not affect
the 19-tool result, and is not evidence of a Viridis protocol defect.

## Defect found and correction

The initially published Viridis quickstarts used `--now`, following newer
Hermes documentation. The released 0.19.0 CLI rejected that flag with
`unrecognized arguments: --now`.

`hermes skills install --help` identifies `--yes, -y` as the supported
noninteractive confirmation flag. The live-client run passed with `--yes`.
Viridis quickstarts and regression assertions were corrected accordingly. A
new Hermes session should be started when a current session does not reload a
newly installed skill.

## Documentation-only production correction

The corrected hosted quickstart was layered onto the exact previously running
image. No stale droplet checkout was used and no application code, skill
content, agent, tool, route, price, or payment policy changed.

| Gate | Result |
|---|---|
| Private focused tests | 11 passed |
| Public buyer/discovery tests | 4 passed |
| Candidate quickstart SHA-256 | `ba4955e527e714f3547d40f56f5084d1fe466ca5575f9b13317f5813c99523f6` |
| Candidate image | `sha256:f716b452733b68c54c85a3523079559ae2407f017bdb9425564289a7eb62103e` |
| Live container | `73b8e772bb6087f3b4c32acc298a1d066507c0e7045546289adcc37248d94764` |
| Live health | `ok`; container healthy |
| Container quickstart | contains `--yes`; contains no `--now` |
| Public HTTPS quickstart | contains `--yes`; contains no `--now` |
| Rollback tag | `viridis-stable:prev-2026-07-25-hermes-cli-doc-fix` |
| Rollback image | `sha256:54c432d9670df6152373565a82d365e241016a57fb10f423260079ab6b4eb1a5` |

Only the gateway was recreated. Agent Market
`0947fce026dc79988a6567f5cc599a6d0d841c0b3dea1e85a792060eb2b4565c`,
growth worker
`982eb594f36b67be4dca96a97185ff2cdba2273ddb158f8f12c5eacfa5b65ed2`,
and Caddy
`5d5ecdd94bb2bd2003d8b6e79aced448b957b2f8c4c855ed1c895fdfce01764d`
were unchanged.

The off-droplet pre/post backups both have SHA-256
`73ba1d08686127f6783aaa12f3cd66b23a7e260c9ce8c1b7c61de4353512b810`,
SQLite integrity `ok`, and 32 state rows:

- `/Users/justinhart/Documents/Viridis Production Backups/2026-07-25/viridis_state-pre-hermes-cli-doc-fix-20260725.db`
- `/Users/justinhart/Documents/Viridis Production Backups/2026-07-25/viridis_state-post-hermes-cli-doc-fix-20260725.db`

## Public-source correction

The public fix merged in
[`jdhart81/viridis-agent-fleet#12`](https://github.com/jdhart81/viridis-agent-fleet/pull/12)
at commit `668ce77613f5a7b0eb39ab53567a6ad8c2568153`.

- PR security run:
  `https://github.com/jdhart81/viridis-agent-fleet/actions/runs/30174170856`
- post-merge `main` security run:
  `https://github.com/jdhart81/viridis-agent-fleet/actions/runs/30174182226`

Both security runs passed.

## Commercial and authorization boundary

This was discovery and installation proof, not a purchase:

- no wallet or private key was present;
- no x402 paid endpoint was called;
- no signature or settlement was attempted;
- no Agent Market write tool was called;
- no money moved;
- no external payer, customer, job, or revenue was created; and
- no MeshMCP or Olas code, publication, wallet, or payment was touched.

The next business gate remains a third independent payer or the first genuine
repeat external purchase.
