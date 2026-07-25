# x402 discovery compatibility release

**Released:** 2026-07-25

**Outcome:** Deployed and restart-verified

**Money moved:** None

## Incident and boundary

Viridis community material had already published:

`https://mcp.viridisconservation.com/.well-known/x402`

The live gateway returned HTTP 404 there even though the canonical Viridis
machine catalog was healthy at `/x402/catalog`.

`/.well-known/x402` is now a narrow compatibility alias for the existing
Viridis catalog. The route does not claim that this path or
`viridis-x402-catalog-v1` is mandated by the x402 protocol. Official Bazaar
discovery remains facilitator-based.

## Verification

Both paths execute the same handler, and regression coverage requires their
decoded JSON documents to be identical.

| Gate | Result |
|---|---:|
| Operational focused test | 8 passed |
| Public-mirror focused test | 8 passed |
| Gateway/release suite | 548 passed |
| Full isolated fleet | 1,433 passed, 0 failed, 33/33 suites |
| Local version/tool coherence | 27 agents, pass |
| Offline production snapshot compatibility | Pass |
| Candidate MCP surface | 27 mounts, 204 tools |
| Candidate restart | Pass |
| Production MCP surface | 27 mounts, 204 tools |
| Production route equality | HTTP 200 and identical JSON |

The candidate was derived from the exact healthy live image and replaced only
`deploy/gateway/viridis_mcp_gateway.py`. It ran against a copied production
database. Production state was never overwritten.

## Production and rollback proof

- Live image:
  `sha256:21f5c2a62006ca993e9d38e3ba6af8cd49d179db124c406dfb6dd7be085c7d8c`
- Live gateway container:
  `913d46f22559ab0f03ce51dadeb3fbfa89f3d15db107d0e6c351b0e5b9340eea`
- Rollback tag:
  `viridis-stable:prev-2026-07-25-x402-discovery`
- Rollback image:
  `sha256:211633ab91aa82e45f7bbf4674f2e11d9791f27509bd45b1d9c6f909505fe004`
- Persisted metering before release: sequence 633, 520 events
- Persisted metering after release: sequence 634, 520 events
- Agent Market retained:
  `0947fce026dc79988a6567f5cc599a6d0d841c0b3dea1e85a792060eb2b4565c`
- Caddy retained:
  `5d5ecdd94bb2bd2003d8b6e79aced448b957b2f8c4c855ed1c895fdfce01764d`
- Disk after release: 24 GB total, 5.7 GB used, 18 GB free, 25% used

## Recovery evidence

- Backup: `viridis_state-20260725T174810Z.db`
- SHA-256:
  `73ba1d08686127f6783aaa12f3cd66b23a7e260c9ce8c1b7c61de4353512b810`
- SQLite integrity: `ok`
- Agent-state rows: 32
- Independent off-droplet checksum and integrity verification: pass
- Scratch restore drill: pass, 32 rows

## Distribution boundary

The live registry coherence check still reports the nine pre-existing stale or
missing entries: agent-escrow, agent-arbitration,
agent-offset-clearinghouse, agent-erc8004-bridge, agent-notary,
wavefunction-search, SmartScale, Verdigraph, and ViridisOS.

No registry publication occurred. That existing distribution-maintenance lane
does not alter the deployed route compatibility fix.
