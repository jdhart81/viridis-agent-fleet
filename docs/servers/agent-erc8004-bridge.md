# io.github.jdhart81/agent-erc8004-bridge

The MCP-native bridge to ERC-8004 (on-chain agent identity/reputation/validation, EF+Google+Coinbase, 170k+ agents): resolve registrations, score feedback with decay-weighted math, bind on-chain identities to DIDs, export unsigned attestations. No keys, no chain writes.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-erc8004-bridge` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/erc8004/mcp` |
| Version | 0.2.0 |
| Tools | 10 |
| Source | [`agent-erc8004-bridge-agent/`](../../agent-erc8004-bridge-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-erc8004-bridge": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/erc8004/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-erc8004-bridge https://mcp.viridisconservation.com/erc8004/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `import_registration`

Import an ERC-8004 Identity Registry record (chain_id + ERC-721 token_id + agentURI + owner). Idempotent: re-import updates in place. Returns the canonical record with its deterministic bridge DID …

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_uri` | string | yes | The agentURI recorded on chain for this token. |
| `chain_id` | integer | yes | EVM chain id where the ERC-8004 registry lives, for example 8453 for Base. |
| `metadata` | object | no | Optional. Extra registration metadata to keep with the record. |
| `owner` | string | yes | Owner address of the token, 0x-prefixed. |
| `token_id` | integer | yes | The agent's ERC-721 token id in the Identity Registry. |

### `resolve_agent`

Resolve an imported ERC-8004 registration by bridge DID or by (chain_id, token_id).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bridge_did` | string | no | The bridge DID, did:viridis:erc8004:<chain>:<token>. Or give chain_id and token_id. |
| `chain_id` | integer | no | EVM chain id where the ERC-8004 registry lives, for example 8453 for Base. |
| `token_id` | integer | no | The agent's ERC-721 token id in the Identity Registry. |

### `import_feedback`

Import ERC-8004 Reputation Registry feedback records for an agent. Each item: {value: bool|0..1, at: ISO-8601, source?, weight?, feedback_id?}. Idempotent per feedback_id.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `chain_id` | integer | yes | EVM chain id where the ERC-8004 registry lives, for example 8453 for Base. |
| `feedback` | array of object | yes | Feedback items: {value: true/false or 0..1, at: ISO-8601, source?, weight?, feedback_id?}. |
| `token_id` | integer | yes | The agent's ERC-721 token id in the Identity Registry. |

### `score_agent`

Decay-weighted trust score in [0,1] + tier over the agent's imported ERC-8004 feedback — recent behavior outweighs old; no feedback scores a neutral 0.5 prior (no blind trust, no unfair zero).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `bridge_did` | string | no | The bridge DID, did:viridis:erc8004:<chain>:<token>. Or give chain_id and token_id. |
| `chain_id` | integer | no | EVM chain id where the ERC-8004 registry lives, for example 8453 for Base. |
| `token_id` | integer | no | The agent's ERC-721 token id in the Identity Registry. |

### `bind_identity`

Bind a fleet DID to an ERC-8004 identity. Produces an order-independent, content-addressed (unsigned) binding attestation.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `chain_id` | integer | yes | EVM chain id where the ERC-8004 registry lives, for example 8453 for Base. |
| `fleet_did` | string | yes | The fleet DID to bind, from the identity server. |
| `proof_note` | string | no | Optional. Where the binding proof can be checked. |
| `token_id` | integer | yes | The agent's ERC-721 token id in the Identity Registry. |

### `export_attestation`

Export the agent's current trust score as an UNSIGNED ERC-8004 Validation Registry-shaped payload, content-addressed and ready for YOUR OWN signer to anchor on-chain.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `chain_id` | integer | yes | EVM chain id where the ERC-8004 registry lives, for example 8453 for Base. |
| `token_id` | integer | yes | The agent's ERC-721 token id in the Identity Registry. |

### `verify_attestation`

Recompute a payload's content hash and report whether it is intact.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `payload` | object | yes | The attestation payload returned by export_attestation, unchanged. |

### `list_registrations`

List all imported ERC-8004 registrations.

*read-only; structured output*

No inputs.

### `export_validation_response`

Build UNSIGNED ERC-8004 Validation Registry validationResponse args from an Outcome Receipt (ORC v0.1): responseHash = receipt commitment, tag "orc/0.1", response 100 only if the bridge re-verifies the receipt AND your …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `receipt` | object | yes | An Outcome Receipt (ORC v0.1) object, unchanged. |
| `replay_ok` | boolean | yes | True only if you replayed the receipted work and it reproduced. |
| `request_hash` | string | yes | The validation request hash from the Validation Registry, 0x-prefixed. |
| `response_uri` | string | yes | URI where your validation response details are published. |

### `describe_agent`

Return the bridge's capabilities and input contract.

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
  "name": "agent-erc8004-bridge-agent",
  "version": "0.2.0",
  "capabilities": [
    "import_registration",
    "resolve",
    "import_feedback",
    "score",
    "bind",
    "export_attestation",
    "verify",
    "list",
    "export_validation_response"
  ],
  "inputs": {
    "action": "one of capabilities",
    "...": "per action"
  },
  "outputs": {
    "status": "ok|error",
    "data": "per action"
  },
  "a2a_role": "identity-bridge"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-erc8004-bridge-agent/`](../../agent-erc8004-bridge-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
