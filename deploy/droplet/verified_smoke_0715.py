import json, os, urllib.request
BASE = "https://mcp.viridisconservation.com"
def call(_mount, _tool, **args):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                       "params":{"name":_tool,"arguments":args}}).encode()
    req = urllib.request.Request(f"{BASE}/{_mount}/mcp", data=body,
        headers={"content-type":"application/json",
                 "accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":postdeploy-verify"})
    raw = urllib.request.urlopen(req, timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
r = call("verified","register_service", url=f"{BASE}/trust/mcp",
         provider="viridis-selftest", description="fleet self-verification loop")
sid = r["data"]["service_id"]; print("registered:", sid, "dup:", r["data"]["duplicate"])
c = call("verified","call_verified", service_id=sid, tool="describe_agent",
         call_id="genesis-verified-0715c")
print("relay:", c["status"], "outcome:", c["data"]["receipt"]["outcome"] if c["status"]=="ok" else c.get("message"))
if c["status"]=="ok":
    rc = c["data"]["receipt"]
    print("receipt:", rc["receipt_id"], "req", rc["request_hash"][:10], "resp", rc["response_hash"][:10], rc["elapsed_ms"], "ms")
v = call("verified","verify_receipts", service_id=sid)["data"]
print("chain:", v["valid"], "receipts:", v["receipt_count"], "fees consistent:", v["fees_consistent"], "accrued:", v["fees_accrued_minor"], "minor")
import urllib.request as u
s = u.urlopen(BASE + "/stats", timeout=15).read().decode()
print("/stats:", "OK" if "USAGE STATISTICS" in s else "MISSING", len(s), "bytes")
