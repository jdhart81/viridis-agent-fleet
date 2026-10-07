# Platform compatibility and rollout status

Updated 2026-10-06. Public source and live caller-bound service are released.
Local installation, native invocation, authenticated assessment and public
listing are different milestones; none should stand in for another.

## Verified platform matrix

| Platform | Local install | Native invocation | Authenticated useful assessment | Directory |
|---|---|---|---|---|
| Codex 0.160.0 bundled in ChatGPT.app | 0.1.2 installed in native cache, globally disabled, enabled only in scratch project | Ephemeral read-only native thread: five tools discovered, live `describe_agent` and synthetic filtered receipt passed; unrelated servers disabled | Unrun; existing caller/credential/session and explicit scope required | Not submitted, reviewed or listed |
| ChatGPT hosted | Portable package and HTTP endpoint prepared | Hosted custom connection unrun; Codex app-server evidence is not a ChatGPT chat test | Unrun; OAuth and account-resolved caller binding absent | ZIP preparation only; verified publisher/project and portal access unknown |
| Claude Code 2.1.241 | 0.1.2 installed in isolated configuration/cache and scratch local settings | Native zero-model control interface discovered the skill, all five hosted tools and a local fixture server; no native business-tool invocation | Unrun; current native auth check says logged out | Public repository marketplace is separate from Anthropic's directory |
| Claude chat/Desktop/Cowork | Remote HTTPS connector instructions prepared | Account connector installation/invocation unrun | Unrun; per-user OAuth absent; fixed-header beta is conditional | Connector and plugin submissions both required, neither submitted |

Previous local-preparation text claiming that the unsafe source is still live,
that no Codex binary exists, or that no native installation was performed is
superseded. Native tests used no model turns, purchases, live scans, customer
credits, new credentials or OAuth grants. Version 0.1.2 packaging and the live tool-title metadata update are released;
an authenticated hosted workflow is still unrun.

## Live service boundary

Endpoint: `https://mcp.viridisconservation.com/security-preflight/mcp`.
Public service version: 1.2.0. Expected tools are `describe_agent`,
`get_security_receipt`, `security_preflight`, `scan_source`, `screen_injection`.
The first two are reads; the other three persist signed assessment results.
All five live tools have truthful annotations and display titles. The initial
metadata check found missing titles; the coordinated adapter/private OSS pin/image
release added them, and the public post-cutover metadata check passed.

Direct assessments, `create_service_checkout` and `fulfill_paid_scan` require
caller auth independently of general gateway auth mode. Fixed orders bind the
verified caller and exact input/service/amount/currency/tax. Shared credits cannot
fund these direct MCP assessments. Historical orders with unknown callers need
owner review; no caller or consumed capacity is inferred. No rollback may reopen
shared-credit assessments or full public receipt records.

Public reads are unsigned filtered summaries with original-record hashes.
Original authorized signed deliveries and durable stored records remain intact.
For direct manifest calls, the exact retained intake includes `action: scan`,
`policy: {}` and `sample_inputs: []` defaults when omitted. Retain the checkout
intake and prefer fixed-order fulfillment to avoid normalization mismatch.

## Local verification

```sh
python3 -m pytest -q plugins/viridis-agent-reliability/tests/test_compatibility.py
claude plugin validate ./plugins/viridis-agent-reliability
claude plugin validate .
python3 plugins/viridis-agent-reliability/scripts/check_mcp.py
python3 plugins/viridis-agent-reliability/scripts/build_package.py --output /tmp/viridis-plugin.zip
```

The live smoke calls only `describe_agent`. Local SDK tests cover truthful
annotations/titles, input contract, filtered receipts, JSON/SSE/pagination and
contract mismatch rejection. The installed older Claude validator does not
establish all newer strict/directory checks. Portal validation and real host
workflow tests remain required.

## Making assessments usable

