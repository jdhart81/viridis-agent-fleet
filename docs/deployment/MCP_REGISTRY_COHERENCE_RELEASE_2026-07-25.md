# Official MCP Registry coherence release

**Released:** 2026-07-25

**Outcome:** 27-agent local, Registry, and live coherence passed

**Money moved:** None

## Distribution problem

The live fleet and its current manifests were coherent locally, but the
official MCP Registry had nine stale or missing latest entries:

- stale versions: Agent Escrow, Agent Arbitration, Agent Offset
  Clearinghouse, and SmartScale;
- missing latest entries: ERC-8004 Bridge, Agent Notary, Wavefunction Search,
  Verdigraph, and ViridisOS.

That meant a registry client could see an older version or no current entry
even while the corresponding MCP endpoint was live.

## Safe publication path

All nine operational `server.json` manifests passed the official Registry
validator. The owner repository then gained a manual, allowlisted GitHub OIDC
publisher:

- source commit:
  `2c3447b86bcc16c0e3483cc0052134609ff95d36`;
- Verdigraph identity correction:
  `db38332aad99b878b4f39c9116b752485f397545`;
- publisher version: `mcp-publisher` 1.7.9;
- pinned Linux archive SHA-256:
  `ab128162b0616090b47cf245afe0a23f3ef08936fdce19074f5ba0a4469281ac`;
- permissions: repository contents read and GitHub OIDC identity-token write;
- no Registry password, private key, or long-lived publication token was
  created or stored.

## Official latest entries

| Registry name | Version | Result |
|---|---:|---|
| `io.github.jdhart81/agent-escrow` | 0.1.3 | Published |
| `io.github.jdhart81/agent-arbitration` | 0.2.0 | Published |
| `io.github.jdhart81/agent-offset-clearinghouse` | 0.5.0 | Published |
| `io.github.jdhart81/agent-erc8004-bridge` | 0.1.0 | Published |
| `io.github.jdhart81/agent-notary` | 0.1.0 | Published |
| `io.github.jdhart81/wavefunction-search` | 0.1.1 | Published |
| `io.github.jdhart81/smartscale` | 0.9.4 | Published |
| `io.github.jdhart81/verdigraph` | 0.1.0 | Already canonical; mapping repaired |
| `io.github.jdhart81/viridisos` | 1.0.0 | Published |

Each entry is `active`, marked latest by the official Registry, and points to
its exact `https://mcp.viridisconservation.com/<mount>/mcp` endpoint.

## Verdigraph collision handling

The initial Verdigraph manifest used the proposed name
`io.github.jdhart81/verdigraph-brain`. The Registry correctly rejected it
because the same remote URL was already owned by the existing canonical
`io.github.jdhart81/verdigraph` entry.

The fleet coherence map and both operational manifests were corrected to the
existing identity. A second publication attempt was rejected as a duplicate
version, proving no replacement was needed. No duplicate Registry entry was
created. The final live coherence gate recognizes the already-active canonical
entry.

## Verification

- Nine GitHub copies matched the validated operational manifests byte for byte
  before publication.
- All nine GitHub copies passed the official Registry validator.
- Eight OIDC publication runs completed successfully.
- Verdigraph remained on its pre-existing canonical entry.
- Publish-contract regression: 16 passed.
- Final fleet coherence passed for all 27 agents across local manifests,
  official Registry latest versions, and live health.

## Commercial boundary

This closes a distribution-coherence defect. It does not prove a purchase,
repeat customer, independently verified Agent Market job, or new revenue.
Unsigned pipeline and Registry visibility are not revenue.
