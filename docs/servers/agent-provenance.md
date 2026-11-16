# io.github.jdhart81/agent-provenance

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/agent-provenance)](https://mcptry.com/servers/io.github.jdhart81/agent-provenance)

Genesis certificates, lineage, and cascading recalls: birth certificates + bloodlines for the agent economy. The founding cohort is provably first.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-provenance` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/provenance/mcp` |
| Version | 0.2.1 |
| Tools | 11 |
| Source | [`agent-provenance-agent/`](../../agent-provenance-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-provenance": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/provenance/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-provenance https://mcp.viridisconservation.com/provenance/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `register_genesis`

Register an agent's birth. Issues a content-addressed genesis certificate with a strictly monotone index (epoch 0 = the founding cohort). parent_id records lineage; children of recalled/quarantined parents are …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |
| `artifact_hash` | string | no | Optional. SHA-256 of the agent's code or model. |
| `parent_id` | string | no | Optional. Id of the parent agent, to record lineage. |

### `get_certificate`

Fetch an agent's genesis certificate + recall/quarantine status.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |

### `verify_certificate`

Verify a certificate: recompute its content hash and check the ledger.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `certificate` | object | yes | The genesis certificate object, unchanged. |

### `lineage`

Full ancestry and descendants of an agent, plus its generation number.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |

### `recall`

Recall an agent: flags it and quarantines every transitive descendant. Reports exactly which agents were quarantined.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | Id of the agent. |
| `reason` | string | no | Optional. A short note of why, kept on the record. |

### `list_records`

List genesis records, optionally by epoch (0 = founding cohort).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `epoch` | integer | no | Optional filter: the epoch number (0 is the founding cohort). |

### `register_artifact`

Register a content-addressed artifact in a separate provenance DAG. Parent hashes may be registered artifacts or external content roots. Idempotent on artifact_id; does not consume a genesis index.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `artifact_hash` | string | yes | SHA-256 of the artifact content, lowercase hex. |
| `artifact_id` | string | yes | Your id for the artifact; registering it again is idempotent. |
| `metadata_digest` | string | no | Optional. SHA-256 of any metadata you keep elsewhere. |
| `parent_hashes` | array | no | Optional. Hashes of the inputs it was derived from. |
| `producer_agent_id` | string | yes | Id of the agent that produced the artifact. |
| `relation` | string | no | Optional. How it relates to its parents. Default derived_from. |

### `get_artifact`

Fetch one registered artifact by artifact_id.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `artifact_id` | string | yes | Your id for the artifact; registering it again is idempotent. |

### `verify_artifact`

Recompute an artifact record hash and verify it against the DAG ledger.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `artifact` | object | yes | The artifact record object, unchanged. |

### `list_artifacts`

List artifacts, optionally filtered by producer agent.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `producer_agent_id` | string | no | Optional filter: only this producer's artifacts. |

### `describe_agent`

Describe this agent: name, version, purpose, every action it supports and the inputs each one takes. Read-only and free; call it first to learn how to use this server.

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
  "name": "agent-provenance-agent",
  "version": "0.2.0",
  "description": "Genesis certificates, lineage, and cascading recalls: birth certificates + bloodlines for the agent economy.",
  "capabilities": [
    "register_genesis",
    "get_certificate",
    "verify_certificate",
    "lineage",
    "recall",
    "list",
    "register_artifact",
    "get_artifact",
    "verify_artifact",
    "list_artifacts"
  ],
  "inputs": {
    "action": "str",
    "agent_id": "str",
    "parent_id": "str|null",
    "artifact_hash": "str",
    "certificate": "dict",
    "reason": "str",
    "epoch": "int",
    "artifact_id": "str",
    "producer_agent_id": "str",
    "parent_hashes": "list[str]",
    "relation": "str",
    "metadata_digest": "sha256 hex|empty",
    "artifact": "dict"
  },
  "outputs": {
    "status": "str (ok|error)",
    "data": "dict"
  },
  "a2a_role": "provenance"
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-provenance-agent/`](../../agent-provenance-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-16T23:45:07Z).*
