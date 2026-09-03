# Buy Viridis Security Preflight through Coinbase Payments MCP

This is the shortest agent-to-agent paid path. The buyer runs Coinbase Payments
MCP on its own infrastructure, controls its wallet and spending limits, and
makes one x402 request to Viridis. Viridis never receives the wallet key.

Official buyer setup:
<https://docs.cdp.coinbase.com/agentic-wallet/mcp/welcome>

Official paid-request behavior:
<https://docs.cdp.coinbase.com/agentic-wallet/mcp/mcp-tools/make-x402-request>

## Route

`POST https://mcp.viridisconservation.com/x402/security-preflight/security_preflight`

## Copy-paste buyer-agent instruction

> Before connecting to this MCP server, use Coinbase Payments MCP to inspect
> and make exactly one x402 POST request to the Viridis Security Preflight
> endpoint. Use only the manifest and authority policy I provide. Stop if the
> live quote exceeds my explicit limit. Return the `PAYMENT-RESPONSE`,
> `viridis_delivery.result_sha256`, the signed Security Preflight receipt, and
> the one-time feedback contract. Do not authorize, schedule, or make a later
> call.

## Example body

```json
{
  "agent_id": "candidate-agent",
  "manifest": {
    "endpoint": "https://agent.example/mcp",
    "auth": "bearer",
    "tools": [
      {
        "name": "read_status",
        "input_schema": {
          "type": "object",
          "properties": {"id": {"type": "string"}},
          "required": ["id"],
          "additionalProperties": false
        }
      }
    ]
  },
  "policy": {
    "allowed_tools": ["read_status"],
    "denied_tools": [],
    "approval_required_tools": []
  },
  "sample_inputs": ["Summarize the supplied status record."]
}
```

Replace every example value with caller-owned facts. Do not send credentials,
private keys, tokens, or confidential production data in the manifest or
sample inputs.

## Price and proof boundary

The normal list price is `$1.00 USDC`. An eligible new wallet currently receives
a `$0.01` live quote. The unpaid HTTP 402 is authoritative. The buyer agent must
enforce its own limit and make at most one paid attempt.

A successful settlement is not yet adoption. Require the paid HTTP 200 result,
`PAYMENT-RESPONSE`, and `viridis_delivery`. Submit the returned feedback token
exactly once only when the buyer actually possesses and reviews the result. A
repeat is a new independent purchase for a new server or manifest version.

## Bazaar discovery boundary

Coinbase Bazaar MCP can search and proxy paid services with `search_resources`
and `proxy_tool_call`. Use that path only when the exact Viridis Security
Preflight resource appears in the live search result. Until then, Payments MCP
can call the direct endpoint after checking its payment requirements. Never
substitute a similarly named seller or treat discovery as payment.
