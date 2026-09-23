import json, os, urllib.request
from production_smoke_guard import guarded_smoke_base
BASE=guarded_smoke_base()
def call(_m, _t, **args):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                     "params":{"name":_t,"arguments":args}}).encode()
    req=urllib.request.Request(f"{BASE}/{_m}/mcp", data=body,
        headers={"content-type":"application/json",
                 "accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":underwriting-smoke"})
    raw=urllib.request.urlopen(req,timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
# Register EnergyAI (external, real) + build a delivery record.
sid=call("verified","register_service",url="https://api.energyaisolution.com/mcp",
         provider="energyai")["data"]["service_id"]
for i in range(5):
    call("verified","call_verified",service_id=sid,tool="check_incentives",
         call_id=f"uw-hist-{i}",arguments={"zip_code":"94103"})
stats=call("verified","service_stats",service_id=sid)["data"]
print("service:",sid,"| calls_ok:",stats["calls_ok"],"| calls_error:",stats["calls_error"])
# Underwrite a $1,000 bond for 30 days off that record.
q=call("payments","underwrite_service_bond",service_id=sid,coverage_minor=100000,duration_days=30)
if q["status"]=="ok":
    qt=q["quote"]
    print("UNDERWRITE OK — decision:",qt["decision"],
          "| premium_minor:",qt.get("premium_minor"),
          "| eff_rate_bps/yr:",qt.get("effective_rate_bps_per_year"),
          "| hash:",qt["quote_hash"][:12])
    print("inputs disclosed:",q["underwriting_inputs"])
else:
    print("ERR:",q.get("message"))
# Contrast: a brand-new provider (no history) should price higher / unknown.
fresh=call("verified","register_service",url="https://api.energyaisolution.com/mcp",
           provider="fresh-provider")["data"]["service_id"]
qf=call("payments","underwrite_service_bond",service_id=fresh,coverage_minor=100000,duration_days=30)["quote"]
print("fresh provider (0 deliveries): decision",qf["decision"],"premium",qf.get("premium_minor"),"mult_ppm",qf.get("multiplier_ppm"))
