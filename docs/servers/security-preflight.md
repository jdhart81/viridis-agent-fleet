# io.github.jdhart81/security-preflight

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/security-preflight)](https://mcptry.com/servers/io.github.jdhart81/security-preflight)

Evidence-bounded MCP manifest and tool-policy security preflight with signed receipts

| | |
|---|---|
| Registry name | `io.github.jdhart81/security-preflight` |
| Endpoint (Streamable HTTP) | `https://mcp.viridis-security.com/security-preflight/mcp` |
| Version | 1.3.1 |
| Tools | 5 |
| Source | [`security-preflight-agent/`](../../security-preflight-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-security-preflight": {
      "type": "http",
      "url": "https://mcp.viridis-security.com/security-preflight/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-security-preflight https://mcp.viridis-security.com/security-preflight/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `security_preflight`

Run a $1 static Security Preflight and return a signed receipt. Direct MCP requires the checkout caller and verified fixed-order session. The separate x402 HTTP rail retains its existing introductory quote policy. No …

*changes records; may need a caller credential (see below); $1.00 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent or server being checked. |
| `manifest` | object | yes | The server's manifest: tools, schemas, declared permissions. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `policy` | object | no | Optional. The policy to check against. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `sample_inputs` | array | no | Optional. Sample inputs to screen. |
| `session_id` | string | no | The verified checkout session id. Required for direct MCP calls. |
| `subject_profile_sha256` | string | no | Optional. SHA-256 of a subject profile, to bind into the receipt. |

### `scan_source`

$1 bounded inline VulnCanon source scan; indicators, not proven exploits. Direct MCP requires the checkout caller and verified fixed-order session. At most 64 KiB, 2000 lines, 4096 characters per line. No model calls, …

*changes records; may need a caller credential (see below); $1.00 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent or server being checked. |
| `session_id` | string | no | The verified checkout session id. Required for direct MCP calls. |
| `source` | string | yes | The source code to scan, inline. At most 64 KiB. |

### `screen_injection`

$1 batch of 1–20 text samples screened for deterministic injection markers. Direct MCP requires the checkout caller and verified fixed-order session. Maximum 64 KiB total. Heuristic indicators, not calibrated …

*changes records; may need a caller credential (see below); $1.00 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent or server being checked. |
| `session_id` | string | no | The verified checkout session id. Required for direct MCP calls. |
| `texts` | array of string | yes | One to twenty text samples, 64 KiB in total. |

### `get_security_receipt`

Read an unsigned, filtered public view; retain original delivery for signature verification.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `receipt_id` | string | yes | The receipt id from a preflight or scan. |

### `describe_agent`

Describe scope, evidence boundary, inputs, and outputs.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-16):

```json
{
  "name": "describe_agent",
  "arguments": {}
}
```

Response (shortened):

```json
{
  "name": "security-preflight-agent",
  "version": "1.2.0",
  "description": "Deterministic preflight of caller-supplied MCP manifests, tool schemas, policies, and sample inputs with signed, input-redacted receipts.",
  "capabilities": [
    "mcp-manifest-security-preflight",
    "tool-schema-analysis",
    "tool-authority-policy-check",
    "static-injection-indicator-scan",
    "signed-security-receipts",
    "persistent-public-receipts",
    "artifact-and-profile-digest-binding",
    "bounded-source-pattern-scan",
    "bounded-text-injection-screening"
  ],
  "inputs": [
    "agent_id",
    "subject_profile_sha256",
    "manifest",
    "policy",
    "sample_inputs"
  ],
  "outputs": [
    "verdict",
    "checks",
    "signed_receipt",
    "explicit_market_import_payload"
  ],
  "claim_boundary": "Covers only the buyer-supplied manifest, tool schemas, policy, and sample inputs evaluated by deterministic static checks. It does not fetch or test the deployed runtime and does not certify the agent as secure, vulnerability-free, or independently audited.",
  "receipt_protocol": "viridis-security-receipt-v1",
  "receipt_issuer_id": "viridis-security-preflight",
  "receipt_public_key_b64": "yIVh2rBsfkEcGGtdDhdd6i9gSjHUiApaXI6V9uB2VIY",
  "privacy": "Raw supplied manifests, source and text are not stored in assessment records or returned as raw artifacts. Original signed deliveries retain subject identifiers, digests, findings and scanner metadata; diagnostic messages can repeat submitted tool and policy names verbatim. Public receipt reads use an unsigned filtered summary and original-record hashes, excluding those private fields and original signatures. Retain original delivery for signature verification. Never submit secrets. This does not promise anonymity or a deletion period."
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`security-preflight-agent/`](../../security-preflight-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-16T23:45:07Z).*
