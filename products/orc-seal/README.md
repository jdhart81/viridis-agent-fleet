# orc-seal

**Every MCP tool result gets a receipt a stranger can verify.** Put `orc-seal` in front of any MCP server, in any language, with no code changes. Each successful `tools/call` result carries an [Outcome Receipt (ORC v0.1)](https://github.com/jdhart81/viridis-agent-fleet/blob/main/docs/standards/OUTCOME_RECEIPT_v0.1.md) under `result._meta["com.viridisconservation/orc"]`.

Identity standards say who an agent is. Payment rails say what was paid. A receipt says **what was actually delivered**, and anyone can check it.

## Use it (one line)
In your MCP client config, prefix the server command:
```json
{ "command": "orc-seal",
  "args": ["--issuer", "did:web:yourdomain.com", "--", "npx", "-y", "@you/your-mcp-server"] }
```
Install: `pip install orc-seal` (stdlib only, Python ≥ 3.10).

No Python? The [Node port](../orc-seal-js) takes the same flags and makes interchangeable receipts: `npx -y orc-seal --issuer did:web:yourdomain.com -- <server command>`.

## Levels
| Level | What it proves | How you get it |
|---|---|---|
| **INTACT** (L1) | The result was not altered after sealing | Default. Nothing leaves your machine. |
| **ISSUED** (L2) | A public registry recorded this exact seal, with a timestamp | Set `ORC_SEAL_API_KEY`. Free tier: 1,000 receipts/month. |

The registry only ever sees the commitment, digest, salt, profile, tool name, issuer and time. **Your outputs and tool arguments never leave the process.** Arguments are not in the receipt either; only their SHA-256 is.

## Verify
- In a browser: open the receipt's `verify.page` link (runs locally in the page).
- CLI: `orc-seal verify receipt.json`
- Python: `from orc_seal import verify`

## Show it
Add this badge to your server's README so users know its results come with receipts:
```markdown
[![ORC sealed](https://img.shields.io/badge/ORC-sealed-2e7d32)](https://github.com/jdhart81/viridis-agent-fleet/blob/main/docs/standards/OUTCOME_RECEIPT_v0.1.md)
```

## Python decorator (optional)
```python
from orc_seal import Sealer, sealed
s = Sealer({"id": "did:web:yourdomain.com"})
@sealed(s)
def quote(kwh: int) -> dict: ...
quote(1000)  # -> {"result": {...}, "orc": {...receipt...}}
```

## Guarantees (tested)
M1 result never changed · M2 every receipt verifies · M3 arguments and outputs never sent · M4 registry failures fail open · M5 deterministic float handling · M6 errors are not sealed · M7 oversized results pass through unsealed · P1 non-tool traffic is byte-identical.

## Get a registry key
Email hartjustin6@gmail.com with your issuer id. Design partners get the free tier and help shape ORC v0.2.

Apache-2.0 · Viridis LLC
