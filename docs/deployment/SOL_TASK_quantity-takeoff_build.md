# Sol — build `quantity-takeoff` (Material Takeoff Engine)

**This is fleet revenue tool #3 and the first construction primitive.** Build it exactly like `taxcredit-engine-agent` and `ghg-ledger-agent` (your reference implementations): deterministic Decimal core + thin MCP adapter + **bundled, versioned, source-linked** data pack + letter-series invariant tests that fail loud + content-addressed audit hash that composes with the notary rail. Ship end-to-end: build → wire into gateway → deploy to droplet (**19→20**) → submission pipeline.

Read `docs/deployment/CONSTRUCTION_TOOLS_BUILD_LIST.md` first — this anchors the **agent estimator pipeline** (`smartscale` measure → **`quantity-takeoff`** → `cost-estimator` → `bid-leveler` → `payment-app`).

## What it is

Dimensions/geometry (typed, or a `smartscale`/`protogen` measurement result) → **material quantities with locked, explicit waste factors**: concrete yd³, rebar lb/lf, framing board-feet + stud counts, drywall/sheathing sheets, roofing squares, CMU/brick counts, structural-steel tonnage, sitework volumes, paint gallons. Pure deterministic geometry + a bundled material-data pack. **No inference in the serving path, no paid APIs.** It computes an auditable quantity *estimate*; it is not a guaranteed material order.

Directly kills the market's top pain: the "5 estimators / 5 different waste factors" inconsistency and slow bid turnaround.

## Spec invariants (QT1–QT9 — restate, implement, test each)

