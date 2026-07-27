# Security Preflight v1.1 trust-binding release — 2026-07-27

## Outcome

Viridis Security Preflight v1.1.0 is live at:

- MCP: `https://mcp.viridisconservation.com/security-preflight/mcp`
- paid HTTP: `https://mcp.viridisconservation.com/x402/security-preflight/security_preflight`

The list price remains $1.00 with zero free calls. This release does not add a
new payment rail or change the one-time fleet introductory-price policy.

The release closes two trust gaps in v1.0:

1. signed public receipts now persist in a dedicated SQLite store across
   process and container restarts;
2. each receipt binds the exact supplied manifest/policy artifact, and an
   explicitly Market-eligible receipt also binds the target's current Agent
   Market profile SHA-256.

Raw manifests, policies, and sample inputs are not stored. The scanner still
does not fetch endpoints, execute tools, test the deployed runtime, certify a
target secure, or represent common-control evidence as independent assessment.

## Market contract

Agent Market v0.8.1 preserves legacy receipt history while enforcing a stricter
contract for Security Preflight v1.1 and later:

- one valid `artifact-sha256:<digest>` binding is required;
- one valid `profile-sha256:<digest>` binding is required for import;
- that profile digest must match the target's current signed Market profile;
- a later profile change makes the old evidence ranking-ineligible without
  deleting its audit record;
- findings and scanner errors receive zero discovery-ranking credit;
- warnings and narrow scope reduce credit;
- common-control and self evidence rank below current third-party evidence.

This is evidence-weighted discovery, not a vulnerability-free or independent
verification claim.

## Verification

| Gate | Result |
|---|---|
| Security Preflight focused tests | 11 passed, 1 public production-compatibility skip |
| Current fleet runner | 1,846 passed, 0 failed, 35/35 suites |
| Agent Market focused suite | 55 passed |
| Copied-state gateway candidate | healthy, zero mount errors, v1.1.0 |
| Copied-state Market candidate | healthy, v0.8.1 |
| Receipt durability | candidate-only receipt recovered after container recreation |
| Input boundary | malformed request returned HTTP 400 before payment |
| Payment boundary | valid unpaid request returned HTTP 402 |
| Live MCP initialize | HTTP 200 |
| Live receipt database | integrity `ok`, zero rows after deployment |

The durability smoke used only a fake candidate agent in a candidate-only
volume. It did not call the paid endpoint and was never imported into Agent
Market. Candidate containers and volumes were removed after verification.

## Production and rollback

Promoted images:

- gateway:
  `sha256:9dc219f22d78e8a3e2e199a62c90143468536b248b90c91f5c31a0531d5c717c`
- Agent Market:
  `sha256:f7d7e7e0b338912a3f5fbb35184db1562bf0c4c7554bf0e3ac034058a5c95fce`

Rollback tags:

- `viridis-stable:pre-security-v11-20260727T205829Z` ->
  `sha256:b26fae03e0c5184a246f6ade3c45b0a535e79901852915304cf5ef5ac6fbe25b`
- `viridis-agent-market-network:pre-security-v11-20260727T205829Z` ->
  `sha256:cfbde1943466d5949290f550bbd2d8464ee09f56dfb89005057831838a4a48ec`

Transaction-consistent pre-release backups passed SQLite integrity checks and
were independently copied off the droplet:

- gateway state SHA-256:
  `e1bef026366ea82aa28f76072b6bfd4234bd1c941b121c23c8bd077138ceafc4`
- Agent Market state SHA-256:
  `a22a86b2a134f120eeaf19b1bc4800862328a930bd6a27881758d33ccfb35953`

The gateway backup contained 35 agent-state rows. The Market backup contained
12 profiles and zero imported Security receipts.

## Money truth and next gate

No paid smoke, external purchase, receipt import, outreach, or self-settlement
was created. Viridis Security Preflight external revenue remains **$0**.

The next commercial gate is one external agent builder buying a scan with its
current Market profile digest, explicitly importing the receipt, and deciding
whether the result justifies the $99 reviewed evidence-pack upgrade. Until that
happens, the product is technically live but demand and repeat purchase remain
unproven.
