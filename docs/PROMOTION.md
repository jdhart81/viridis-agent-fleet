# Viridis community launch assets

All claims and prices below match the live suite on 2026-07-27. Before reusing
later, verify <https://mcp.viridisconservation.com/x402/catalog>.

These are human-ready assets for relevant channels that permit project
announcements or for replies to genuine implementation questions. Do not use
them for unsolicited bulk email, DMs, duplicate posts, or automated posting
through a personal account.

## Security Preflight launch post

Viridis Security Preflight v1.1 is live: a $1 static security check for
caller-supplied MCP manifests, tool schemas, authority policies, and bounded
sample inputs.

It returns a signed, input-redacted receipt bound to the exact supplied
artifact. Optional Agent Market binding also ties the receipt to the target's
current profile digest, so a later profile change makes stale evidence
ranking-ineligible.

The boundary is intentionally narrow: it does not fetch endpoints, execute
tools, scan a repository, certify a deployed runtime, or claim an agent is
vulnerability-free.

Inspect the MCP tools and a valid unpaid x402 quote:
https://github.com/jdhart81/viridis-agent-fleet/blob/main/docs/SECURITY_PREFLIGHT_QUICKSTART.md

Live MCP:
https://mcp.viridisconservation.com/security-preflight/mcp

Official MCP Registry:
https://registry.modelcontextprotocol.io/v0/servers?search=security-preflight&limit=100

## Fleet launch post

Viridis has seven agent-native paid routes behind x402 v2 HTTP endpoints. Five
deterministic carbon and compliance agents chain measure → account → disclose
→ claim → scan. Agent Hive adds a fixed-price reviewed multi-agent solve, and
Security Preflight adds static MCP metadata and policy checks with a signed
receipt.

- quantity-takeoff ($0.50) — material takeoff to embodied-carbon inputs
- ghg-ledger ($1.00) — deterministic Scope 1, 2, and 3 inventory
- disclosure-compiler ($2.00) — CSRD / IFRS S2 draft evidence
- taxcredit-engine ($2.00) — 45Q/45V/45Y/48E/45X scenarios
- regulatory-radar ($0.25) — energy and climate requirement scan
- agent-hive-orchestrator ($5.00) — cost-bounded solve with cross-review
- security-preflight ($1.00) — static MCP artifact and policy checks

No signup or API key is required for the x402 routes. The buyer receives HTTP
402, signs an exact Base-USDC authorization, and receives the result after
settlement. Eligible routes may quote a new payer wallet's first call at $0.01;
the live unpaid quote is authoritative.

Free inspection: https://mcp.viridisconservation.com/quickstart
Live suite: https://mcp.viridisconservation.com/agents

## Registry blurb

Viridis Security Preflight is a deterministic static check of caller-supplied
MCP manifests, closed tool schemas, authority policies, and bounded sample
inputs. It returns a signed, input-redacted receipt and does not fetch or
certify the deployed runtime. x402/USDC on Base, no signup, $1 list price.

## Inbound implementation reply

Use only when a builder asks a relevant implementation question:

> Security Preflight can check the manifest, tool schemas, approval policy,
> and bounded sample text you supply. It returns a signed, input-redacted
> receipt, but it does not fetch or certify the live server. You can inspect
> the MCP tool list and a valid unpaid 402 here:
> https://github.com/jdhart81/viridis-agent-fleet/blob/main/docs/SECURITY_PREFLIGHT_QUICKSTART.md

## Awesome-x402 entry

```markdown
- [Viridis Agent Fleet](https://mcp.viridisconservation.com/agents) — Seven
  agent-native paid routes: a five-step carbon/compliance chain, reviewed Hive
  orchestration, and signed Security Preflight receipts; x402 v2 and USDC on
  Base, no signup, free quote inspection. Category: AI agents / climate,
  compliance, and security.
```
