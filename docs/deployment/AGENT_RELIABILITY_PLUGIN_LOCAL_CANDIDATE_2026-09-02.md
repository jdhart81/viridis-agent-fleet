# Agent Reliability Plugin — Local Candidate Receipt

**Date:** 2026-09-02
**Classification:** `LOCAL_CANDIDATE_NOT_INSTALLED_NOT_PUBLISHED_NOT_PRODUCTION`

## Outcome

The first P0 flywheel repair is complete locally:

- created the validated `viridis-agent-reliability` Codex plugin package;
- added a bounded, read-only Agent Reliability Check skill;
- connected the package to the existing Viridis Security Preflight MCP server;
- reconciled Regulatory Radar and Neurogenesis publish versions/tool schemas;
- made Security Preflight a permanent input to offline manifest generation;
- restored the 29-surface aggregate distribution manifest; and
- kept the full Fleet regression green.

## Product boundary

The plugin's free check covers discovery, protocol compatibility, Agent Card
identity, authority, public payment and delivery contracts, and technical
health. It does not invoke priced tools or change external state without
specific authorization. It does not call a listing, payment, technical test,
or diagnostic a delivered customer outcome.

The bundled Security Preflight evaluates buyer-supplied static artifacts. It
does not fetch a runtime and does not certify that an agent is secure.

## Distribution reconciliation

| Surface | Before | Local candidate |
|---|---:|---:|
| Aggregate entries | 28 | 29 |
| Aggregate tools | 213 | 216 |
| Regulatory Radar version | 0.1.3 publish / 0.2.0 runtime source | 0.2.0 coherent |
| Regulatory Radar tools | missing `build_evidence_pack` | included |
| Neurogenesis version | 0.1.0 publish / 0.2.0 runtime source | 0.2.0 coherent |
| Neurogenesis tools | missing `record_route_outcome` | included |
| Security Preflight generator entry | absent | included, 3 tools |

A read-only production snapshot contained 28 hosted agents plus one auxiliary
Subscriptions surface and 215 tools. The local candidate has one additional
tool because `build_evidence_pack` is present locally but not yet live.

## Verification

- Plugin ingestion validation: **pass**.
- Local version/tool coherence: **pass**, zero violations.
- Distribution plus gateway regression: **598 passed**.
- Full Fleet regression: **2,194 passed, 0 failed, 0 errors, 37/37 clean**.

## External gates still closed

- The plugin was not installed into a personal or team marketplace.
- No Codex marketplace entry was created.
- No ChatGPT app ID or `.app.json` was fabricated.
- No official MCP Registry package was published.
- No Glama, Coinbase Bazaar, or other catalog was mutated.
- No production image was built or promoted.
- No payment or priced Security Preflight was invoked.
- No prospect or buyer was contacted.

## Next exact gate

Review the local plugin and distribution candidate. A later, separately
authorized release should validate the official registry packages, promote the
matching runtime, verify public readback and semantic discovery, then decide
whether to install or publish the plugin. Outreach remains a separate gate.
