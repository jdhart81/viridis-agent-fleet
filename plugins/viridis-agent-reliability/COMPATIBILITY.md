# Compatibility and installation acceptance plan

Prepared 2026-10-06. This package is local and uninstalled. It wires a real
SecurityPreflight MCP server; a loaded skill alone is not an acceptance result.
No credentials, OAuth grants, access changes, publication or purchases were
performed during preparation.

## Scope and evidence

Endpoint: `https://mcp.viridisconservation.com/security-preflight/mcp`.
Expected tools: `describe_agent`, `get_security_receipt`, `security_preflight`,
`scan_source`, `screen_injection`. The first two are diagnostic reads; the
other three create assessments. The local adapter adds truthful read-only,
idempotency, destructive and open-world hints; the service description clarifies
original receipt metadata and filtered public summaries. These hints are advisory, not
authorization or payment enforcement. They are not deployed by this package.

The skill makes no paid-service referrals. The plugin still advertises all
five server tools. Host tool controls must keep assessments out of a read-only
diagnostic. No server-side filtering or access expansion is implied.

The reviewed live source omitted SecurityPreflight from caller authentication
and spent shared credits without a caller identity; public receipt reads exposed
full records. This local remediation adds mandatory auth for assessments,
`create_service_checkout` and `fulfill_paid_scan` even in general auth `off`
mode. New scan orders durably bind the verified caller. Direct assessment tools
accept `session_id`, route to the existing fixed-order fulfillment and bypass
shared credits. The registered caller must match the checkout creator, and
input/service/amount/tax/replay checks remain intact. Unknown historical caller
bindings are held for owner review; no legacy owner is inferred.

Public MCP/HTTP receipt reads now return unsigned filtered summaries and original
record digests, preserving full signed records in storage and authorized delivery.
This deliberately breaks clients that fetched complete public receipts or spent
shared credits through direct MCP tools. Keep original deliveries for signature
verification. Legacy `payment_ref`/`request_id` arguments do not replace a fixed
order and must not accompany a fixed-order intake. For manifest assessments the
exact intake includes `action: scan`, `policy: {}` and `sample_inputs: []` defaults
when omitted from the direct tool call. Prefer `fulfill_paid_scan` with the exact
retained intake to avoid default normalization mismatches.

The patch is not deployed. Broad installation requires coordinated public
adapter publication/private OSS pin/gateway release, owner handling for unbound
orders and client receipt-contract migration. No new credentials or OAuth flow
is added. Local tests use synthetic payment verification and inputs only.

Local checks (from the repository root, existing Python MCP SDK/pytest needed):

```sh
python3 -m pytest -q plugins/viridis-agent-reliability/tests/test_compatibility.py
claude plugin validate ./plugins/viridis-agent-reliability
```

The prepared `.agents/plugins/marketplace.json` exposes this candidate as
available locally, without installing it. After approval, from this repository
root run `codex plugin marketplace add .` in an available Codex CLI, then use the
desktop app to install the candidate from `viridis-local-preparation`. Confirm
the installed manifest's MCP mapping in a new session. Do not invent a registered
app ID if ChatGPT requires one; complete that registration only when approved.

The installed Claude Code 2.1.241 validator accepts the manifest. Official docs
say expanded MCP configuration validation requires 2.1.281 or later; the older
validator result is not that expanded check. Mock HTTP tests exercise the real
MCP SDK with JSON, SSE, pagination and contract mismatch rejection, and assert
that no assessment tool is called. A separate live SDK smoke negotiated
2025-11-25 and successfully called only `describe_agent`, anonymously.

Optional bounded live smoke (discovery plus free description, no scans):

```sh
python3 plugins/viridis-agent-reliability/scripts/check_mcp.py
```

## Client matrix and tests to execute after approval

| Client | Prepared connection | Exact acceptance test | Remaining boundary |
|---|---|---|---|
| ChatGPT | Portable `plugin.json` + `mcp.json`, Codex compatibility overlay | Register the public endpoint as a custom MCP connection; confirm five tools, call only `describe_agent`, and load the diagnostic skill in a new chat | Account registration/installation and native host test are not performed; no technical app ID is invented |
| Codex | Existing `.codex-plugin/plugin.json` + `.mcp.json`, portable equivalents | Use a local marketplace in the desktop app, install candidate, open a new session, inspect `/mcp`, and call only `describe_agent` | No Codex CLI on PATH here; package parsing and SDK access do not establish native host installation |
| Claude Code | `.claude-plugin/plugin.json` + root `.mcp.json` | Load the directory for one session with `claude --plugin-dir ./plugins/viridis-agent-reliability`; inspect `/mcp`, confirm five tools, call only `describe_agent` | Session/account setup and any model usage need approval; no plugin install or model request was made |
| Claude / Cowork / Desktop remote connector | Public HTTP endpoint | Add a custom connector for this endpoint, choose no sign-in for diagnostic reads, confirm tools and call only `describe_agent` | A Claude Code manifest does not create a Claude account connector; account setup is separate |

For every host, record client version, exact endpoint, negotiated protocol,
tool names/schemas, description response, and the absence of paid calls. Confirm
that a prompt to assess an unknown endpoint produces evidence/unknowns without
invoking the three assessment tools or referring to a paid engagement. Stop on
unexpected OAuth prompts, a changed tool contract or any priced operation.
Do not accept terms or grant new permissions as part of this test.

