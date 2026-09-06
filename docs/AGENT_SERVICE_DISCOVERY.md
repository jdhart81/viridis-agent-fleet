# Find and connect to Viridis agent services

Start with [MCP Security Preflight](https://mcp.viridis-security.com/security-preflight)
when you need static checks of an MCP manifest, tool schemas, authority policy,
or sample text. The service evaluates supplied inputs and returns a signed,
input-redacted assessment. It does not fetch or certify a deployed runtime.

| Security Preflight discovery path | Entry point |
|---|---|
| Product | [Scope, price, and integration](https://mcp.viridis-security.com/security-preflight) |
| Integration guide | [Quickstart](https://mcp.viridis-security.com/security-preflight/quickstart) |
| Machine contract | [Service metadata, input schema, and example](https://mcp.viridis-security.com/security-preflight/service.json) |
| HTTP schema | [OpenAPI](https://mcp.viridis-security.com/security-preflight/openapi.json) |
| Machine-readable guide | [llms.txt](https://mcp.viridis-security.com/llms.txt) |
| MCP Registry | `io.github.jdhart81/security-preflight` |

## Connect a client

For clients supporting Streamable HTTP:

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

The [quickstart](SECURITY_PREFLIGHT_QUICKSTART.md) includes a valid manifest and
an unpaid HTTP 402 quote inspection. The [change-check recipe](SECURITY_PREFLIGHT_CHANGE_CHECK.md)
connects a purchased assessment to the buyer's own release events. Unchanged
inputs can reuse a current assessment; another purchase requires a fresh quote
and the buyer's authorization. The free helper never signs or pays.

## Domain and protocol boundaries

The Security product pages and canonical front door belong to the existing
Viridis Security DigitalOcean deployment. The front door uses the shared
fleet assessment and settlement backend. Its x402 v2 quotes bind the exact
Security-origin resource URL, including on the signed retry; signed payloads
are never rewritten to change their resource. Existing conservation-origin
clients retain their original quote binding.

The existing Security `/mcp` endpoint remains Injection Detector. Security
Preflight uses `/security-preflight/mcp`. Its pay-per-call x402 terms are
separate from the existing Injection Detector API-key plans.

The [broader fleet catalog](https://mcp.viridisconservation.com/x402/catalog),
[fleet A2A card](https://mcp.viridisconservation.com/.well-known/agent-card.json),
and [fleet adoption contract](https://mcp.viridisconservation.com/.well-known/agent-adoption.json)
remain at their established addresses. They are separate discovery surfaces.
Do not assume an HTML fallback at a well-known path is a machine contract.

Registry metadata revision 1.2.1 changes the advertised remote URL. The
assessment scanner remains 1.2.0, so this address correction does not itself
invalidate an otherwise current baseline assessment.

## Indexing and source scope

Coinbase's [seller guide](https://docs.cdp.coinbase.com/x402/seller/get-discovered)
describes successful settlement as the trigger for Bazaar indexing. A valid
unpaid quote or a passing public validation does not establish indexing,
buyer adoption, or revenue. Use the service contract's public example when
checking a quote: missing required inputs correctly return HTTP 400.

The [Security-origin integration patch](deployment/patches/security-origin-3201fb43.patch)
targets the complete private fleet tree at production base `3201fb43`, using
its `deploy/gateway` paths. Add the published `gateway/preflight_origin.py`
at that same runtime path. The older public gateway reference is not the
complete private runtime. The new public pages are in
[`deploy/security-frontdoor/landing`](../deploy/security-frontdoor/landing).

The aggregate bridge is a separate integration with 29 route groups and 216
tool declarations, including auxiliary subscriptions. Hosted-agent counts,
bundled declarations, directory rebuilds, and successful live calls are
separate observations. External directory recrawls and Search Console
performance are not implied by a source release.
