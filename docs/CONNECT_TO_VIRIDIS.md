# Connect to Viridis MCP services

Use Viridis-hosted tools from an MCP client supporting Streamable HTTP. Start
with the [service catalog](https://mcp.viridisconservation.com/agents?source=github) and select
one operation that fits your inputs and intended result.

## Choose a service

| Your task | Service | MCP endpoint |
|---|---|---|
| Check supplied manifests, source patterns and injection indicators | Security Preflight | `https://mcp.viridis-security.com/security-preflight/mcp` |
| Research supported energy and climate requirements | Regulatory Radar | `https://mcp.viridisconservation.com/regulatory-radar/mcp` |
| Prepare a greenhouse-gas inventory | GHG Ledger | `https://mcp.viridisconservation.com/ghg-ledger/mcp` |
| Prepare disclosure evidence and identify gaps | Disclosure Compiler | `https://mcp.viridisconservation.com/disclosure-compiler/mcp` |
| Model workload routing from your evaluations and costs | Wu Wei Router | `https://mcp.viridisconservation.com/wu-wei-router/mcp` |

Inspect the [live priced catalog](https://mcp.viridisconservation.com/x402/catalog)
for exact operations, schemas, examples, and list prices. The fresh quote governs
payment. Regulatory and disclosure tools provide bounded research and preparation
outputs. Security Preflight checks supplied material, not deployed behavior;
Wu Wei returns a plan, not executed workloads or measured savings.

## Add the endpoint to your client

Example configuration (field names can vary by client):

```json
{
  "mcpServers": {
    "viridis-security-preflight": {
      "type": "streamable-http",
      "url": "https://mcp.viridis-security.com/security-preflight/mcp"
    }
  }
}
```

Connect to the service-specific endpoint, discover its tools, and inspect their
input schemas. The catalog URL is a discovery document, not an MCP endpoint.
No repository checkout or server deployment is required for hosted access.

## Inspect terms before a paid call

MCP connectivity and payment support are separate. A connected client may still
need an x402-capable buyer integration to authorize payment in USDC on Base.
Never put wallet private keys in MCP configuration.

For a complete example, follow the
[Security Preflight buyer walkthrough](SECURITY_PREFLIGHT_BUYER_QUICKSTART.md).
It starts with an unpaid quote and uses an explicit spending cap for purchase.
The [sample report](SECURITY_PREFLIGHT_SAMPLE.md) shows the output and its limits
before you pay. Free discovery and change checks do not authorize paid execution.

Other integration paths:

- [HTTP inputs and prices](https://mcp.viridisconservation.com/x402/catalog)
- [OpenAPI contracts](https://mcp.viridisconservation.com/openapi.json)
- [A2A Agent Card](https://mcp.viridisconservation.com/.well-known/agent-card.json)
- [Agent-readable guide](https://mcp.viridisconservation.com/llms.txt)

## Build an integration

Use the public schemas, buyer scripts, and examples to connect your application
to the hosted services. Selected implementation files are also published, but
this repository does not contain the full production fleet. Consult the
[README](../README.md#hosted-service-and-public-code) for that boundary.

After a paid operation, check the returned result against your intended task.
Payment and delivery receipts record their respective events; usefulness and
repeat need must be assessed separately.

For manifest assessments, [verify signed evidence](AGENT_SECURITY_INTEGRATION.md) against your exact inputs before relying on it. The manifest verifier deliberately rejects source-scan and text-screening receipt contracts.

## Help us understand discovery

If you actually discovered Viridis through GitHub, the buyer client accepts
`--source github` on quote and paid invocations. Omit it if unknown; operator
rehearsals use `--source internal`. See [measurement and its limits](REPOSITORY_FUNNEL_MEASUREMENT.md).