Native Codex/Claude Code can send an existing bearer credential and registered
actor through process-local environment-backed headers. Review-only examples
remain inactive. `examples/codex-assessments.config.toml` restricts the assessment
server to the three exact tools; `examples/claude-assessments.mcp.json` supplies
headers but needs separate exact host permission controls. Each invocation needs
the same caller's already paid session and original intake. Neither example
creates a payment or credentials. Client storage, transmission and activation
require an explicit account and scope decision.

The separate ordinary card flow fixes 100 cents USD plus applicable automatic
tax for one static scan, US50/DC, declared personal/business use and exact intake.
`/payments/mcp` exposes a broader 32-tool surface; restrict it to
`create_service_checkout` and `fulfill_paid_scan` when explicitly approved.
Existing checkout templates are not activated, and are excluded from the
submission ZIP. No real funded transaction or assessment was tested.

For **ChatGPT directory**, current guidelines prohibit digital-service sales,
transactional links and indirect checkout referrals. Existing paid-account/subscription access
is a different documented direction; one-off order eligibility remains subject
to review; do not add the $1 checkout
tools to the plugin or use the diagnostic as an upsell. A user-supplied token or
actor in chat is not a substitute for OAuth. The current fixed-order service
requires both Bearer and `X-Viridis-Agent-ID`; a future OAuth identity mapping must
resolve the verified registered caller without weakening that boundary. Approval
for an identity provider, token audience/scopes, data disclosure and service auth
changes is needed before implementation/deployment.

For **Claude hosted**, per-user OAuth is the supported general account pathway.
Static headers are beta for a limited set of organizations and send the same
credential for every member. `X-Viridis-Agent-ID` is a custom header requiring
Anthropic approval before saving. Do not assume beta availability, header approval
or a shared credential's suitability. Directory auth setup must be tested in the
actual host, not inferred from native CLI configuration.

## Submission prerequisites and approvals

Prepare source/listing copy now, but do not attest unfinished tests or privacy
practices. OpenAI needs a verified publishing identity, owning organization and
project with Apps Management Write, domain challenge, five tested positive and
three negative cases, reviewer access and a walkthrough recording. Its ZIP may
include one connected MCP; no technical app ID is fabricated.

Claude's portal is `https://claude.ai/directory/manage`: use an eligible paid
account/organization. Submit the remote MCP connector and the plugin folder from
`jdhart81/viridis-agent-fleet` separately under the same owner. A connected GitHub
account with push access is required. Prefer Scheduled check only over creating a
new push webhook. Submission entails four plugin or seven connector policy
acknowledgements plus Directory Terms; owner approval is required. The first
organization to submit the repository folder owns that listing long term.

Both need an owner-approved public privacy/retention/user-controls policy,
support contact and listing identity/assets. Authenticated reviewer credentials
must be a dedicated synthetic-only test account, privately scoped and approved;
never give a real customer or broad organization account. No such account was
created. A real payment or production test requires separate authorization.

## Current official sources

- [OpenAI package format](https://developers.openai.com/plugins/build/plugins)
- [OpenAI submission and review](https://developers.openai.com/plugins/deploy/submission)
- [OpenAI directory rules, including digital commerce](https://developers.openai.com/plugins/plugin-guidelines)
- [OpenAI OAuth](https://developers.openai.com/plugins/build/auth)
- [Claude marketplace publishing](https://code.claude.com/docs/en/plugins/publish)
- [Claude directory process](https://claude.com/docs/directory/publish)
- [Claude plugin checklist](https://claude.com/docs/plugins/pre-submission-checklist)
- [Claude connector submission](https://claude.com/docs/connectors/building/submission)
- [Claude authentication](https://claude.com/docs/connectors/building/authentication)
- [Claude static-header beta and header approval](https://claude.com/docs/connectors/custom/add-unlisted)
- [Anthropic Directory Terms](https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms)
- [Anthropic Directory Policy](https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy)
