#!/usr/bin/env python3
"""Live-gateway smoke: real MCP client over streamable-http against a running
gateway (default http://127.0.0.1:8402). Run the gateway first, then this.
Exits non-zero on any failure."""
import asyncio, hashlib, json, os, urllib.request
from decimal import Decimal
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

BASE = os.environ.get("BASE", "http://127.0.0.1:8402").rstrip("/")
# A fresh candidate must prove the calculation itself.  A stateful production
# gateway may already have exhausted a gated agent's daily allowance; there a
# precise payment_required response is the correct protocol outcome, not a
# service failure.  Release jobs set STRICT_GATED_CALCS=1 for fresh candidates.
STRICT_GATED_CALCS = os.environ.get("STRICT_GATED_CALCS", "0") == "1"

async def call(path, tool, args):
    async with streamablehttp_client(f"{BASE}/{path}/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            return res.content[0].text

async def tools(path):
    async with streamablehttp_client(f"{BASE}/{path}/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return [t.name for t in (await s.list_tools()).tools]

async def main():
    checks = []
    def check(label, ok):
        checks.append((label, ok)); print(("  OK   " if ok else "  FAIL ") + label)

    t = await tools("identity")
    check(f"identity: tools/list over HTTP ({len(t)} tools)", "register_agent" in t)
    def get_health():
        with urllib.request.urlopen(f"{BASE}/healthz", timeout=20) as response:
            return json.load(response)
    health = await asyncio.to_thread(get_health)
    check(f"gateway: 21 hosted agents healthy ({len(health.get('agents', {}))})",
          health.get("status") == "ok" and len(health.get("agents", {})) == 21
          and health.get("persistence", {}).get("available") is True
          and not health.get("persistence", {}).get("errors", {})
          and health["agents"].get("taxcredit-engine", {}).get("version") == "0.1.0"
          and health["agents"].get("ghg-ledger", {}).get("version") == "0.1.0"
          and health["agents"].get("quantity-takeoff", {}).get("version") == "0.1.0"
          and health["agents"].get("disclosure-compiler", {}).get("version") == "0.1.0"
          and "ghg-ledger" in health.get("payment_gate", {}).get("gated_agents", [])
          and "quantity-takeoff" in health.get("payment_gate", {}).get("gated_agents", [])
          and "disclosure-compiler" in health.get("payment_gate", {}).get("gated_agents", [])
          and health.get("payment_gate", {}).get("prices_minor", {}).get("quantity-takeoff") == 50
          and health.get("payment_gate", {}).get("prices_minor", {}).get("disclosure-compiler") == 200)
    seat_catalog = json.loads(await call("subscriptions", "list_plans", {}))
    seat_plans = {
        plan.get("id"): plan
        for plan in seat_catalog.get("data", {}).get("plans", [])
        if isinstance(plan, dict)
    }
    unlocked = ("energy-seat", "climate-seat", "compliance-seat")
    check("subscriptions: disclosure bundles coverage-ready but checkout fail-closed",
          seat_catalog.get("status") == "ok"
          and seat_catalog.get("data", {}).get("pack_version") == "0.2.0"
          and all(
              seat_plans.get(plan_id, {}).get("coverage_ready") is True
              and seat_plans[plan_id].get("configuration_required") is True
              and seat_plans[plan_id].get("checkout_status")
                  == "configuration_required"
              and seat_plans[plan_id].get("stripe_price_id") is None
              and seat_plans[plan_id].get("approval_status") == "draft"
              and seat_plans[plan_id].get("checkout_enabled") is False
              for plan_id in unlocked))
    reg = json.loads(await call("identity", "register_agent",
                                {"agent_id": "live-worker", "capabilities": ["cad"]}))
    check("identity: register over live MCP", reg["status"] == "ok"
          and reg["data"]["did"].startswith("did:"))
    disc = json.loads(await call("identity", "discover_agents", {"capabilities": ["cad"]}))
    check("identity: state persists across MCP sessions",
          any(item.get("agent_id") == "live-worker"
              for item in disc["data"].get("results", [])))
    cov = json.loads(await call("covenant", "grant_covenant",
                                {"principal": "justin", "agent_id": "live-worker",
                                 "scopes": ["offsets.buy"], "budget_minor": 1000,
                                 "expires_at": "2099-01-01T00:00:00+00:00"}))
    cid = cov["data"]["covenant_id"]
    act = json.loads(await call("covenant", "check_act",
                                {"covenant_id": cid, "act_id": "a1",
                                 "scope": "offsets.buy", "amount_minor": 90}))
    check("covenant: authorized act over live MCP", act["data"]["allowed"] is True)
    await call("offsets", "list_credit",
               {"issuer": "viridis", "project_id": "hdfm-7", "mass_g": 1000,
                "price_minor_per_kg": 900, "verification_ref": "dscore:site7"})
    buy = json.loads(await call("offsets", "buy_offset",
                                {"buyer": "live-worker", "purchase_id": "p1", "mass_g": 80}))
    check("offsets: verified credit retired over live MCP",
          buy["data"]["fills"][0]["mass_g"] == 80)
    m = await call("smartscale", "scale_objects_from_credit_card",
                   {"image_id": "i", "credit_card_pixel_width": 856.0,
                    "objects": [{"name": "box", "pixel_width": 1712.0,
                                 "pixel_height": 856.0}]})
    smartscale_ok = "171.2" in m
    try:
        smartscale_payload = json.loads(m)
    except (TypeError, ValueError):
        smartscale_payload = {}
    smartscale_quota_402 = (
        not STRICT_GATED_CALCS
        and smartscale_payload.get("status") == "error"
        and smartscale_payload.get("error_type") == "payment_required"
        and smartscale_payload.get("http_equivalent") == 402
        and smartscale_payload.get("amount_minor") == 50
        and smartscale_payload.get("currency") == "USD"
        and smartscale_payload.get("billing_path") == "per_call_freemium"
    )
    smartscale_label = (
        "smartscale: measurement over live MCP (171.2 mm)"
        if smartscale_ok else
        "smartscale: exact $0.50 402 after free-tier exhaustion")
    check(smartscale_label, smartscale_ok or smartscale_quota_402)
    led = json.loads(await call("compute-ledger", "record_work",
                                {"agent_id": "live-worker", "entry_id": "e1",
                                 "power_w": 200.0, "duration_s": 3600.0, "bit_ops": 1e19}))
    check("compute-ledger: Landauer-validated entry over live MCP",
          led["status"] == "ok" and 0 < led["data"]["landauer_efficiency"] <= 1)
    tax = json.loads(await call("taxcredit-engine", "calculate_tax_credit", {
        "credit": "45V", "facts": {
            "tax_year": 2026, "kg_hydrogen": "1000",
            "lifecycle_kg_co2e_per_kg_h2": "0.44",
            "greet_version": "45VH2-GREET-2025",
            "evidence_digest": hashlib.sha256(b"smoke-greet-report").hexdigest(),
            "pwa_met": True, "produced_in_us": True,
            "construction_begin_date": "2026-01-01",
            "placed_in_service_date": "2026-01-01",
            "section_45q_claimed_for_facility": False,
            "tax_exempt_bond_financing_percent": "0"}}))
    tax_audit_ok = (
        tax.get("status") == "ok"
        and tax.get("data", {}).get("credit_amount_usd") == "3280.00"
        and len(tax.get("data", {}).get("audit_sha256", "")) == 64
    )
    tax_quota_402 = (
        not STRICT_GATED_CALCS
        and tax.get("status") == "error"
        and tax.get("error_type") == "payment_required"
        and tax.get("http_equivalent") == 402
        and tax.get("amount_minor") == 200
        and tax.get("currency") == "USD"
        and tax.get("billing_path") == "per_call_freemium"
    )
    tax_label = ("taxcredit-engine: 45V 2026 tier-4 audit ($3,280)"
                 if tax_audit_ok else
                 "taxcredit-engine: exact $2.00 402 after free-tier exhaustion")
    check(tax_label, tax_audit_ok or tax_quota_402)
    ghg = json.loads(await call("ghg-ledger", "calculate_inventory", {
        "activities": [{
            "activity_type": "purchased_electricity",
            "quantity": "1000",
            "unit": "kwh",
            "region": "US",
            "year": 2023,
        }],
        "options": {
            "reporting_period": "2026",
            "organization_id": "gateway-smoke",
            "organizational_boundary": "operational_control",
        },
    }))
    ghg_data = ghg.get("data", {})
    ghg_scopes = ghg_data.get("scope_totals_kg_co2e", {})
    try:
        ghg_scope_conserved = (
            Decimal(ghg_scopes["scope_1"])
            + Decimal(ghg_scopes["scope_2_location_based"])
            + Decimal(ghg_scopes["scope_3"])
            == Decimal(ghg_data["grand_total"]["kg_co2e"])
        )
    except (KeyError, TypeError, ValueError, ArithmeticError):
        ghg_scope_conserved = False
    ghg_audit_ok = (
        ghg.get("status") == "ok"
        and ghg_data.get("inventory_status")
            == "complete_for_supplied_activities"
        and ghg_data.get("grand_total", {}).get("kg_co2e") == "349.742"
        and ghg_scopes.get("scope_2_location_based") == "349.742"
        and ghg_scope_conserved
        and len(ghg_data.get("audit_sha256", "")) == 64
    )
    ghg_quota_402 = (
        not STRICT_GATED_CALCS
        and ghg.get("status") == "error"
        and ghg.get("error_type") == "payment_required"
        and ghg.get("http_equivalent") == 402
        and ghg.get("amount_minor") == 100
        and ghg.get("currency") == "USD"
        and ghg.get("billing_path") == "per_call_freemium"
    )
    ghg_label = (
        "ghg-ledger: 1,000 kWh eGRID2023 audit (349.742 kg CO2e)"
        if ghg_audit_ok else
        "ghg-ledger: exact $1.00 402 after free-tier exhaustion")
    check(ghg_label, ghg_audit_ok or ghg_quota_402)

    if ghg_audit_ok:
        audit_sha256 = ghg_data["audit_sha256"]
        input_sha256 = ghg_data["input_sha256"]
        factor_pack = ghg_data["factor_pack"]
        pack_version = (factor_pack.get("version")
                        or factor_pack.get("pack_version"))
        pack_digest = factor_pack.get("sha256") or factor_pack.get("digest")
        source_ids = ghg_data["lineage"]["source_ids_used"]
        record_id = f"ghg-{audit_sha256[:24]}"
        rail_posts = ghg.get("rail_posts", {})
        ghg_posts_ok = (
            rail_posts.get("compute_ledger", {}).get("status") == "ok"
            and rail_posts.get("provenance", {}).get("status") == "ok"
            and rail_posts["compute_ledger"]["inventory_id"] == record_id
            and rail_posts["provenance"]["artifact_id"] == record_id)
        inventory = json.loads(await call(
            "compute-ledger", "get_inventory", {"inventory_id": record_id}))
        artifact = json.loads(await call(
            "provenance", "get_artifact", {"artifact_id": record_id}))
        ghg_lineage_ok = (
            inventory["status"] == "ok"
            and artifact["status"] == "ok"
            and inventory["data"]["mass_g"] == 349742
            and inventory["data"]["content_digest"] == audit_sha256
            and inventory["data"]["factor_pack_version"] == pack_version
            and inventory["data"]["factor_pack_digest"] == pack_digest
            and inventory["data"]["source_ids"] == source_ids
            and artifact["data"]["artifact_hash"] == audit_sha256
            and artifact["data"]["parent_hashes"] == [pack_digest]
            and artifact["data"]["relation"] == "calculated_from"
            and artifact["data"]["metadata_digest"] == input_sha256)
        verified = json.loads(await call(
            "ghg-ledger", "verify_result",
            {"result_json": json.dumps(
                ghg_data, sort_keys=True, separators=(",", ":"))}))
        ghg_verify_ok = (
            verified["status"] == "ok"
            and verified["data"]["valid"] is True
            and verified["data"]["factor_pack_current"] is True
            and verified["data"]["supplied_sha256"]
                == verified["data"]["computed_sha256"])
        tampered = json.loads(json.dumps(ghg_data))
        tampered["grand_total"]["kg_co2e"] = "0.000"
        rejected = json.loads(await call(
            "ghg-ledger", "verify_result",
            {"result_json": json.dumps(
                tampered, sort_keys=True, separators=(",", ":"))}))
        ghg_tamper_ok = (
            rejected["status"] == "ok"
            and rejected["data"]["valid"] is False
            and rejected["data"]["supplied_sha256"]
                != rejected["data"]["computed_sha256"])
    else:
        # Production can legitimately be quota-exhausted. The exact 402 proves
        # the gate contract; dependent calculation/rail checks are deferred,
        # never attempted with absent data and never represented as executed.
        ghg_posts_ok = ghg_lineage_ok = ghg_verify_ok = ghg_tamper_ok = (
            ghg_quota_402)

    quota_suffix = " deferred by exact $1.00 402" if ghg_quota_402 else ""
    check("ghg-ledger: derived posts accepted by both free rails" + quota_suffix,
          ghg_posts_ok)
    check("ghg-ledger: rail records preserve mass, audit, and factor lineage"
          + quota_suffix, ghg_lineage_ok)
    check("ghg-ledger: audit verifies against current factor pack" + quota_suffix,
          ghg_verify_ok)
    check("ghg-ledger: audit rejects a tampered total" + quota_suffix,
          ghg_tamper_ok)

    disclosure_args = {
        "framework": "esrs-e1",
        "company_facts": {
            "company_name": "Viridis Gateway Smoke",
            "reporting_period": "2026",
            "transition_plan": {
                "status": "supplied_for_smoke_verification",
                "professional_review_required": True,
            },
            "climate_targets": {
                "target": "supplied_for_smoke_verification",
                "professional_review_required": True,
            },
            "ghg_intensity": {
                "value": "1.000",
                "unit": "tCO2e/USDm revenue",
            },
        },
        "options": {"applicability": {
            "framework": "esrs-e1",
            "applies": True,
            "reason": "regulatory-radar matched ESRS E1 for smoke verification",
            "source": "regulatory-radar",
        }},
    }
    if ghg_audit_ok:
        disclosure_args["ghg_result"] = ghg_data
    disclosure = json.loads(await call(
        "disclosure-compiler", "compile_disclosure", disclosure_args))
    disclosure_data = disclosure.get("data", {})
    completeness = disclosure_data.get("completeness", {})
    filled = disclosure_data.get("filled_datapoints", [])
    gaps = disclosure_data.get("gaps", [])
    expected_filled = 9 if ghg_audit_ok else 5
    expected_missing = 1 if ghg_audit_ok else 5
    expected_ratio = "0.900000" if ghg_audit_ok else "0.500000"
    expected_percent = "90.00" if ghg_audit_ok else "50.00"
    disclosure_audit_ok = (
        disclosure.get("status") == "ok"
        and disclosure_data.get("framework", {}).get("id") == "esrs-e1"
        and disclosure_data.get("label")
            == "disclosure draft for professional review"
        and disclosure_data.get("inference_used") is False
        and completeness.get("filled_required") == expected_filled
        and completeness.get("required") == 10
        and completeness.get("missing_required") == expected_missing
        and completeness.get("ratio") == expected_ratio
        and completeness.get("percent") == expected_percent
        and len(filled) == expected_filled
        and len(gaps) == expected_missing
        and all(len(item.get("citations", [])) >= 2 for item in filled)
        and all(str(item.get("status", "")).startswith("MISSING: ")
                and item.get("excluded_from_filled") is True for item in gaps)
        and len(disclosure_data.get("audit_sha256", "")) == 64
        and disclosure_data.get("notary_payload", {}).get("content_digest")
            == disclosure_data.get("audit_sha256")
        and disclosure_data.get("notary_payload", {}).get("digest_algorithm")
            == "sha256"
        and (not ghg_audit_ok or (
            disclosure_data.get("ghg_provenance", {}).get("audit_sha256")
                == ghg_data.get("audit_sha256")
            and disclosure_data.get("ghg_provenance", {}).get(
                "factor_pack", {}).get("sha256")
                == ghg_data.get("factor_pack", {}).get("sha256")
            and any(
                citation.get("type") == "verified_ghg_result"
                and citation.get("audit_sha256") == ghg_data.get("audit_sha256")
                for item in filled for citation in item.get("citations", []))
        ))
    )
    disclosure_quota_402 = (
        not STRICT_GATED_CALCS
        and disclosure.get("status") == "error"
        and disclosure.get("error_type") == "payment_required"
        and disclosure.get("http_equivalent") == 402
        and disclosure.get("amount_minor") == 200
        and disclosure.get("currency") == "USD"
        and disclosure.get("billing_path") == "per_call_freemium"
    )
    disclosure_label = (
        "disclosure-compiler: cited ESRS E1 draft with verified GHG lineage"
        if disclosure_audit_ok else
        "disclosure-compiler: exact $2.00 402 after free-tier exhaustion")
    check(disclosure_label, disclosure_audit_ok or disclosure_quota_402)

    if disclosure_audit_ok:
        disclosure_verified = json.loads(await call(
            "disclosure-compiler", "verify_result", {
                "result_json": json.dumps(
                    disclosure_data, sort_keys=True, separators=(",", ":")),
            }))
        verified_data = disclosure_verified.get("data", {})
        disclosure_verify_ok = (
            disclosure_verified.get("status") == "ok"
            and verified_data.get("valid") is True
            and verified_data.get("audit_hash_valid") is True
            and verified_data.get("notary_payload_valid") is True
            and verified_data.get("framework_pack_current") is True
            and verified_data.get("supplied_sha256")
                == verified_data.get("computed_sha256")
        )
        disclosure_tampered = json.loads(json.dumps(disclosure_data))
        disclosure_tampered["filled_datapoints"][0]["value"] = (
            "tampered gateway smoke value")
        disclosure_rejected = json.loads(await call(
            "disclosure-compiler", "verify_result", {
                "result_json": json.dumps(
                    disclosure_tampered, sort_keys=True, separators=(",", ":")),
            }))
        rejected_data = disclosure_rejected.get("data", {})
        disclosure_tamper_ok = (
            disclosure_rejected.get("status") == "ok"
            and rejected_data.get("valid") is False
            and rejected_data.get("audit_hash_valid") is False
            and rejected_data.get("supplied_sha256")
                != rejected_data.get("computed_sha256")
        )
    else:
        disclosure_verify_ok = disclosure_tamper_ok = disclosure_quota_402
    disclosure_quota_suffix = (
        " deferred by exact $2.00 402" if disclosure_quota_402 else "")
    check("disclosure-compiler: audit and notary payload verify"
          + disclosure_quota_suffix, disclosure_verify_ok)
    check("disclosure-compiler: tampered draft audit is rejected"
          + disclosure_quota_suffix, disclosure_tamper_ok)

    takeoff = json.loads(await call(
        "quantity-takeoff", "calculate_takeoff", {
            "items": [{
                "id": "smoke-slab-1",
                "assembly": "concrete_slab",
                "unit_system": "imperial",
                "dimensions": {
                    "length": {"value": "20", "unit": "ft"},
                    "width": {"value": "30", "unit": "ft"},
                    "thickness": {"value": "4", "unit": "in"},
                },
            }],
            "options": {"project_id": "gateway-smoke"},
        }))
    takeoff_data = takeoff.get("data", {})
    takeoff_lines = takeoff_data.get("line_items", [])
    takeoff_line = takeoff_lines[0] if len(takeoff_lines) == 1 else {}
    takeoff_audit_ok = (
        takeoff.get("status") == "ok"
        and takeoff_data.get("takeoff_status")
            == "complete_for_supplied_items"
        and takeoff_line.get("material") == "ready_mix_concrete"
        and takeoff_line.get("net_qty") == "7.407"
        and takeoff_line.get("exact_qty") == "7.778"
        and takeoff_line.get("purchase_qty") == "7.78"
        and len(takeoff_data.get("audit_sha256", "")) == 64
        and takeoff_data.get("notary_payload", {}).get("content_digest")
            == takeoff_data.get("audit_sha256")
    )
    takeoff_quota_402 = (
        not STRICT_GATED_CALCS
        and takeoff.get("status") == "error"
        and takeoff.get("error_type") == "payment_required"
        and takeoff.get("http_equivalent") == 402
        and takeoff.get("amount_minor") == 50
        and takeoff.get("currency") == "USD"
        and takeoff.get("billing_path") == "per_call_freemium"
    )
    takeoff_label = (
        "quantity-takeoff: 20x30x4in slab audit (7.78 yd3 purchase)"
        if takeoff_audit_ok else
        "quantity-takeoff: exact $0.50 402 after free-tier exhaustion")
    check(takeoff_label, takeoff_audit_ok or takeoff_quota_402)
    if takeoff_audit_ok:
        takeoff_verified = json.loads(await call(
            "quantity-takeoff", "verify_result", {
                "result_json": json.dumps(
                    takeoff_data, sort_keys=True, separators=(",", ":")),
            }))
        takeoff_verify_ok = (
            takeoff_verified.get("status") == "ok"
            and takeoff_verified.get("data", {}).get("valid") is True
            and takeoff_verified.get("data", {}).get("material_pack_current")
                is True
        )
    else:
        takeoff_verify_ok = takeoff_quota_402
    check("quantity-takeoff: audit verifies against current material pack",
          takeoff_verify_ok)
    fails = [l for l, ok in checks if not ok]
    print(f"\nLIVE GATEWAY: {len(checks)-len(fails)}/{len(checks)} protocol checks passed")
    raise SystemExit(1 if fails else 0)

asyncio.run(main())
