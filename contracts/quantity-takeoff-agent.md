# Viridis Quantity Takeoff — public contract

Endpoint: `https://mcp.viridisconservation.com/quantity-takeoff/mcp`

Version: `0.1.0`

This deterministic construction primitive converts explicit typed dimensions,
SmartScale measurements, or ProtoGen/CAD measurement payloads into auditable
material quantities. Its serving path uses Python stdlib, `Decimal`, and one
bundled, versioned, source-linked material pack. It uses no inference, paid API,
or network lookup and never guesses an unknown assembly or factor.

## Public tools

`calculate_takeoff`, `list_assemblies`, `get_assembly`, `list_material_pack`,
`get_material_pack`, `verify_result`, and `describe_agent`.

## v0.1 coverage and source pack

Material pack `2026.07.13-v0.1.0` covers concrete slabs, footings, walls and
columns; rebar grids with #3–#11 unit weights; wood-wall framing, sheathing,
drywall and dimensional lumber; asphalt shingles with roof-pitch multipliers;
8×8×16 CMU and modular brick veneer; a common AISC W/HSS structural-steel
subset; excavation, aggregate base and paint. It also bundles locked waste
factors, purchase increments, and explicit length/area/volume/mass conversions.

Every constant cites one of the pack's dated sources, including ACI, CRSI,
AWC/NDS, APA, GA-235-10, GAF, TMS, CMHA, BIA, AISC, ASTM, NIST,
Sherwin-Williams, or the explicitly non-authoritative Viridis builder-spec pin
record. Everything outside this enumerated pack fails closed as
`indeterminate`.

## QT1–QT9 contract invariants

- **QT1 — Decimal and dual quantities.** All quantity math uses `Decimal`; output reports both exact and conservatively
  rounded purchase quantities.
- **QT2 — Locked waste.** Waste factors are locked to the material pack unless the caller supplies an
  explicit override, which is recorded in the result.
- **QT3 — Geometry validation.** The unit system is mandatory and dimensions must be finite and positive.
- **QT4 — Line auditability.** Every line exposes its formula, operands, factor source, waste application,
  purchase increment, and rounding rule.
- **QT5 — Unit integrity.** Conversions use only the bundled unit table; unsupported conversions fail.
- **QT6 — Fail closed.** Unknown assemblies and missing dimensions become explicit `indeterminate`
  lines and are excluded from totals.
- **QT7 — Conservative purchase rounding.** Exact quantity rounds upward only to the material's recorded purchase increment.
- **QT8 — Deterministic audit.** Every result carries material-pack version/SHA-256, `audit_sha256`, and a
  notary-ready payload without a timestamp inside the hashed content.
- **QT9 — Conservation.** Assembly, trade, and grand rollups conserve exactly and fail loudly on drift.

## Pricing and liability

The first 10 takeoffs per UTC day are free; additional calculations cost $0.50
each through the fleet payment-credit gate and `redeem_payment`. Catalog reads,
verification, and agent description remain free. A future construction B2B seat
will add monthly entitlement without changing anonymous per-call access.

Outputs are auditable planning estimates, not guaranteed material orders or a
substitute for a professional estimator. They do not verify field conditions or
drawing completeness. Industry-typical waste defaults must be confirmed for the
specific project.
