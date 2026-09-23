import json, os, urllib.request, time
from production_smoke_guard import guarded_smoke_base
BASE=guarded_smoke_base()
def call(_m,_t,**args):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":_t,"arguments":args}}).encode()
    req=urllib.request.Request(f"{BASE}/{_m}/mcp",data=body,
        headers={"content-type":"application/json","accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":verra-ret-smoke"})
    raw=urllib.request.urlopen(req,timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
u=str(int(time.time())); serial=f"VCS-1477-{u}-R"
# Viridis Conservation lists its OWN nature-based VCU as CHEAPEST so it fills
call("offsets","list_credit",issuer="viridis-conservation",project_id="andes-reforestation",
     mass_g=5000000,price_minor_per_kg=100,verification_ref="dscore:zenodo.19317982/andes",
     registry="verra",vcs_project_id="VCS1477",vintage="2024",serial_number=serial,methodology="VM0047")
call("offsets","buy_offset",buyer="acme-corp-"+u,purchase_id="ret-"+u,mass_g=2000000)  # 2 tCO2e
rec=call("offsets","verra_retirement_record",purchase_id="ret-"+u,retirement_reason="CSRD FY2026 compliance")["data"]
r=rec["records"][0]
print(f"VERRA RETIREMENT RECORD ({rec['submission_status']} via {rec['submission_channel']}):")
print(f"  {r['quantity_tco2e']} tCO2e | VCS {r['vcs_project_id']} | serial {r['serial_number'][-10:]} | {r['methodology']} | beneficiary {r['retirement_beneficiary']}")
print(f"  cross-ref: {r['public_cross_reference']}")
print(f"  reason: {r['retirement_reason']}")
print("LIVE: VERRA RETIREMENT-RECORD GENERATOR" if rec['total_quantity_tco2e']==2.0 else "CHECK")
