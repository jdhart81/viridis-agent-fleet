import json, os, urllib.request, time
from production_smoke_guard import guarded_smoke_base
BASE=guarded_smoke_base()
def call(_m,_t,**args):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":_t,"arguments":args}}).encode()
    req=urllib.request.Request(f"{BASE}/{_m}/mcp",data=body,
        headers={"content-type":"application/json","accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":funding-smoke2"})
    raw=urllib.request.urlopen(req,timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
u=str(int(time.time())); proj="reef2-"+u
call("offsets","register_project",project_id=proj,verification_ref="dscore:reef2",name="Reef2",beneficiary="Palau CS")
# list the CHEAPEST credit on the book so THIS purchase fills from our project
call("offsets","list_credit",issuer="viridis-land-trust",project_id=proj,mass_g=100000,price_minor_per_kg=100,verification_ref="dscore:reef2")
call("offsets","buy_offset",buyer="corp-"+u,purchase_id="sale2-"+u,mass_g=5000)
f=call("offsets","project_funding",project_id=proj)["data"]
print(f"TARGETED: {proj} earned {f['gross_proceeds_minor']} minor on {f['retired_g']}g, owed to {f['beneficiary']}, registered={f['registered']}")
allf=call("offsets","project_funding")["data"]
print(f"ALL PROJECTS: {allf['count']} projects, total owed ${allf['total_owed_to_projects_minor']/100:.2f}")
for p in sorted(allf["projects"],key=lambda x:-x["gross_proceeds_minor"])[:4]:
    print(f"  {p['project_id'][:24]:<24} {p['retired_g']:>8}g  ${p['gross_proceeds_minor']/100:>8.2f}  {'✓reg' if p['registered'] else ''}")
print("FUNDING LEDGER LIVE" if f['gross_proceeds_minor']==500 and f['retired_g']==5000 else "CHECK")
