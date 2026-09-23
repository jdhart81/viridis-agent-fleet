import json, os, urllib.request, time
from production_smoke_guard import guarded_smoke_base
BASE=guarded_smoke_base()
def call(_m,_t,**args):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                     "params":{"name":_t,"arguments":args}}).encode()
    req=urllib.request.Request(f"{BASE}/{_m}/mcp",data=body,
        headers={"content-type":"application/json",
                 "accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":funding-smoke"})
    raw=urllib.request.urlopen(req,timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
u=str(int(time.time())); proj="reef-"+u
p=call("offsets","register_project",project_id=proj,verification_ref="dscore:zenodo.19317982/reef",
       name="Coral Reef Restoration",location="Palau",beneficiary="Palau Conservation Society",
       registry_ref="VCS-9999")
print("project registered:",p["data"]["name"],"->",p["data"]["beneficiary"],"| dup",p["data"]["duplicate"])
call("offsets","list_credit",issuer="viridis-land-trust",project_id=proj,
     mass_g=1000000,price_minor_per_kg=1200,verification_ref="dscore:zenodo.19317982/reef")
call("offsets","buy_offset",buyer="corp-buyer-"+u,purchase_id="sale-"+u,mass_g=5000)
f=call("offsets","project_funding",project_id=proj)["data"]
print(f"funding: {proj} earned {f['gross_proceeds_minor']} minor (${f['gross_proceeds_minor']/100:.2f}) "
      f"on {f['retired_g']}g retired, owed to {f['beneficiary']}")
print("FUNDING LEDGER LIVE" if f['gross_proceeds_minor']>0 and f['registered'] else "FAIL")
