import json, os, urllib.request, time
from production_smoke_guard import guarded_smoke_base
BASE=guarded_smoke_base()
def call(_m,_t,**args):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":_t,"arguments":args}}).encode()
    req=urllib.request.Request(f"{BASE}/{_m}/mcp",data=body,
        headers={"content-type":"application/json","accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":verra-insured-smoke"})
    raw=urllib.request.urlopen(req,timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
u=str(int(time.time()))
# --- VERRA TRADE ---
serial=f"VCS-1477-{u}-A"
c=call("offsets","list_credit",issuer="verra-broker",project_id="andes-cloud-forest",
       mass_g=1000000,price_minor_per_kg=1200,verification_ref="dscore:zenodo.19317982/andes",
       registry="verra",vcs_project_id="VCS1477",vintage="2024",serial_number=serial,methodology="VM0007")
print("VERRA credit listed:",c["data"]["registry"],c["data"]["vcs_project_id"],"serial",c["data"]["serial_number"][-12:])
sup=call("offsets","verra_supply")["data"]
print(f"VERRA supply: {sup['count']} credits, {sup['available_g']}g available, viridis take {sup['viridis_take_bps']/100}%")
buy=call("offsets","buy_offset",buyer="corp-"+u,purchase_id="vsale-"+u,mass_g=5000)
f=buy["data"]["fills"][0]
print(f"VERRA retirement: {f['mass_g']}g referencing {f['vcs_project_id']}/{f['serial_number'][-12:]} — cross-ref on registry.verra.org")
# --- INSURED JOB (one call) ---
sid=call("verified","list_services")["data"]["services"]
best=max(sid,key=lambda x:x["calls_ok"]) if sid else None
if best and best["calls_ok"]>0:
    q=call("payments","quote_insured_job",service_id=best["service_id"],job_amount_minor=100000,coverage_minor=50000,duration_days=30)
    if q.get("insurable"):
        qt=q["quote"]
        print(f"INSURED JOB quote ({best['provider']}, {best['calls_ok']} deliveries): bond {qt['bond_premium_minor']} + escrow {qt['escrow_fee_minor']} = {qt['total_protection_cost_minor']} minor ({qt['protection_pct_of_job']}% of job), {len(q['playbook'])}-step playbook")
    else:
        print("INSURED JOB:",best['provider'],"not insurable —",q.get("reason"))
else:
    print("INSURED JOB: no provider with deliveries to quote")
print("LIVE: VERRA TRADING + INSURED-JOB PRODUCT")
