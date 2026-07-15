# Your first Viridis fleet call in 30 seconds

Every fleet agent is a plain MCP streamable-http endpoint. No signup, no key:
priced agents give **10 free calls per UTC day**, the settlement rails are
free forever. One curl pattern works everywhere:

```bash
curl -s https://mcp.viridisconservation.com/<MOUNT>/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"<TOOL>","arguments":{...}}}'
```

Or point any MCP client (Claude Desktop, ChatGPT connectors, mcp-remote) at
`https://mcp.viridisconservation.com/<MOUNT>/mcp`.

## Worked examples (copy-paste)

**Scan EU regulations for your sector** — regulatory-radar, $0.25/call after free tier:
```bash
curl -s https://mcp.viridisconservation.com/regulatory-radar/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"scan_regulations",
       "arguments":{"jurisdiction":"EU","sector":"manufacturing"}}}'
```

**List supported clean-energy tax credits** — taxcredit-engine (free read; scenarios $2):
```bash
curl -s https://mcp.viridisconservation.com/taxcredit-engine/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_rule_packs","arguments":{}}}'
```

**Wrap YOUR MCP server with tamper-evident delivery receipts** — Viridis Verified, $0.02/relayed call:
```bash
curl -s https://mcp.viridisconservation.com/verified/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"register_service",
       "arguments":{"url":"https://your-server.example.com/mcp","provider":"your-org"}}}'
# then relay any call through it and get a hash-chained receipt:
#   call_verified(service_id, tool, call_id, arguments) -> result + receipt
#   verify_receipts(service_id) -> recompute the whole evidence chain
```

**Underwrite a counterparty** — surety, free quote, deterministic + recomputable:
```bash
curl -s https://mcp.viridisconservation.com/surety/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"price_bond",
       "arguments":{"coverage_minor":100000,"duration_days":30,"successful_deliveries":12}}}'
```

**Open an escrow between two agents** — rails, free forever:
```bash
curl -s https://mcp.viridisconservation.com/escrow/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Python (any agent, 8 lines)

```python
import json, urllib.request
def fleet(mount, tool, **args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": args}}).encode()
    req = urllib.request.Request(
        f"https://mcp.viridisconservation.com/{mount}/mcp", data=body,
        headers={"content-type": "application/json",
                 "accept": "application/json, text/event-stream"})
    raw = urllib.request.urlopen(req).read().decode()
    data = [l[5:] for l in raw.splitlines() if l.startswith("data:")]
    return json.loads(data[-1] if data else raw)

print(fleet("regulatory-radar", "scan_regulations", jurisdiction="EU"))
```

## When you hit the free tier

The 11th call returns a structured `payment_required` envelope (HTTP-402
idiom) with both paths inline: a Stripe checkout link for humans
(`create_payment` → pay → `redeem_payment` for instant prepaid credits) and
the x402 escrow path for agents. Nothing crashes; the envelope tells you
exactly what to do next.

## The full directory

- Fleet directory: https://mcp.viridisconservation.com/
- Live health: https://mcp.viridisconservation.com/healthz
- Usage statistics: https://mcp.viridisconservation.com/stats
- ARD catalog: https://mcp.viridisconservation.com/.well-known/ai-catalog.json
- Carbon receipts spec (x402-C): `docs/standards/X402C_CARBON_RECEIPTS.md`
