# orc-seal for Node

**Every MCP tool result gets a receipt a stranger can verify.** Put `orc-seal` in front of any stdio MCP server, in any language, with no code changes. Each successful `tools/call` result carries an [Outcome Receipt (ORC v0.1)](https://github.com/jdhart81/viridis-agent-fleet/blob/main/docs/standards/OUTCOME_RECEIPT_v0.1.md) under `result._meta["com.viridisconservation/orc"]`.

This is the Node port of the [Python `orc-seal`](../orc-seal). Same flags, same receipts: a receipt sealed by either one verifies in the other, and both give the same digest for the same tool response (tested on every push).

## Use it (one line)
In your MCP client config, prefix the server command:
```json
{ "command": "npx",
  "args": ["-y", "orc-seal", "--issuer", "did:web:yourdomain.com", "--", "npx", "-y", "@you/your-mcp-server"] }
```
Node 18.17 or newer. No dependencies.

## Levels
| Level | What it proves | How you get it |
|---|---|---|
| **INTACT** (L1) | The result was not altered after sealing | Default. Nothing leaves your machine. |
| **ISSUED** (L2) | A public registry recorded this exact seal, with a timestamp | Set `ORC_SEAL_API_KEY`. Free tier: 1,000 receipts/month. |

The registry only ever sees the commitment, digest, salt, profile, tool name, issuer and time. **Your outputs and tool arguments never leave the process.** Arguments are not in the receipt either; only their SHA-256 is.

## Verify
- In a browser: open the receipt's `verify.page` link (runs locally in the page).
- CLI: `npx orc-seal verify receipt.json`
- Code: `import { verify, parse } from "orc-seal"; verify(parse(text)).label // "INTACT"`

## Show it
`npx orc-seal badge` prints a README badge for your server:

[![ORC sealed](https://img.shields.io/badge/ORC-sealed-2e7d32)](https://github.com/jdhart81/viridis-agent-fleet/blob/main/docs/standards/OUTCOME_RECEIPT_v0.1.md)

## Library
```js
import { Sealer, parse } from "orc-seal";
const s = new Sealer({ id: "did:web:yourdomain.com" }, { agent: "my-server" });
const receipt = await s.seal("quote", { kwh: 1000 }, { usd: "120.00" });
```
Parse JSON with the package's `parse()`, not `JSON.parse()`, when you seal or verify text: `JSON.parse` turns `1.0` into `1` and rounds integers above 2^53, which changes the digest.

## Guarantees (tested)
M1 result never changed · M2 every receipt verifies · M3 arguments and outputs never sent · M4 registry failures fail open (3 s timeout) · M5 deterministic float handling, matching Python's `repr` · M6 errors are not sealed · M7 oversized results pass through unsealed · P1 non-tool traffic is byte-identical · P2 order is kept · P4 the proxy exits with the server's exit code · X1 byte-identical canonical form and digests with the Python package.

The proxy rewrites only sealed `tools/call` responses. It keeps their numbers exactly as the server wrote them (Python's proxy re-encodes them).

## Limits
- Windows is not yet tested. On Windows, wrapping a `.cmd` launcher such as `npx` may need `cmd /c` in front of the server command.
- Receipts are for stdio servers. Streamable HTTP servers aren't wrapped yet.

## Get a registry key
Email hartjustin6@gmail.com with your issuer id. Design partners get the free tier and help shape ORC v0.2.

Apache-2.0 · Viridis LLC