- **QT1 — Decimal + dual quantities.** All math in `Decimal`. Report **exact quantity** and **purchase quantity** (rounded to the material's purchase increment). No floats in the math path.
- **QT2 — Waste factors explicit & locked.** Every material's waste factor comes from the bundled pack (industry-typical default), is applied explicitly, and the version used is recorded on the result. A caller may override, but the override is recorded (not silent). This is the whole point — standardized, auditable waste.
- **QT3 — Geometry validated.** Zero/negative/non-finite dimensions → error; the unit system must be explicit (imperial/SI); never assume a unit silently.
- **QT4 — Every line is auditable.** Each material line carries its formula + operands + factor source. No magic numbers; every constant traces to the pack + a source id.
- **QT5 — Unit integrity.** Dimension units and factor units must be consistent; conversions only via the **bundled unit table** (in↔ft, ft²↔yd², ft³↔yd³, lb↔ton, etc.); mismatch with no bundled conversion → error, never a silent reinterpretation.
- **QT6 — Fail closed on unknowns.** Unknown assembly/material or missing required dimension → that line is `indeterminate` with a reason, excluded from totals, surfaced explicitly. Never guess a factor or quantity. (Mirror taxcredit TC6.)
- **QT7 — Purchase rounding is explicit & conservative.** Exact → purchase rounds **up** to the purchase increment (whole sheets, bags, sticks, whole tons or specified fraction, etc.); both values reported; the rounding rule is recorded per line.
- **QT8 — Content-addressed, deterministic audit.** `audit_sha256` over canonical(inputs + pack sha + result) + a `notary_payload` (same shape taxcredit/ghg emit) so a takeoff can be **locked and stamped on the notary rail**. No timestamp inside hashed content — byte-reproducible. Provide `verify_result`.
- **QT9 — Conservation.** Assembly total == Σ its line items; per-trade rollups and the grand rollup reconcile exactly; **fail loud** on any drift (mirror surety/offset/ghg conservation checks).

## Tool surface (actions)

- `calculate_takeoff(items[], options)` → per-line {exact_qty, purchase_qty, unit, weight?, formula, operands, source} + per-trade & grand rollups + `indeterminate[]` + `audit_sha256`/`notary_payload`. Each `item` = `{assembly, dimensions{}, waste_override?}`; `dimensions` may be a `smartscale`/`protogen` measurement payload.
- `list_assemblies()` / `get_assembly(type)` → supported assemblies, required dimensions, default waste, formula, sources.
- `list_material_pack()` / `get_material_pack()` → bundled factors/densities/coverages + sources + pack sha (like taxcredit's list/get_rule_pack).
- `verify_result(result)` → recompute + compare `audit_sha256`; flag `material_pack_current`.
- `describe_agent()` / health with version + pack digest.

## Bundled data — `data/material_pack.vX.json` (enumerate; else QT6 indeterminate)

MVP assemblies + the constants each needs, every constant source-linked (industry standards: ACI/CRSI rebar weights, APA/NDS lumber, ASTM/TMS masonry unit coverage, AISC shape weights, asphalt-shingle squares, ASTM aggregate densities). Non-authoritative pin record like taxcredit's `builder-spec`.
- **Concrete:** `concrete_slab`, `concrete_footing`, `concrete_wall`, `concrete_column` (volume → yd³; density 4050 lb/yd³).
- **Rebar:** bar unit weights #3–#11 (e.g. #4 = 0.668 lb/ft, #5 = 1.043 lb/ft) → lf + weight from spacing/count.
- **Framing:** `wood_wall_framing` (studs from length ÷ spacing + corners/openings), `sheathing`, `drywall` (area ÷ 32 sf/sheet), `dimensional_lumber` (board-feet = nominal-in × nominal-in × length-ft ÷ 12).
- **Roofing:** `asphalt_shingle` (area ÷ 100 = squares × pitch-multiplier table).
- **Masonry:** `cmu_wall` (1.125 units/sf for 8×8×16), `brick_veneer` (6.75 modular/sf).
- **Steel:** `structural_steel` (AISC shape lb/ft × length → tons) — a common-shape subset (W, HSS).
- **Sitework:** `excavation`, `aggregate_base` (volume × density → tons), `paint` (area ÷ coverage sf/gal × coats).
- **Waste factors:** default % per material (e.g. concrete 5%, drywall 10%, roofing 10%, framing 10%) — the locked table.
- **Unit conversions** table.

## Composition with the rails (the flywheel)

- **smartscale / protogen** — accept a measurement/CAD payload as `dimensions` (measure-from-photo → takeoff, or CAD → takeoff).
- **notary** — `notary_payload` locks an auditable takeoff (kills "estimators rebuild from scratch every revision" — a stamped, versioned takeoff).
- **metering** — every `calculate_takeoff` is a metered, priced call.
- **feeds `cost-estimator`** (next build) — quantities are the input to unit-cost estimating.

## Pricing / gate

Per the pricing doctrine (agent-market micro = adoption): **agent per-call $0.50 / takeoff** (`PRICE_MINOR = 50`), 10 free calls/day, `redeem_payment` packs. Capital comes later from the **construction B2B seat** (subscription tier). Add `quantity-takeoff` to `payment_gate.py` `PRICE_MINOR` + the gate attach tuple (`viridis_mcp_gateway.py`), the deck maps (`ROLE`("revenue · construction")/`PRICE_L`(50)/`PRICE`(50)/footnote), and healthz. Rails stay free.

## Liability discipline (like taxcredit)

Output is an **auditable quantity estimate for planning** — not a guaranteed material order, not a substitute for a professional estimator, and it does not verify field conditions or drawing completeness. Waste factors are industry-typical defaults; confirm project-specific. Ship a disclaimer in every result + `describe`.

## Tests (QT1–QT9, stdlib unittest) — assert exact hand-verifiable numbers

At least: concrete slab 20ft×30ft×4in → 200 ft³ = **7.407 yd³**, +5% waste = **7.78 yd³**; drywall 1,000 sf ÷ 32 = 31.25 sheets, +10% = 34.375 → purchase **35 sheets** (round-up); roofing 2,400 sf ÷ 100 = 24 sq × 6:12 pitch multiplier; `W12x26` × 40 ft = 1,040 lb = **0.52 ton**; a rebar line from spacing; a unit-conversion case; an unknown assembly → `indeterminate` (excluded from totals); a conservation check that fails loud if a rollup is tampered; a `verify_result` tamper case; and a waste-override-recorded case. Wire into `run_fleet_tests.py`; full gate stays green.

## Ship checklist (end-to-end — same path taxcredit/ghg took)

- [ ] Core + adapter + `mcp_server.py`; QT1–QT9 tests green; added to `run_fleet_tests.py`
- [ ] `data/material_pack.vX.json` — factors/densities/coverages/waste/units, all source-linked + sha
- [ ] Mounted `/quantity-takeoff/mcp`; healthz + version; payment gate $0.50; gate attach tuple + deck maps updated
- [ ] Build image, **tag rollback** (`viridis-stable:pre-takeoff-<date>`), `docker compose up -d --force-recreate gateway`; verify healthz **19→20**, all ok, gated set includes `quantity-takeoff`, persistence intact
- [ ] Submission pipeline: regen `deploy/glama/fleet_manifest.json` + add to `fleet_bridge.py` ROLE → push public repo → Glama Sync + Build & Release → Smithery `hartjustin6/quantity-takeoff` (Continue needs a 2nd click) → official registry `io.github.jdhart81/quantity-takeoff`

## Follow-ups (v0.2 — not blockers)

Expand assemblies (MEP rough-in, insulation, doors/windows, flooring); metric/SI parity; assembly *kits* (e.g. "wall assembly" = studs+plates+sheathing+drywall+insulation in one call); optional paid inference tier to parse a plan/scope PDF into `items[]` (separate tier, pass-through metered, never in the free path). Keep every factor change a new dated pack version with sources + bumped sha.
