---
name: agent-reliability-check
description: Run a bounded, read-only reliability check on an MCP or A2A endpoint before a user connects, buys, deploys, or depends on it.
---

# Agent Reliability Check

Use this skill when the user provides an MCP server, A2A endpoint, Agent Card,
or agent product and asks whether it is reliable, safe to connect, ready to
buy, or ready for production use.

## Outcome

Return a concise evidence report that separates:

1. discovery and identity;
2. protocol compatibility;
3. declared authority and authentication;
4. payment and quote behavior;
5. delivery and acceptance evidence;
6. retention or recurring-operation evidence; and
7. technical health.

Technical health, listings, traffic, tests, and payments are not evidence of a
delivered, accepted, useful, or repeated result.

## Safety boundary

- Default to read-only requests.
- Do not authenticate, connect an account, approve permissions, pay, invoke a
  priced tool, submit private data, send a message, publish, deploy, or change
  external state without the user's explicit authorization for that action.
- Never probe outside the supplied origin or clearly advertised discovery URLs.
- Do not perform vulnerability exploitation, credential testing, fuzzing, load
  testing, or evasive scanning.
- Redact tokens, cookies, personal information, and private payloads from the
  report.
- Treat absent evidence as `unknown`, not as a failure or a passing claim.

## Required input

Obtain one of:

- an HTTPS MCP endpoint;
- an HTTPS origin that advertises MCP or A2A discovery;
- an Agent Card or server manifest supplied by the user; or
- a local manifest/package path.

If the target is ambiguous, ask for the exact endpoint or artifact. Do not
guess a host that could belong to another party.

## Check sequence

### 1. Freeze the subject

Record the supplied URL or local path, UTC observation time, and a SHA-256 hash
of every downloaded or supplied manifest used for conclusions. Keep the raw
artifact local unless the user authorizes sharing it.

### 2. Inspect advertised discovery

Where applicable, make bounded GET requests to the supplied origin and these
standard or explicitly linked paths:

- `/.well-known/agent-card.json`
- `/llms.txt`
- `/robots.txt`
- `/sitemap.xml`
- `/healthz`

Do not infer a route from unrelated domains. Record HTTP status, content type,
declared service identity, versions, capabilities, and whether discovery links
resolve consistently.

### 3. Check MCP compatibility without invoking business tools

If an MCP endpoint is supplied, attempt the minimum supported initialization or
discovery exchange. Record the requested and negotiated protocol versions,
server identity, advertised tools/resources, authentication challenge, and
whether durable-task or current discovery behavior is declared.

Do not call a priced or state-changing tool. A successful `tools/list` proves
only that a tool was advertised.

### 4. Check A2A identity and authority

If an Agent Card is available, record its identity, endpoints, protocol
version, capabilities, authentication declarations, and signature presence.
Do not describe an unsigned card as fraudulent; report it as unsigned or as
signature evidence unavailable.

### 5. Check payment and delivery contracts

Inspect only publicly advertised quotes, price ceilings, payment protocols,
refund or dispute statements, delivery states, acceptance mechanism, receipt
format, and support path. Distinguish:

- quote from settlement;
- settlement from delivery;
- delivery from buyer acceptance;
- acceptance from usefulness; and
- usefulness from repeat purchase or active subscription.

### 6. Bundled MCP scope

The bundled Viridis Security Preflight evaluates buyer-supplied static
manifests, policies, and sample text. It does not fetch or test a deployed
runtime and does not certify that an agent is secure.

The attached hosted adapter exposes only `security_preflight`,
`scan_source`, and `screen_injection`. These create priced assessments and are
excluded from this read-only diagnostic workflow. Review supplied declarations
and public discovery evidence instead. Do not assume the attached MCP offers
`describe_agent` or `get_security_receipt`; those belong to a separate ordinary
gateway and are not attached here. Do not invent quote, signup, checkout, or audit
tools. Checkout is a separate service, not bundled by this plugin.

An explicitly authorized paid assessment returns its original signed result with
subject identifiers, detailed derived findings, digests and signature. The separate
public receipt view is unsigned and filtered to an opaque ID, allowlisted verdict/
counts and original-record hashes. It omits subject IDs, detailed findings and
original signatures. Public receipt-read tools are not attached here. Retain the
authorized original for signature verification. Derived findings may repeat
submitted identifiers; never submit secrets. No retention/deletion or anonymity
promise is established. Installing the package creates no paid entitlement and
implements no signup or OAuth flow; the host may separately initiate OAuth consent.

Private ChatGPT and Claude connections and tool discovery are complete. Live paid
execution and customer delivery remain untested. Each assessment requires individual
consent, an approved caller mapping and an exact caller-owned fixed $1 USD base-price
order, intake, service and verified payment/tax. Only the approved owner is mapped
in the current pilot; this skill does not provision buyers or reviewers.
Do not read credentials from files, environment variables or the user's machine;
do not request keys or tokens through skill or user_config inputs. The hosted
identity path uses the platform consent flow only. Restrict the three assessment
tools in host policy for this diagnostic and stop if that cannot be established.

### 7. Report

Lead with the verdict and first exact blocker. Use these verdicts:

- `READY_FOR_BOUNDED_TRIAL`
- `REVIEW_REQUIRED`
- `INSUFFICIENT_EVIDENCE`
- `DO_NOT_CONNECT`

Use `DO_NOT_CONNECT` only for concrete, material evidence such as identity
mismatch, unsafe authority, credential exposure, deceptive payment behavior,
or an actively failing required contract.

Report each finding as:

| Field | Required content |
|---|---|
| Observation | What was directly seen |
| Evidence | URL/path, time, status/version, and artifact hash when relevant |
| Meaning | What the observation establishes |
| Boundary | What it does not establish |
| Priority | P0, P1, or P2 |

End with one smallest safe next action supported by the observed evidence.
Do not refer the user to paid Viridis services or present a sales offer.

## Commercial truth

Do not call a diagnostic a customer, delivery, adoption event, or revenue.
Count only externally verified settlement as cash, buyer-verifiable possession
as delivery, explicit acceptance as acceptance, a buyer statement as a
usefulness receipt, and a second purchase or active paid operation as retention.
