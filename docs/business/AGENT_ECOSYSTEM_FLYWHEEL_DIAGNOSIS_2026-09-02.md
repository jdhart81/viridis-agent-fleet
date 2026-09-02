# Agent Ecosystem Flywheel Diagnosis

**Date:** 2026-09-02
**Decision:** Repair discovery and delivery proof before adding agents, payment rails, or broad acquisition.

**Local implementation update, 2026-09-02:** The first repair candidate is
complete locally. Registry/tool manifests are coherent, the aggregate
distribution bundle contains 29 surfaces and 216 tools, and the repository now
contains a validated `viridis-agent-reliability` plugin with a bounded free
diagnostic skill and the existing Security Preflight MCP connection. The full
Fleet gate passes 2,194 tests across 37/37 suites. Nothing in this update was
installed, published, promoted to production, or used for outreach.

## Direct answer

The Fleet does not have a supply problem. It has a two-break flywheel:

1. **Discovery and activation are broken.** The services are live, but the external catalog contains only four older routes, those routes received zero calls and zero unique payers in the last 30 days, and two relevant semantic searches returned no Viridis result.
2. **Delivery and retention are broken.** Four historical external settlements produced no verified delivery, acceptance, usefulness, repeat purchase, subscription, or MRR record.

The ecosystem has moved past raw MCP listings. Distribution is increasingly organized around installable plugins/apps, interactive in-conversation workflows, current discovery metadata, standardized agent identity, and managed payment infrastructure. Viridis has much of the infrastructure, but it is not packaged as one buyer-complete workflow and cannot yet turn a paid event into proof and a repeat.

## Current receipts

| Layer | Current state | Commercial meaning |
|---|---:|---|
| External payers | 4 | Historical validation only |
| External settlements | 4 / **$0.280000** | Cash, but not proof of delivered value |
| Verified delivered results | 0 | Primary flywheel break |
| Historical outcomes | 4 unknown | Recovery queue, not delivery |
| Repeat buyers | 0 | No retention signal |
| Subscriptions / MRR | 0 / **$0.00** | No recurring engine |
| Seat views | 252: 10 direct, 242 unattributed | Attention only |
| Checkout starts | 0 | Activation is not occurring |
| Fleet health | 28/28 healthy; 2,194 tests; 37/37 suites | Technical supply is ready |

The operative funnel is:

`252 views -> 0 checkout starts -> 0 verified deliveries -> 0 usefulness receipts -> 0 repeats -> $0 MRR`

## What is new in the agent ecosystem

### 1. The distribution unit is becoming a plugin or app, not a server listing

OpenAI moved app discovery into a broader Plugin directory in July 2026. Plugins can combine apps, skills, and templates. The Apps SDK submission guidance favors tightly scoped products that complete a real workflow. Separately, MCP Apps became an official extension for interactive UI inside a conversation.

**Implication:** A catalog of 28 technical agents is not itself a buyer experience. Viridis needs one installable, outcome-named surface.

### 2. MCP has moved toward stateless discovery and durable tasks

The July 28 MCP specification removed the initialization/session requirement for the new transport model, added `server/discover`, introduced Tasks for longer-running work, and strengthened enterprise authorization. The live Viridis endpoint still negotiates `2025-11-25`; a `2026-07-28` `server/discover` request is rejected as unsupported.

**Implication:** Viridis is healthy on an older contract but is behind the current discovery model used by new hosts and registries.

### 3. Payment rails are becoming commodity infrastructure

AWS AgentCore Payments is generally available and supports x402 and MPP with wallets, spend controls, observability, and paid resource discovery. Stripe's Machine Payments Protocol adds microtransaction and recurring-payment patterns. Coinbase Bazaar already provides semantic discovery and paid tool proxying for x402.

**Implication:** Adding another payment protocol is not the present advantage. The scarce asset is verified useful delivery and the trust evidence surrounding it.

### 4. Agent identity and authorization are hardening

A2A 1.0 is a stable standard with signed Agent Cards and version negotiation. NIST is also advancing work on software-agent identity and authority.

**Implication:** Viridis has an A2A endpoint and Agent Card, but no observed signed Agent Card. Verifiable identity should become part of the reliability product, not just infrastructure hygiene.

### 5. Commerce is becoming cross-protocol

Google's Universal Commerce Protocol is designed to work through APIs, A2A, and MCP and interoperate with Agent Payments Protocol concepts.

**Implication:** Viridis should keep its outcome contract portable, while resisting a premature multi-rail build before one accepted paid result exists.

## What Viridis is missing, in priority order

### P0 — One buyer-complete wedge

Package a single **Agent Reliability Check** as an installable plugin/app:

- Input: an MCP or A2A endpoint.
- Free bounded result: compatibility, identity, discovery, authorization, payment, and delivery-contract findings.
- Paid next step: the existing **$995 Agent Reliability Sprint**.
- Recurring next step: **$149/month Reliability Watch**, offered only after an accepted Sprint delivery.

