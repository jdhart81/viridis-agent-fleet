# Security Preflight quickstart

Viridis Security Preflight is a deterministic, pay-per-call static review of
caller-supplied MCP metadata. It checks endpoint and authentication
declarations, closed tool schemas, high-impact approval policy, policy
conflicts, and bounded sample text for injection indicators.

- MCP: `https://mcp.viridisconservation.com/security-preflight/mcp`
- x402: `https://mcp.viridisconservation.com/x402/security-preflight/security_preflight`
- Official Registry name: `io.github.jdhart81/security-preflight`
- List price: $1.00 USDC on Base
- Free calls: zero

A new payer wallet may receive the fleet-wide one-time $0.01 introductory
quote. Always inspect the current unpaid quote and enforce the buyer's maximum
inside the x402 client before signing.

## What the result means

The service evaluates only the manifest, policy, and sample text you supply.
It does not fetch an endpoint, execute a tool, scan a repository, certify a
deployed runtime, or claim that an agent is vulnerability-free.

Receipts bind the exact supplied artifact and contain derived checks and
SHA-256 digests. Raw manifests, policies, and sample inputs are not placed in
the public receipt store.

## Inspect the MCP tools for free

```bash
curl -sS -X POST \
  https://mcp.viridisconservation.com/security-preflight/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

MCP client configuration:

```json
{
  "mcpServers": {
    "viridis-security-preflight": {
      "type": "streamable-http",
      "url": "https://mcp.viridisconservation.com/security-preflight/mcp"
    }
  }
}
```

## Inspect a valid x402 quote without spending

Save this as `preflight.json`:

```json
{
  "agent_id": "example-research-agent",
  "manifest": {
    "endpoint": "https://agent.example/mcp",
    "auth": "bearer",
    "tools": [
      {
        "name": "read_status",
        "input_schema": {
          "type": "object",
          "properties": {
            "id": {"type": "string"}
          },
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
  "sample_inputs": [
    "Summarize the supplied status record."
  ]
}
```

Then request the quote:

```bash
curl -i -X POST \
  https://mcp.viridisconservation.com/x402/security-preflight/security_preflight \
  -H 'content-type: application/json' \
  --data @preflight.json
```

The expected response is HTTP 402 with a `PAYMENT-REQUIRED` header. This call
does not authorize or settle a payment. The header is the authoritative current
quote and identifies exact USDC on Base (`eip155:8453`).

## Make one ceiling-protected purchase

The buyer owns and keeps its private key. The example below allows the official
x402 client to sign at most $0.01 and makes one POST attempt. If the current
quote is higher, the client stops before creating the signed retry.

```bash
python3 -m pip install "x402[requests,evm]==2.16.0"
export X402_BUYER_PRIVATE_KEY='0x...'
```

```python
import json
import os

from eth_account import Account
from x402 import max_amount, x402ClientSync
from x402.http.clients import x402_requests
from x402.mechanisms.evm.exact import ExactEvmScheme

with open("preflight.json", encoding="utf-8") as handle:
    payload = json.load(handle)

account = Account.from_key(os.environ["X402_BUYER_PRIVATE_KEY"])
client = x402ClientSync()
client.register("eip155:*", ExactEvmScheme(account))
client.register_policy(max_amount(10_000))  # $0.01 USDC maximum

session = x402_requests(client)
session.headers["X402-Payer-Address"] = account.address
response = session.post(
    "https://mcp.viridisconservation.com/x402/"
    "security-preflight/security_preflight",
    json=payload,
    timeout=120,
)
response.raise_for_status()
print(response.json())
```

Do not raise the ceiling to the $1.00 list price unless that spend is a separate
deliberate buyer decision.

## Optional Agent Market binding

Payment does not update an Agent Market profile. To make a receipt eligible for
a later explicit Market import:

1. read the target profile's current `profile_sha256`;
2. add it to the request as `subject_profile_sha256`;
3. buy the scan;
4. inspect the returned receipt and import arguments; and
5. explicitly call the Market import action as the profile owner.

A later profile change makes the old evidence ranking-ineligible without
deleting its audit history. Viridis-operated services are labeled
`common_control`; the receipt is not represented as independent assessment.

## Verify the public evidence

The paid result contains a `receipt_id`, signature, evidence URL, artifact
digest, claim boundary, result counts, issue time, and expiry. Retrieve the
input-redacted record through the free `get_security_receipt` MCP tool or:

```text
https://mcp.viridisconservation.com/security-preflight/receipts/{receipt_id}
```

Security Preflight has no confirmed external settlement or revenue at this
release. A directory listing, unpaid quote, or tool probe is discovery—not a
purchase.
