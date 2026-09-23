import json, os, urllib.request
BASE = "https://mcp.viridisconservation.com"
ADMIN = os.environ["VIRIDIS_ADMIN_TOKEN"]
def call(mount, tool, **args):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                       "params":{"name":tool,"arguments":args}}).encode()
    req = urllib.request.Request(f"{BASE}/{mount}/mcp", data=body,
        headers={"content-type":"application/json",
                 "accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":postdeploy-verify"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    txt=msg["result"]["content"][0]["text"]
    return json.loads(txt)
# G2: chain valid on the biggest legacy meter
print("verify_chain mtr-000004:", call("metering","verify_chain",meter_id="mtr-000004")["data"])
# G7/G10: flag the synthetic evaluator meters
for mid in ("mtr-000011","mtr-000012","mtr-000013"):
    r = call("metering","flag_meter",meter_id=mid,is_test=True,
             admin_token=ADMIN,note="synthetic evaluator meter (docstring example values)")
    print("flag", mid, r["status"], r.get("data",{}).get("is_test"), r.get("message",""))
# G9: timeseries runs against historical data
ts = call("metering","usage_timeseries",bucket="day")["data"]
print("timeseries:", ts["bucket_count"], "day buckets;",
      sum(b["events"] for b in ts["series"]), "events after test-exclusion")
# SB9: live underwriting quote
q = call("surety","price_bond",coverage_minor=100000,duration_days=30,successful_deliveries=12)["data"]
print("price_bond quote:", q["decision"], q.get("premium_minor"), "hash", q["quote_hash"][:12])
