# Viridis Quantity Takeoff

Deterministic construction material quantities from explicit geometry or
supported SmartScale/ProtoGen measurement payloads. The serving path uses
Python stdlib, `Decimal`, and a bundled, source-linked material pack—no
inference, paid API, network factor lookup, or guessed material factor.

The v0.1.0 pack covers concrete, rebar grids, wall framing, sheathing,
drywall, dimensional lumber, asphalt shingles, CMU, modular brick, a small
AISC W/HSS set, excavation, aggregate base, and paint. Unsupported assemblies,
shapes, factors, or missing dimensions are explicitly `indeterminate` and
excluded from rollups.

Each line reports geometry before waste (`net_qty`), the explicit
waste-adjusted calculation quantity (`exact_qty`), and conservative
purchase-increment rounding (`purchase_qty`). Formula, operands, conversions,
factor sources, pack SHA, rollups, `audit_sha256`, and a notary payload are
included. Waste overrides are allowed only when explicitly supplied and are
recorded alongside the replaced bundled default.

This is an auditable planning estimate, not a guaranteed material order,
professional-estimator certification, engineering design, or verification of
field conditions or drawing completeness. Confirm project-specific waste,
laps, cuts, accessories, packaging, and supplier minimums before procurement.

## MCP

```bash
python3 adapters/mcp_server.py
python3 adapters/mcp_server.py --serve
```

Tools: `calculate_takeoff`, `list_assemblies`, `get_assembly`,
`list_material_pack`, `get_material_pack`, `verify_result`, and
`describe_agent`.

Hosted route: `https://mcp.viridisconservation.com/quantity-takeoff/mcp`.
Pricing: 10 free takeoffs per UTC day, then $0.50 each through the fleet
payment-credit gate. Reads and verification remain free.

## Test

```bash
python3 -m unittest discover -s tests -v
```


## Worked example (copy-paste)

One `tools/call` against the live endpoint — no auth, no signup; the first
10 state-changing calls per day are free, then $0.50/call
(Stripe Checkout for humans, or an a2a escrow via `payment_ref` for agents —
the 402 envelope carries both sets of instructions).

```bash
curl -s https://mcp.viridisconservation.com/quantity-takeoff/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "calculate_takeoff", "arguments": {"items": [{"id": "slab-1", "assembly": "concrete_slab", "unit_system": "imperial", "dimensions": {"length": {"value": "20", "unit": "ft"}, "width": {"value": "30", "unit": "ft"}, "thickness": {"value": "4", "unit": "in"}}}]}}}'
```

Real response (from this exact request; long fields truncated):

