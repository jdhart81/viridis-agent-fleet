import json, os, urllib.request, math
from production_smoke_guard import guarded_smoke_base
BASE=guarded_smoke_base()
def call(_m,_t,**args):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                     "params":{"name":_t,"arguments":args}}).encode()
    req=urllib.request.Request(f"{BASE}/{_m}/mcp",data=body,
        headers={"content-type":"application/json",
                 "accept":"application/json, text/event-stream",
                 "x-viridis-internal":os.environ["VIRIDIS_INTERNAL_SECRET"]+":carbon-x402c-smoke"})
    raw=urllib.request.urlopen(req,timeout=35).read().decode()
    data=[l[5:] for l in raw.splitlines() if l.startswith("data:")]
    msg=json.loads(data[-1] if data else raw)
    return json.loads(msg["result"]["content"][0]["text"])
import time; uid=str(int(time.time()))
w=call("compute-ledger","record_work",agent_id="smoke-"+uid,entry_id="j-"+uid,
       power_w=350.0,duration_s=8.0,bit_ops=5e13,grid_intensity_g_per_kwh=380.0)
g=w["data"]["carbon_g"]; grams=math.ceil(g)
print("work:",round(g,4),"gCO2e; landauer_eff",f"{w['data']['landauer_efficiency']:.2e}")
call("offsets","list_credit",issuer="viridis-land-trust",project_id="site7",
     mass_g=1000000,price_minor_per_kg=800,verification_ref="dscore:zenodo.19317982/site7")
buy=call("offsets","buy_offset",buyer="smoke-"+uid,purchase_id="neut-"+uid,mass_g=grams)
print("retired:",buy["data"]["mass_g"],"g; cert",buy["data"]["certificate_hash"][:12])
rc=call("compute-ledger","carbon_receipt",entry_id="j-"+uid,offset_ref="neut-"+uid)["data"]["carbon"]
print("x402-C receipt: version",rc["version"],"method",rc["method"],
      "g_co2e",rc["g_co2e"],"offset_ref",rc["offset_ref"],"att",rc["attestation_hash"][:12])
vr=call("offsets","verify_retirement",purchase_id="neut-"+uid,required_g=grams)["data"]
print("C4 verify_retirement: covered",vr["covered"],"retired",vr["retired_g"],">=",grams)
print("LIVE x402-C LOOP OK" if (rc["method"]=="landauer-floor" and vr["covered"]) else "FAIL")