Before any model-driven native session, establish a client-side tool allowlist
limited to `describe_agent` and `get_security_receipt`. If the host cannot prove
that restriction, stop. Do not install/enable the unrestricted five-tool package
for general use on the strength of skill instructions or advisory annotations.
A meaningful credential-free test is receipt retrieval for an owner-approved
public receipt ID and inspection of its filtered summary. Compare returned
record hashes to an owner-provided original delivery locally, then verify the
original signature; the public view itself is unsigned and hides the subject. Description alone is discovery, not an assessment.
No receipt ID or customer record was selected during preparation.

The bounded native candidate is installed Claude Code 2.1.241, with this folder
loaded via `--plugin-dir` for one session in a scratch project. Inspect the native
MCP qualified tool names before model use. Start the actual read test in
`dontAsk` mode with only those two exact read tools pre-approved and explicit
denies for the three exact assessment tool names. Verify the effective policy;
do not use a wildcard allowing the whole server. Existing account sign-in can
be reused, without provisioning Viridis credentials or changing server security.
This still needs session-loading approval and an approved public receipt ID;
any additional model spend needs separate bounded approval. The installation
and effective native policy were not tested here.

## Ordinary $1 card pathway is separate

`/payments/mcp` currently advertises many payment/admin/escrow tools, not just
the two scanner tools. It is intentionally excluded from the plugin's activated
connections. `examples/` holds review-only client templates; the Codex server
is disabled and restricts visible tools to `create_service_checkout` and
`fulfill_paid_scan`. Claude's HTTP configuration does not itself filter tools;
review per-tool controls before activating it. Do not enable unrelated payment
tools or automatic approvals.

Both checkout and redemption need an already provisioned caller credential and
registered actor, sent as Bearer authorization plus `X-Viridis-Agent-ID`.
Installing a plugin, listing tools or paying does not provision those values.
The scan subject's `agent_id` does not register an account. No self-service
signup is implemented. Keep credentials and checkout session IDs private.

The existing ordinary flow fixes $1 USD plus applicable automatic tax, US50/DC,
actual declared personal/business use and exact scan-input binding. Its paid
verification and failure/replay tests are deterministic; no purchase or live
scan was performed here. The prepared public projection excludes private fields;
original authorized deliveries remain signed and may contain submitted names.
Existing stored/signed receipts are not edited or sanitized.

Claude's current remote connector documentation supports fixed request headers,
subject to account/organization controls. Using them would persist an existing
credential and is not authorized in this preparation. Do not use a broad shared
organization credential. OpenAI's authenticated plugin guidance expects OAuth;
the current Bearer-plus-actor flow is not a demonstrated ChatGPT authenticated
integration. A future OAuth design must resolve an authorized caller identity
and preserve existing service/payment boundaries rather than dropping the actor
check. No OAuth server, client ID, token scope or grant is fabricated here.

## Exact next approval gates

Approve production separately after reviewing the local remediation and its
explicit compatibility breaks. Required scope: mandatory caller auth and
existing fixed-order assessments at `/security-preflight/mcp`; caller binding
for `create_service_checkout`/`fulfill_paid_scan` at `/payments/mcp`; filtered
public reads at the MCP `get_security_receipt` tool and
`/security-preflight/receipts/{receipt_id}`. The SQLite migration only adds a
nullable caller column; legacy owners are not inferred. No credentials, OAuth,
price, geography, tax, x402 settlement or unrelated gateway security is changed.

Coordinate public adapter publication/private OSS pin/build with the gateway
release. Snapshot receipts/orders and the canonical Caddy static buyer page;
modify only the reviewed copy. Verify auth, exact caller/order/input/replay,
filtered reads and original signatures using synthetic staging fixtures before
public use. Hold unbound historical orders pending documented owner proof.
Shared credit balances remain stored but cannot fund direct MCP assessments;
owner reconciliation requires a separate narrow decision, with no automatic
refund, transfer or reassignment. Do not infer whether historical slots/orders
or credits have been consumed.

Rollback must keep assessments closed and public receipts filtered; reverting
to the old shared-credit/raw-receipt behavior restores the verified blockers.
Retain the caller column and original records; never restore stale order state
across new deliveries. If needed disable assessments while retaining diagnostic
reads and durable evidence, then repair locally.

Native session loading, client credential storage/actor scope, any OAuth/new
credentials, paid production transaction, model spend and directory submission
are separate approvals. A native paid test must name actor/input/rail/budget
and verify entitlement plus signed delivery. No deployment or installation was
performed during local preparation.

## Official documentation reviewed

- [OpenAI packaging](https://developers.openai.com/plugins/build/plugins): portable manifests/MCP wiring and compatibility layout; registered app mappings are separate.
- [OpenAI MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli): environment-backed headers and per-server tool controls.
- [OpenAI native testing](https://developers.openai.com/plugins/deploy/connect-chatgpt): endpoint and host testing requirements.
- [OpenAI authentication](https://developers.openai.com/plugins/build/auth): OAuth requirements for authenticated integrations.
- [Claude plugin manifest](https://code.claude.com/docs/en/plugins-reference): MCP loading and validator version boundary.
- [Claude plugin installation](https://code.claude.com/docs/en/plugins/install): temporary directory loading and account/plugin distinction.
- [Claude Code MCP](https://code.claude.com/docs/en/mcp): HTTP transport and environment-backed headers.
- [Claude remote connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp): account connector setup and fixed headers.
- [Claude permissions](https://code.claude.com/docs/en/permissions): exact MCP tool rules and `dontAsk` behavior.
