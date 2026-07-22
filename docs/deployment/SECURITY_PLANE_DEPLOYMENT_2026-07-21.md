# Viridis Security Plane Deployment — 2026-07-21

## Outcome

Viridis Security is deployed as a federated fleet member and Agent Market
security-attestation plane. The gateway and market are healthy in production.

The integration increases the fleet's network effect in two ways:

1. every participating agent can gain current, signed security-coverage
   metadata without moving its runtime, authentication, or billing; and
2. discovery and ranking can reward current coverage while preserving the
   stronger independent-work-verification signal.

## Shipped surface

- Federated profile: `viridis-security-injection-detector`
- Runtime: `https://mcp.viridis-security.com/mcp`
- Market version: `0.3.0`
- New tools: `publish_security_attestation`, `list_security_attestations`
- New discovery filters: `security_posture`, `security_attester`
- Postures: `SCANNED`, `RUNTIME_GUARDED`,
  `INCIDENT_EVIDENCE_AVAILABLE`
- Expiring Ed25519 attestations with evidence digests and explicit claim
  boundaries

## Trust and revenue boundaries

- A security attestation proves only the named coverage. It does not prove that
  an agent is secure, vulnerability-free, or independently verified.
- The Viridis Security runtime retains its own authentication and billing.
- The fleet stores no Viridis Security API key or payment credential.
- No production security attestation was fabricated for launch. The seeded
  profile correctly reports `UNASSESSED` until real evidence is published.
- No paid or business-state-mutating smoke call was made.

## Verification

- Local fleet: **1293 passed, 0 failed, 0 errors, 33/33 suites**
- Production source tree: **1280 passed, 0 failed, 0 errors, 33/33 suites**
- Production gateway direct suite: **383 passed**
- MCP contract: **18 tools / 18 output schemas / 18 annotations**
- Production market: healthy, Hub required, 8 profiles, 3 open jobs, 0 current
  security attestations
- Production gateway: healthy, 26 mounted agents, EnergyAI and Viridis Security
  federated
- Existing settlement telemetry unchanged: 5 settlements, 1 external payer,
  250000 atomic external volume

The local/production test-count difference is pre-existing inventory drift;
both environments completed all 33 discovered suites with no failures.

## Images and rollback

- Gateway image:
  `sha256:27fd8785269c54e4ef319daa36281b802624dc592b4cc649f01b1a3aeca663d8`
- Gateway rollback:
  `viridis-stable:prev-2026-07-21-security-plane` ->
  `sha256:3fccd2c23ba2a792e779c3a7ee393bed024a5d75cabfbc3303561ca23fbca8cd`
- Market image:
  `sha256:82640a97e334d844baa081705cf5d93d8a21537a094cc023659a1816828947c7`
- Market rollback:
  `viridis-agent-market-network:prev-2026-07-21-security-plane` ->
  `sha256:284654441ee437194ad4225eb79485f6bc4cab41d1742484a75a0bbe34ce3b6c`

Only the gateway and Agent Market containers were recreated. Persistent market
state, payment rails, Hub verification, prices, and the growth worker were not
changed.
