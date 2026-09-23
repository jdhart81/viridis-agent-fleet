import json, os, urllib.request
from production_smoke_guard import guarded_smoke_base
BASE=guarded_smoke_base()
def call(_m,_t,**args):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                     "params":{"name":_t,"arguments":args}}).encode()
    req=urllib.request.Request(f"{BASE}/{_m}/mcp",data=body,
        headers={"content-type":"application/json",
                 "accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":uw-smoke2"})
    raw=urllib.request.urlopen(req,timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
# READ-only path (ungated): list existing services, underwrite each.
svcs=call("verified","list_services")["data"]["services"]
print("registered services:",[(s["service_id"][:14],s["provider"],s["calls_ok"],s["calls_error"]) for s in svcs])
for s in sorted(svcs,key=lambda x:-x["calls_ok"]):
    q=call("payments","underwrite_service_bond",service_id=s["service_id"],
           coverage_minor=100000,duration_days=30)
    if q["status"]=="ok":
        qt=q["quote"]
        print(f"  {s['provider']:<16} calls_ok={s['calls_ok']:<3} -> {qt['decision']:<8} "
              f"premium={qt.get('premium_minor')} minor  eff={qt.get('effective_rate_bps_per_year')}bps/yr  "
              f"hash={qt['quote_hash'][:10]}")
    else:
        print("  ",s["provider"],"ERR",q.get("message"))
