# io.github.jdhart81/agent-notary

Commit-reveal content notarization: sellers commit to a deliverable's hash before handover; reveals verify exactly; late reveals expire. Turns escrow delivery proofs into cryptographic receipts. Digests only — never raw content.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-notary` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/notary/mcp` |
| Version | 0.2.0 |
| Tools | 8 |
| Source | [`agent-notary-agent/`](../../agent-notary-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-notary": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/notary/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-notary https://mcp.viridisconservation.com/notary/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `commit`

Commit to a deliverable BEFORE handover. commit_hash = sha256(salt || sha256(content)) as 64 hex chars; deadline is ISO-8601; context links the escrow/job. Idempotent per (committer, nonce).

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `commit_hash` | string | yes | sha256(salt \|\| sha256(content)) as 64 lowercase hex characters. |
| `committer` | string | yes | Agent id of the party committing to the deliverable. |
| `context` | string | no | Optional. The escrow or job this commitment belongs to. |
| `deadline` | string | yes | Reveal deadline, ISO-8601. |
| `nonce` | string | yes | Your unique value for this commitment; committer plus nonce is idempotent. |

### `reveal`

Reveal the committed content's digest + salt after handover. Verifies against the commitment (one bit of drift fails); returns a delivery_proof string for escrow release. Late reveals expire the commitment.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `commitment_id` | string | yes | The commitment id returned by commit. |
| `content_digest` | string | yes | sha256 of the delivered content, 64 lowercase hex characters. |
| `salt` | string | yes | The salt used in commit_hash, revealed now. |

### `verify`

Independently verify a revealed commitment; optionally check it against the digest of content you received.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `commitment_id` | string | yes | The commitment id returned by commit. |
| `content_digest` | string | no | sha256 of the delivered content, 64 lowercase hex characters. |

### `commitment_status`

Current record for a commitment (pre-reveal, salt/digest stay hidden).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `commitment_id` | string | yes | The commitment id returned by commit. |

### `list_commitments`

List commitments, optionally filtered by state (PENDING|REVEALED|EXPIRED).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `state` | string | no | Optional filter: PENDING, REVEALED or EXPIRED. |

### `seal_outcome_receipt`

Seal an agent output as an Outcome Receipt (ORC v0.1) and register its commitment. Returns a portable receipt anyone can verify offline (L1) and against this notary's registry (L2). The notary attests integrity and time …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bindings` | object | no | Optional. Ids to bind into the receipt, for example an escrow id. |
| `excludes` | array | no | Optional. Field paths to leave out of the digest, for example timestamps. |
| `output` | object | yes | The agent output to seal, as an object. |
| `profile` | string | no | Optional. Receipt profile name. Default generic. |
| `subject` | object | no | Optional. What the output is about: {agent, tool, ...}. |

### `get_orc_commitment`

Registry lookup: is this ORC commitment sealed by this notary? Returns digest, issuer, profile, attestation and registered_at, or NotFound.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `commitment` | string | yes | The receipt commitment value, 64 hex characters. |

### `describe_agent`

Return capabilities and input contract.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "describe_agent",
  "arguments": {}
}
```

Response (shortened):

```json
{
  "name": "agent-notary-agent",
  "version": "0.2.0",
  "capabilities": [
    "commit",
    "reveal",
    "verify",
    "status",
    "list",
    "seal_orc",
    "get_commitment"
  ],
  "inputs": {
    "action": "one of capabilities",
    "...": "per action"
  },
  "outputs": {
    "status": "ok|error",
    "data": "per action"
  },
  "a2a_role": "notary"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-notary-agent/`](../../agent-notary-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