```json
{
  "status": "ok",
  "data": {
    "takeoff_status": "complete_for_supplied_items",
    "project_id": null,
    "revision_id": null,
    "inputs": {
      "items": [
        {
          "id": "slab-1",
          "assembly": "concrete_slab",
          "unit_system": "imperial",
          "dimensions": {
            "length": {
              "value": "20",
              "unit": "ft"
            },
            "width": {
              "value": "30",
              "unit": "ft"
            },
            "thickness": {
              "value": "4",
              "unit": "in"
            }
          }
        }
      ],
      "options": {}
    },
    "input_sha256": "930c5cf2c5af6f1745cdbd060fcf3468208467d9e51298dc18c8e2b9c16928b0",
    "line_items": [
      {
        "id": "slab-1:ready_mix_concrete",
        "item_id": "slab-1",
        "status": "determinate",
        "assembly": "concrete_slab",
        "trade": "concrete",
        "material": "ready_mix_concrete",
        "net_qty": "7.407",
        "exact_qty": "7.778",
        "purchase_qty": "7.78",
        "unit": "yd3",
        "quantity_semantics": {
          "net_qty": "geometry before waste",
          "exact_qty": "waste-adjusted calculation quantity at 0.001 output precision",
          "purchase_qty": "waste-adjusted quantity rounded up to purchase increment"
        },
        "waste": {
          "percent": "5",
          "multiplier": "1.05",
          "basis": "material_pack_default",
          "overridden": false,
          "source_id": "viridis-builder-spec-material-pack-v0.1.0",
          "note": "Planning allowance; project placement and form conditions govern."
        },
        "purchase_rounding": {
          "mode": "ROUND_CEILING",
          "increment": "0.01",
          "unit": "yd3",
          "source_id": "viridis-builder-spec-material-pack-v0.1.0",
          "note": null
        },
        "formula": "length_ft * width_ft * thickness_ft / ft3_per_yd3",
        "operands": {
          "length_ft": "20",
          "width_ft": "30",
          "thickness_ft": "0.3333333333333333333333333333",
          "net_ft3": "200",
          "ft3_per_yd3": "27",
          "net_yd3": "7.407407407407407407407407407"
        },
        "geometry": {
          "unit_system": "imperial",
          "measurement_source": null,
          "conversions": [
            {
              "field": "length",
              "input_value": "20",
              "input_unit": "ft",
              "output_value": "20",
              "output_unit": "ft",
              "conversion_group": "length_ft",
              "source_id": "nist-sp811-unit-conversions"
            },
            {
              "field": "width",
              "input_value": "30",
              "input_unit": "ft",
              "output_value": "30",
              "output_unit": "ft",
              "conversion_group": "length_ft",
              "source_id": "nist-sp811-unit-conversions"
            },
            "... 1 more"
          ]
        },
        "source_ids": [
          "aci-ct25-normalweight-concrete",
          "nist-sp811-unit-conversions",
          "... 1 more"
        ],
        "material_pack_version": "2026.07.13-v0.1.0",
        "weight": {
          "net_lb": "30000.000",
          "density_lb_per_yd3": "4050"
        }
      }
    ],
    "indeterminate": [],
    "assembly_rollups": [
      {
        "item_id": "slab-1",
        "assembly": "concrete_slab",
        "trade": "concrete",
        "totals_by_unit": {
          "yd3": {
            "net_qty": "7.407",
            "exact_qty": "7.778",
            "purchase_qty": "7.780"
          }
        }
      }
    ],
    "trade_rollups": {
      "concrete": {
        "totals_by_unit": {
          "yd3": {
            "net_qty": "7.407",
            "exact_qty": "7.778",
            "purchase_qty": "7.780"
          }
        }
      }
    },
    "grand_rollup": {
      "totals_by_unit": {
        "yd3": {
          "net_qty": "7.407",
          "exact_qty": "7.778",
          "purchase_qty": "7.780"
        }
      },
      "determinate_line_count": 1,
      "indeterminate_item_count": 0,
      "coverage_complete_for_supplied_items": true,
      "conservation_basis": "unit-resolved; unlike units are never summed"
    },
    "material_pack": {
      "version": "2026.07.13-v0.1.0",
      "effective_as_of": "2026-07-13",
      "sha256": "7d9ce8d96fd0999b721dd401550381e5e67104c2854f86caba46b957321272b6",
      "sources_used": [
        {
          "id": "aci-ct25-normalweight-concrete",
          "authority": "ACI Concrete Terminology CT-25",
          "title": "Concrete Terminology: normalweight concrete density definition",
          "publisher": "American Concrete Institute",
          "date": "2025",
          "url": "https://www.concrete.org/portals/0/files/pdf/aci_concrete_terminology.pdf"
        },
        {
          "id": "nist-sp811-unit-conversions",
          "authority": "NIST Special Publication 811",
          "title": "Guide for the Use of the International System of Units",
          "publisher": "National Institute of Standards and Technology",
          "date": "2008",
          "url": "https://www.nist.gov/pml/special-publication-811"
        },
        "... 1 more"
      ]
    },
    "lineage": {
      "producer": {
        "agent_id": "quantity-takeoff-agent",
        "version": "0.1.0"
      },
      "input_sha256": "930c5cf2c5af6f1745cdbd060fcf3468208467d9e51298dc18c8e2b9c16928b0",
      "material_pack": {
        "version": "2026.07.13-v0.1.0",
        "sha256": "7d9ce8d96fd0999b721dd401550381e5e67104c2854f86caba46b957321272b6"
      },
      "source_ids_used": [
        "aci-ct25-normalweight-concrete",
        "nist-sp811-unit-conversions",
        "... 1 more"
      ],
      "upstream_measurements": []
    },
    "downstream": {
      "cost_estimator_ready": true,
      "quantity_source": "line_items",
      "audit_binding": "audit_sha256"
    },
    "disclaimer": "Planning-grade deterministic quantity estimate only. Not a guaranteed material order, bid, professional-estimator certification, engineering design, or verifica ...",
    "audit_sha256": "53e5be24ef893fcea890c62593dbec366d5f9f915e6d24c43822505b65f505ec",
    "notary_payload": {
      "content_digest": "53e5be24ef893fcea890c62593dbec366d5f9f915e6d24c43822505b65f505ec",
      "context": "quantity-takeoff:takeoff:qt-53e5be24ef893fcea890c625",
      "digest_algorithm": "sha256"
    }
  }
}
```
