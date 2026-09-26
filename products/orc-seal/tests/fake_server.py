"""Minimal line-delimited JSON-RPC server for proxy tests (no MCP SDK needed)."""
import json
import sys

for line in sys.stdin:
    raw = line
    try:
        msg = json.loads(line)
    except Exception:
        sys.stdout.write("not json from server\n"); sys.stdout.flush(); continue
    if "id" not in msg:
        continue
    m = msg.get("method")
    if m == "tools/call":
        name = msg["params"]["name"]
        if name == "fail":
            out = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": "boom"}}
        elif name == "iserror":
            out = {"jsonrpc": "2.0", "id": msg["id"],
                   "result": {"content": [{"type": "text", "text": "bad"}], "isError": True}}
        else:
            a = msg["params"].get("arguments", {})
            out = {"jsonrpc": "2.0", "id": msg["id"],
                   "result": {"content": [{"type": "text", "text": str(a.get("x", 0) * 2)}],
                              "structuredContent": {"value": a.get("x", 0) * 2, "ratio": 0.1}}}
    else:
        out = {"jsonrpc": "2.0", "id": msg["id"], "result": {"echo": m}}
    sys.stdout.write(json.dumps(out) + "\n"); sys.stdout.flush()