This is not a new agent. It is a coherent front door to the existing Fleet.

### P0 — A closed delivery contract

Every funded job needs a machine-readable chain:

`funded -> acknowledged -> work started -> result delivered -> buyer accepted -> usefulness receipt -> repeat or Watch offer`

The four unknown historical settlements should remain explicitly unknown unless evidence can reconcile them. They must not be counted as delivered.

### P0 — Real distribution coherence

Observed gaps:

- Coinbase Bazaar indexes only four older Viridis routes; all show zero calls and zero unique payers in the last 30 days.
- Relevant semantic searches returned no Viridis result.
- Published manifests drift from running versions for Offset Clearinghouse, Neurogenesis, and Subscriptions.
- Regulatory Radar and Neurogenesis publish manifests omit current tools or versions.
- There is no observed `.codex-plugin/plugin.json`, ChatGPT app submission package, or MCP Apps UI implementation.

Until these are repaired, “listed” is not equivalent to discoverable.

### P1 — Current protocol and trust signals

- Support the current MCP discovery/task contract while preserving compatibility.
- Publish a signed A2A Agent Card and verify signature readback.
- Make receipt hashes, delivery state, and authority boundaries legible to hosts and buyers.

### P2 — Additional commerce adapters

Evaluate MPP or UCP only after the first accepted paid result. x402 is already sufficient to test the business hypothesis.

## Recovery sequence

| Window | Action | Exit evidence | Authority boundary |
|---|---|---|---|
| 0–48 hours | Repair registry/manifests; specify latest-MCP compatibility; scaffold one Reliability Check plugin/app; define signed-card and delivery-receipt contracts | Local validation is coherent; installable package and test fixtures exist | Local work only; no publication or production promotion implied |
| Week 1 | Publish the approved surface and verify Plugin/MCP/Bazaar discovery for three buyer-intent queries | Viridis appears for relevant intent and 10 qualified starts are attributable | Requires separate publication/deployment authorization |
| Week 1–2 | Run a bounded 10-buyer cycle | 3 scoped conversations and 1 funded Sprint | Requires separate outreach authorization |
| Week 2–3 | Deliver the Sprint and obtain acceptance/usefulness evidence | 1 accepted paid result and 1 usefulness receipt | Buyer action cannot be fabricated |
| Week 3–4 | Offer Reliability Watch to that buyer | 1 repeat purchase or active subscription | Commercial close remains an external outcome |

## The scorecard that matters

Do not optimize raw traffic. Advance these gates in order:

1. **Discovery:** top-ten placement for three exact buyer-intent searches.
2. **Activation:** 10 attributable Reliability Check starts.
3. **Qualification:** 3 completed checks with actionable findings.
4. **Purchase:** 1 externally funded Sprint.
5. **Delivery:** 1 accepted result with immutable receipt.
6. **Retention:** 1 repeat order or active Reliability Watch.

## Stop list

- Do not add more agents.
- Do not treat views, listings, tests, deployments, self-payments, or internal credits as adoption.
- Do not add MPP/UCP merely because they are new.
- Do not begin broad outbound before the product surface and attribution path are coherent.
- Do not claim the four historical settlements were delivered without evidence.
- Do not call local readiness a published, deployed, or commercial outcome.

## Recommendation

The next build should be **one installable Reliability Check that produces a useful result before asking for money**, then converts that result into the existing Reliability Sprint. The next business milestone is not another release. It is one externally funded, accepted delivery followed by a usefulness receipt and a repeat or Watch decision.

## Primary ecosystem sources

- [OpenAI: Apps in ChatGPT and the Plugin directory](https://help.openai.com/en/articles/11487775)
- [OpenAI: Build with the Apps SDK](https://help.openai.com/en/articles/12515353-build-with-the-apps-sdk)
- [OpenAI: Developers can now submit apps to ChatGPT](https://openai.com/index/developers-can-now-submit-apps-to-chatgpt/)
- [MCP: 2026-07-28 specification release](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [MCP: August 2026 roadmap](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/)
- [MCP Apps official extension](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)
- [AWS: AgentCore Payments general availability](https://aws.amazon.com/about-aws/whats-new/2026/08/bedrock-agentcore-payments-ga/)
- [Stripe: Machine Payments Protocol](https://stripe.com/blog/machine-payments-protocol)
- [Coinbase: x402 Bazaar MCP server](https://docs.cdp.coinbase.com/api-reference/v2/rest-api/x402-facilitator/bazaar-mcp-server)
- [A2A: v1.0 production-ready standard](https://a2a-protocol.org/dev/blog/2026/03/12/a2a-protocol-ships-v10-production-ready-standard-for-agent-to-agent-communication/)
- [NIST: Identity and authority for software agents](https://www.nist.gov/news-events/news/2026/02/new-concept-paper-identity-and-authority-software-agents)
- [Google: Universal Commerce Protocol](https://developers.googleblog.com/under-the-hood-universal-commerce-protocol-ucp/)
