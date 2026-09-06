# Find and connect to Viridis agent services

Start with [MCP Security Preflight](https://mcp.viridisconservation.com/security-preflight)
when you need static checks of an MCP manifest, tool schemas, authority policy,
or sample text. The service evaluates supplied inputs and returns a signed,
input-redacted assessment. It does not fetch or certify a deployed runtime.

| Discovery path | Entry point |
|---|---|
| Service page | [Scope, price, and integration](https://mcp.viridisconservation.com/security-preflight) |
| Machine-readable guide | [llms.txt](https://mcp.viridisconservation.com/llms.txt) |
| Paid HTTP services | [x402 catalog](https://mcp.viridisconservation.com/x402/catalog) |
| A2A-compatible clients | [Agent Card](https://mcp.viridisconservation.com/.well-known/agent-card.json) |
| Adoption and repeat workflow | [Adoption contract](https://mcp.viridisconservation.com/.well-known/agent-adoption.json) |
| Skill discovery | [Skill index](https://mcp.viridisconservation.com/.well-known/skills/index.json) |
| MCP Registry | `io.github.jdhart81/security-preflight`, version `1.2.0` |

## Connect a client

For clients supporting Streamable HTTP:

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

The [quickstart](SECURITY_PREFLIGHT_QUICKSTART.md) includes a valid manifest and
an unpaid HTTP 402 quote inspection. The [change-check recipe](SECURITY_PREFLIGHT_CHANGE_CHECK.md)
connects a purchased assessment to the buyer's own release events. Unchanged
inputs can reuse a current assessment; another purchase requires a fresh quote
and the buyer's authorization. The free helper never signs or pays.

## Discovery verification on September 6, 2026

The service page, quickstart, sitemap, machine guide, and main Viridis website
links were deployed and checked after restart. The MCP Registry publication
was read back as v1.2.0. [Release evidence](deployment/AGENT_DISCOVERY_RELEASE_2026-09-06.json)
records the images, source hashes, and checks.

Coinbase's public no-payment validator accepted the existing GET service route
when supplied a public example through query parameters. The bare POST probe
returns 400 because the required agent ID and manifest are absent. Validation
reported no index entry. According to [Coinbase's seller guide](https://docs.cdp.coinbase.com/x402/seller/get-discovered),
a successful payment settlement triggers Bazaar indexing; validation itself
does not make a payment or index the service. This release claims no Bazaar
rank improvement or customer adoption.

## Source scope

The [gateway integration patch](deployment/patches/agent-discovery-d31d4a3c.patch)
targets the complete private fleet tree at production base `d31d4a3c`, using
its `deploy/gateway` paths. The three public HTML/text artifacts in `gateway/`
are copied to that directory for deployment. The older public gateway
reference is not the complete private fleet runtime. The patch was replayed
against exact base files and matched the deployed source bytes.

The bundled aggregate bridge is a separate integration. Its current manifest
has 29 route groups and 216 tool declarations, including auxiliary
subscriptions. A hosted-agent count, bundled declaration count, directory
rebuild, and successful live call are separate observations. External
directory recrawls and Search Console performance have not been verified.
