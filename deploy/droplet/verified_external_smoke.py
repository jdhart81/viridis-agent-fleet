import json, os, urllib.request
BASE = "https://mcp.viridisconservation.com"
def call(_mount, _tool, **args):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                       "params":{"name":_tool,"arguments":args}}).encode()
    req = urllib.request.Request(f"{BASE}/{_mount}/mcp", data=body,
        headers={"content-type":"application/json",
                 "accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":verified-external-smoke"})
    raw = urllib.request.urlopen(req, timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
# Register a REAL external MCP server (EnergyAI, separate droplet) and relay.
r = call("verified","register_service", url="https://api.energyaisolution.com/mcp",
         provider="energyai", description="EnergyAI clean-energy incentives (federated)")
sid=r["data"]["service_id"]; print("registered:", sid, "dup:", r["data"]["duplicate"])
c = call("verified","call_verified", service_id=sid, tool="check_incentives",
         call_id="ext-smoke-0715-1", arguments={"zip_code":"94103"})
if c["status"]=="ok":
    rc=c["data"]["receipt"]
    print("RELAY OK — outcome:", rc["outcome"], "| elapsed", rc["elapsed_ms"],"ms",
          "| req", rc["request_hash"][:10], "resp", rc["response_hash"][:10])
    res=c["data"]["result"]
    print("downstream result keys:", list(res)[:6] if isinstance(res,dict) else type(res).__name__)
else:
    print("RELAY ERROR:", c.get("message"))
    print("receipt outcome:", c.get("receipt",{}).get("outcome"))
v=call("verified","verify_receipts", service_id=sid)["data"]
print("chain valid:", v["valid"], "| receipts:", v["receipt_count"], "| fees consistent:", v["fees_consistent"])
