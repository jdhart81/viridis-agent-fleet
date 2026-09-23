import json, os, urllib.request, time
from production_smoke_guard import guarded_smoke_base
BASE=guarded_smoke_base()
def call(_m,_t,**args):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":_t,"arguments":args}}).encode()
    req=urllib.request.Request(f"{BASE}/{_m}/mcp",data=body,
        headers={"content-type":"application/json","accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":disburse-smoke"})
    raw=urllib.request.urlopen(req,timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
u=str(int(time.time())); proj="andes-"+u
call("offsets","register_project",project_id=proj,verification_ref="dscore:zenodo.19317982/andes",
     name="Andean Cloud Forest",location="Peru",beneficiary="Andes Conservation Trust",registry_ref="VCS-1477")
# cheapest credit so this purchase fills from our project
call("offsets","list_credit",issuer="viridis-land-trust",project_id=proj,mass_g=100000,price_minor_per_kg=100,verification_ref="dscore:zenodo.19317982/andes")
call("offsets","buy_offset",buyer="corp-"+u,purchase_id="sale-"+u,mass_g=20000)  # gross=2000 minor
s=call("offsets","disbursement_schedule",project_id=proj)["data"]
line=s["lines"][0] if s["lines"] else {}
print(f"SCHEDULE @ {s['viridis_withhold_pct']}%: {proj[:16]} owed {line.get('owed_now_minor')} -> "
      f"withhold {line.get('viridis_withhold_minor')} + payout {line.get('project_payout_minor')} to {line.get('beneficiary')}")
cert=call("offsets","certify_disbursement",batch_id="cert-"+u)["data"]
print(f"CERTIFIED batch {cert['batch_id']}: total payout {cert['total_project_payout_minor']}, "
      f"viridis withhold {cert['total_viridis_withhold_minor']}, hash {cert['certificate_hash'][:12]}")
v=call("offsets","verify_disbursement")["data"]
print(f"VERIFY chain: valid={v['valid']} batches={v['batches']} conserved={v['conserved']}")
print("CERTIFIED DISBURSEMENT LIVE" if cert['certificate_hash'] and v['valid'] and v['conserved'] else "FAIL")
