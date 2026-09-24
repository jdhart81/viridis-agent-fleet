# Viridis GHG Ledger

Deterministic greenhouse-gas inventory calculations for explicit Scope 1, 2,
and 3 activity data. The serving path uses Python stdlib, `Decimal`, and one
bundled factor pack—no inference, network lookup, paid API, or guessed factor.

The v0.1.0 pack deliberately covers a focused MVP: selected US stationary and
mobile fuels, two refrigerants, US/eGRID and UK electricity, and starter Scope
3 Categories 1, 5, and 6. Anything outside the exact activity/region/year pack
returns `indeterminate` and is excluded from totals.

Every result includes gas/direct-CO2e resolution, Scope and category rollups,
location- and market-based Scope 2, an ESRS E1-shaped summary, the specific
factor sources used, an authenticated lineage block, `audit_sha256`, a notary
payload, and an integer-gram offset-clearinghouse dry-run weave.

This engine calculates supplied data; it does not provide accounting,
assurance, filing, lifecycle-analysis, legal, or regulatory advice.

## MCP

```bash
python3 adapters/mcp_server.py
python3 adapters/mcp_server.py --serve
```

Tools: `calculate_inventory`, `classify_activity`, `list_factor_packs`,
`get_factor_pack`, `verify_result`, and `describe_agent`.

Hosted route: `https://mcp.viridisconservation.com/ghg-ledger/mcp`.
Pricing: 10 free inventory calculations per UTC day, then $1.00 each through
the fleet payment-credit gate. Classification, factor reads, and verification
remain free.

## Test

```bash
python3 -m unittest discover -s tests -v
```


## Worked example (copy-paste)

One `tools/call` against the live endpoint — no auth, no signup; the first
10 state-changing calls per day are free, then $1.00/call
(Stripe Checkout for humans, or an a2a escrow via `payment_ref` for agents —
the 402 envelope carries both sets of instructions).

```bash
curl -s https://mcp.viridisconservation.com/ghg-ledger/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "calculate_inventory", "arguments": {"activities": [{"id": "grid-1", "activity_type": "purchased_electricity", "quantity": "1000", "unit": "kwh", "region": "US", "year": 2023}]}}}'
```

Real response (from this exact request; long fields truncated):

