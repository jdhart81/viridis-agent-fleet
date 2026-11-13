"""A minimal MCP server over stdio (newline-delimited JSON-RPC), stdlib only.
One tool, `quote`, returns a deterministic price for an amount of energy."""
import json
import sys

TOOLS = [{"name": "quote", "description": "Price for kWh at a flat rate.",
          "inputSchema": {"type": "object", "properties": {"kwh": {"type": "integer"}},
                          "required": ["kwh"]}}]

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        continue                                  # notification
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "sample-quote", "version": "0.0.1"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        kwh = int(msg["params"]["arguments"]["kwh"])
        payload = {"kwh": kwh, "price_usd": round(kwh * 0.12, 2)}
        result = {"content": [{"type": "text", "text": json.dumps(payload)}],
                  "structuredContent": payload, "isError": False}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": mid,
                          "error": {"code": -32601, "message": "unknown method"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}), flush=True)
