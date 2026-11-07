**Value a conservation site's ecological complexity**: eco-funding, free rail (read-only; no money movement):
```bash
curl -s https://mcp.viridisconservation.com/eco-funding/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"value_site","arguments":{"site":{
       "site_id":"my-woodlot",
       "biodiversity":{"taxonomic":{"species_observed":1650,"observations":9800},
                       "productivity":{"value":0.52},"functional":{"value":0.47},"spectral":{"value":0.45}},
       "habitat":{"patches":[{"id":"core","area_ha":7.4,"verified":true}]},
       "thermodynamics":{"npp_gC_per_m2_yr":620,"mean_temperature_K":279.6}}}}}'
```
You get back a complexity score K (complexity-hectares) and a sealed receipt that anyone can re-run with `verify_receipt`. `next_steps` teach the notary, regulatory-radar and ghg-ledger edges. The intelligence-bound capacity term is labelled *conjecture*. The score is not a price. Any real funding pool needs legal review before money moves.
