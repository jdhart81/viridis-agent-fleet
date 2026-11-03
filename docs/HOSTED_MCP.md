# Using the hosted Viridis MCP servers

Every Viridis server is a remote MCP server (Streamable HTTP) at
`https://mcp.viridisconservation.com/<server>/mcp`; Security Preflight is at
`https://mcp.viridis-security.com/security-preflight/mcp`. Connecting, listing
tools and calling free tools need **no account, API key or OAuth**.

## Connect a client

Replace `<server>` with the server path (for example `regulatory-radar` or
`ghg-ledger`).

**Claude (claude.ai or Claude Desktop):** Settings → Connectors → Add custom
connector → paste `https://mcp.viridisconservation.com/<server>/mcp`.

**Claude Code:**

```sh
claude mcp add --transport http viridis-<server> https://mcp.viridisconservation.com/<server>/mcp
```

**ChatGPT:** Settings → Apps & Connectors → Advanced → Developer mode, then add
a connector with the server URL and **No authentication**.

**VS Code** (`.vscode/mcp.json`):

```json
{"servers": {"viridis-<server>": {"type": "http", "url": "https://mcp.viridisconservation.com/<server>/mcp"}}}
```

**APIs:** the Claude API MCP connector, the OpenAI Responses API (`"type": "mcp"`)
and the xAI Grok API (`"type": "mcp"`) all accept the same URL with no
authorization header.

**Any client that only speaks stdio:**

```json
{"mcpServers": {"viridis-<server>": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.viridisconservation.com/<server>/mcp"]}}}
```

## What is free and what is paid

- Read-only tools (descriptions, factor tables, verification, receipts) are free.
- Paid tools include **10 free calls per caller per UTC day** over MCP. After
  that the tool returns `payment_required` with the exact price and the ways
  to pay. Nothing is ever charged without a separate, explicit payment.
- Ways to pay, all initiated by a person or a wallet the buyer controls:
  - **Card:** a person opens a Stripe Checkout link (prepaid credits, or a
    monthly seat at <https://mcp.viridisconservation.com/seats>, from
    $19/month for 200 calls).
  - **x402 (USDC on Base):** each paid tool has an HTTP route under
    `/x402/<server>/<tool>`; an unpaid request returns HTTP 402 with the
    quote, and the buyer's own x402 client signs and retries.
- No Viridis tool moves money or signs payments on its own.

## How the hosted service relates to this repo

- **Open source here (Apache-2.0):** each server's logic, MCP adapter and
  tests, in its `*-agent/` folder. Self-hosting gives the same results for the
  same inputs.
- **Operated by Viridis, not in this repo:** the gateway that hosts the
  servers (payments and settlement, signing keys, receipt and usage storage,
  rate limits, operations).
- **Publisher:** the hosted service is operated by ViridisNorth LLC; the
  "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart (GitHub
  `jdhart81`). Contact: <justin@viridisconservation.com>.
- **Privacy:** see <https://mcp.viridisconservation.com/privacy>. Never send
  secrets, credentials or personal data you are not authorized to share.