```json
{
  "status": "ok",
  "data": {
    "inventory_status": "complete_for_supplied_activities",
    "organization_id": null,
    "reporting_period": null,
    "organizational_boundary": null,
    "inputs": {
      "activities": [
        {
          "id": "grid-1",
          "activity_type": "purchased_electricity",
          "quantity": "1000",
          "unit": "kwh",
          "region": "US",
          "year": 2023
        }
      ],
      "options": {}
    },
    "input_sha256": "846519ec0948493083011432fb4176a1322542c9070d92dd8ce47930aed60a64",
    "line_items": [
      {
        "id": "grid-1",
        "status": "determinate",
        "activity_type": "purchased_electricity",
        "input": {
          "quantity": "1000",
          "unit": "kwh",
          "region": "US",
          "year": 2023
        },
        "classification": {
          "scope": "scope_2",
          "category": "purchased_electricity",
          "scope3_category": null,
          "method": "deterministic_mapping",
          "field_sources": {
            "scope": "deterministic_mapping",
            "category": "deterministic_mapping",
            "scope3_category": "not_applicable"
          }
        },
        "factor": {
          "id": "epa_egrid2023_us_total_ar6",
          "activity_type": "purchased_electricity",
          "unit": "mwh",
          "region": "US",
          "year": 2023,
          "source_id": "epa-egrid2023-ar6-faq",
          "source_ids": [
            "epa-egrid2023-ar6-faq"
          ],
          "applicability": null
        },
        "unit_conversion": {
          "group": "electricity_mwh",
          "quantity_in_factor_unit": "1",
          "factor_unit": "mwh"
        },
        "gas_breakdown": {
          "resolution": "direct_co2e_only",
          "gases": {},
          "direct_co2e": {
            "kg_co2e": "349.742",
            "gas_masses_available": false
          },
          "output_rounding": {
            "precision_kg_co2e": "0.001",
            "mode": "ROUND_HALF_UP",
            "component_allocation": "largest_remainder"
          }
        },
        "kg_co2e": "349.742",
        "scope_2": {
          "location_based_kg_co2e": "349.742",
          "market_based_kg_co2e": null,
          "market_based_status": "indeterminate_not_supplied",
          "market_based_reason": "supplier/REC/residual-mix factor was not supplied; location value is not reused"
        }
      }
    ],
    "indeterminate": [],
    "gas_breakdown_kg_co2e": {
      "direct_co2e": "349.742"
    },
    "scope_totals_kg_co2e": {
      "scope_1": "0.000",
      "scope_2_location_based": "349.742",
      "scope_2_market_based": null,
      "scope_3": "0.000"
    },
    "category_rollups_kg_co2e": {
      "scope_1": {},
      "scope_2": {
        "purchased_electricity": "349.742"
      },
      "scope_3": {
        "category_10_processing_of_sold_products": "0.000",
        "category_11_use_of_sold_products": "0.000",
        "category_12_end_of_life_treatment_of_sold_products": "0.000",
        "category_13_downstream_leased_assets": "0.000",
        "category_14_franchises": "0.000",
        "category_15_investments": "0.000",
        "category_1_purchased_goods_and_services": "0.000",
        "category_2_capital_goods": "0.000",
        "category_3_fuel_and_energy_related_activities": "0.000",
        "category_4_upstream_transportation_and_distribution": "0.000",
        "category_5_waste_generated_in_operations": "0.000",
        "category_6_business_travel": "0.000",
        "category_7_employee_commuting": "0.000",
        "category_8_upstream_leased_assets": "0.000",
        "category_9_downstream_transportation_and_distribution": "0.000"
      }
    },
    "scope_2_dual_reporting": {
      "location_based_kg_co2e": "349.742",
      "market_based_kg_co2e": null,
      "market_based_status": "indeterminate",
      "indeterminate": [
        {
          "id": "grid-1",
          "reason": "supplier/REC/residual-mix factor was not supplied; location value is not reused"
        }
      ]
    },
    "grand_total": {
      "kg_co2e": "349.742",
      "mass_g": 349742,
      "location_based_kg_co2e": "349.742",
      "market_based_kg_co2e": null,
      "determinate_line_count": 1,
      "indeterminate_line_count": 0,
      "coverage_complete": true
    },
    "esrs_e1": {
      "unit": "metric_tonnes_co2e",
      "gross_scope_1": "0.000000",
      "gross_scope_2_location_based": "0.349742",
      "gross_scope_2_market_based": null,
      "gross_scope_3": "0.000000",
      "total_location_based": "0.349742",
      "total_market_based": null,
      "shape_only_not_filing_advice": true
    },
    "factor_pack": {
      "version": "2026.07.13-v0.1.0",
      "effective_as_of": "2026-07-13",
      "sha256": "a5d65d87b44e945f24d887a8722991cea131f594b59c867d816862ef27042469",
      "gwp_set_id": "ipcc_ar6_gwp100_v0.1.0",
      "gwp_set_sha256": "39f45e76f38d687abdbec5b64eea4ea0043511a2782799c3f5f42ed10cbf18d5",
      "sources_used": [
        {
          "id": "epa-egrid2023-ar6-faq",
          "authority": "EPA eGRID2023 FAQ, question 16",
          "title": "CO2e output emission rates under alternative IPCC GWP profiles",
          "publisher": "United States Environmental Protection Agency",
          "date": "2025",
          "url": "https://www.epa.gov/egrid/frequent-questions-about-egrid"
        }
      ]
    },
    "lineage": {
      "producer": {
        "agent_id": "ghg-ledger-agent",
        "version": "0.1.0"
      },
      "input_sha256": "846519ec0948493083011432fb4176a1322542c9070d92dd8ce47930aed60a64",
      "factor_pack": {
        "version": "2026.07.13-v0.1.0",
        "sha256": "a5d65d87b44e945f24d887a8722991cea131f594b59c867d816862ef27042469",
        "regions": [
          "US"
        ],
        "years": [
          2023
        ],
        "factors": [
          {
            "id": "epa_egrid2023_us_total_ar6",
            "region": "US",
            "year": 2023
          }
        ]
      },
      "gwp_set": {
        "id": "ipcc_ar6_gwp100_v0.1.0",
        "sha256": "39f45e76f38d687abdbec5b64eea4ea0043511a2782799c3f5f42ed10cbf18d5",
        "source_id": "ipcc-ar6-wgi-ch7-table-7-15"
      },
      "source_ids_used": [
        "epa-egrid2023-ar6-faq"
      ]
    },
    "disclaimer": "Deterministic activity-data calculation only. Not assurance, legal, accounting, lifecycle-analysis, regulatory-compliance, or filing advice. Results cover only  ...",
    "audit_sha256": "590c7049ba8eed017310d1cb24f5c6fec840d61b4bea9777ba0df4d15dd389dd",
    "notary_payload": {
      "content_digest": "590c7049ba8eed017310d1cb24f5c6fec840d61b4bea9777ba0df4d15dd389dd",
      "context": "ghg-ledger:inventory:ghg-590c7049ba8eed017310d1cb",
      "digest_algorithm": "sha256"
    },
    "offset_weave": {
      "target": "agent-offset-clearinghouse-agent.buy_offset",
      "dry_run_ready": false,
      "commit_ready": false,
      "basis": "complete_inventory",
      "buy_offset_args": null,
      "net_position_args": null,
      "required_inputs": [
        "options.offset_buyer"
      ],
      "source": {
        "audit_sha256": "590c7049ba8eed017310d1cb24f5c6fec840d61b4bea9777ba0df4d15dd389dd",
        "factor_pack_sha256": "a5d65d87b44e945f24d887a8722991cea131f594b59c867d816862ef27042469",
        "mass_source": "grand_total.mass_g",
        "conversion": "kg_co2e * 1000"
      },
      "warnings": [],
      "inventory_id": "ghg-590c7049ba8eed017310d1cb"
    }
  }
}
```
