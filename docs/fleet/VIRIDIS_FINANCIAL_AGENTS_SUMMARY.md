# Viridis Financial Layer: Carbon Bridge & Thermo Arbitrage Agents

**Build Date:** March 28, 2026
**Total Lines of Code:** 2,833 (production-ready Python)
**Disk Used:** ~150MB (including tests)
**Status:** Ready for deployment

---

## Executive Summary

Two novel financial-layer agents operationalize Viridis's core intellectual property:

1. **Carbon Bridge Agent** — TFAC origination, verification, pricing, market routing
2. **Thermo Arbitrage Agent** — Systematic biodiversity mispricing detection via Intelligence Bound theorem

Both implement the thermodynamic economics framework (I_ceiling = P·D/(k_B·T·ln 2)) as production code with real physics, real finance, and comprehensive test coverage.

---

## AGENT 1: CARBON-BRIDGE-AGENT

### Location
`/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/carbon-bridge-agent/`

### Architecture
```
carbon-bridge-agent/
├── agent.yaml                    # Manifest & configuration
├── requirements.txt              # Dependencies
├── src/
│   ├── core.py                  # Main agent (590 lines)
│   ├── tfac_pricing.py          # Thermodynamic valuation (363 lines)
│   └── credit_registry.py       # Ledger & audit trail (474 lines)
├── adapters/
│   └── fastapi_server.py        # REST API endpoints
└── tests/
    └── test_core.py            # 250+ line test suite
```

### Key Features

#### 1. Credit Origination
- **Input:** Restoration project + D-Score assessment
- **Output:** Carbon credits + TFAC credits (dual issuance)
- **Logic:**
  - Carbon: Standard methodology (tonnes CO2e)
  - TFAC: Novel instrument (units of avoided intelligence loss)

#### 2. TFAC Pricing Engine (`tfac_pricing.py`)
Implements thermodynamic valuation:

```
TFAC = NPV of avoided intelligence loss
I_ceiling = P·D/(k_B·T·ln 2)

Where:
- P: Solar irradiance (1361 W/m²) proxy for info processing power
- D: Biodiversity index (baseline → projected)
- k_B: Boltzmann constant (1.380649e-23 J/K)
- T: Temperature (K)
- ln 2: Information entropy unit

NPV = Σ(ΔI·area) / (1+r)^t
- Discount rate: 3% (vs 5% for carbon)
- TFAC premium: 5x over carbon baseline ($25 → $125/TFAC)
```

**Key Methods:**
- `compute_intelligence_ceiling()` — Calculate I_ceiling for region
- `price_tfac()` — Full thermodynamic valuation with NPV
- `marginal_value_of_biodiversity()` — ∂I_ceiling/∂D analysis
- `sensitivity_analysis()` — Curves for temperature, D-score, area, risk
- `carbon_equivalent_tonnage()` — Convert Joules → tCO2e → USD

#### 3. Carbon Pricing
Standard financial adjustments:
- Base: $25/tCO2e
- Verification premium: +10%
- Methodology premium: +5-15% (AR-ACM0015, VCS M-CPR)
- Vintage discount: -2% per year
- Floor: $15/tCO2e

#### 4. Verification Workflow
Routes evidence to validation:
- **Evidence Types:** Satellite, acoustic, drone, ground measurement
- **Outputs:** Verification status, attestation, confidence score
- **Updates:** Credit status → VERIFIED in registry

#### 5. Market Routing
Matches credits to optimal markets:
- **Carbon:** Verra VCS, Gold Standard, EU ETS, Article 6, Bilateral
- **TFAC:** Bilateral (ESG-focused), Gold Standard
- **Decision Logic:** Methodology quality + vintage + verification + market depth

#### 6. Credit Registry (`credit_registry.py`)
Immutable ledger with full audit trail:
- **Lifecycle:** ORIGINATED → VERIFIED → LISTED → SOLD → RETIRED
- **Operations:**
  - `issue_credit()` — Issuance with serial number
  - `verify_credit()` — Mark verified
  - `list_credit()` — Put on market
  - `sell_credit()` — Transfer (with partial-split support)
  - `retire_credit()` — Remove from circulation
  - `cancel_credit()` — Invalidate
- **Deduplication:** Serial number uniqueness enforced
- **Audit Trail:** Every transaction logged with timestamp, actor, metadata

#### 7. Portfolio Analytics
Aggregate across projects:
- Total carbon tonnes & TFAC units
- Weighted average pricing
- Status distribution (originated, verified, sold, retired)
- Vintage distribution
- Permanence risk assessment

### REST API Endpoints

**Carbon Bridge Agent** runs on `localhost:8000`

```
POST /originate
  Input: {project, dscore}
  Output: {carbon_credit, tfac_credit, total_value_usd, origination_fee}

POST /price-tfac
  Input: {dscore_baseline, dscore_projected, area_hectares, time_horizon_years, ...}
  Output: {price_per_unit, total_value, npv_joules, carbon_equivalent_tonnes}

POST /price-carbon
  Input: {tonnes_co2, vintage, methodology, verification_status}
  Output: {price_per_unit, total_value, adjustments}

POST /verify
  Input: {project_id, evidence}
  Output: {status, validation_score, attestation, credits_updated}

POST /route-to-market
  Input: {project_id, market_preference}
  Output: {recommended_market, estimated_value_usd, credits_routed}

GET /portfolio/{project_id}
  Output: {total_tonnes, total_tfac_units, status_distribution, vintage_distribution}

GET /credit/{serial}
  Output: {credit_metadata, status, pricing, audit_trail}

GET /registry/summary
  Output: {total_credits, status_distribution, vintage_range}

GET /registry/transactions?limit=100
  Output: {transaction_history}

POST /tfac-sensitivity
  Input: {sensitivity_params}
  Output: {temperature_curve, d_score_curve, area_curve, permanence_curve}
```

### Test Coverage (`test_core.py` — 250+ lines)

**TFAC Pricing Tests:**
- `test_intelligence_ceiling_computation()` — Physical consistency
- `test_marginal_value_of_biodiversity()` — ∂I/∂D verification
- `test_tfac_pricing_basic()` — Positive pricing, units consistency
- `test_tfac_pricing_no_biodiversity_gain()` — Edge case (zero gain)
- `test_tfac_premium_over_carbon()` — 3-10x premium validation
- `test_tfac_sensitivity_analysis()` — All parameter sensitivities

**Carbon Pricing Tests:**
- `test_carbon_pricing_baseline()` — Base case with adjustments
- `test_carbon_vintage_discount()` — Age penalty
- `test_carbon_verification_premium()` — Verification boost

**Origination Tests:**
- `test_originate_credits()` — End-to-end dual issuance
- `test_origination_project_mismatch()` — Validation

**Verification & Registry Tests:**
- `test_verify_project()` — Status transitions
- `test_registry_issuance()` — Credit creation
- `test_registry_state_transitions()` — Full lifecycle
- `test_registry_partial_sale()` — Credit splitting
- `test_registry_portfolio_summary()` — Aggregation

**Integration Tests:**
- `test_end_to_end_origination_to_retirement()` — Full workflow

---

## AGENT 2: THERMO-ARBITRAGE-AGENT

### Location
`/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/thermo-arbitrage-agent/`

### Architecture
```
thermo-arbitrage-agent/
├── agent.yaml                    # Manifest & configuration
├── requirements.txt              # Dependencies
├── src/
│   ├── core.py                  # Main agent (607 lines)
│   ├── intelligence_bound.py    # I_ceiling computation (398 lines)
│   └── repricing_model.py       # Catalyst modeling (401 lines)
├── adapters/
│   └── fastapi_server.py        # REST API endpoints
└── tests/
    └── test_core.py            # 250+ line test suite
```

### Key Features

#### 1. Intelligence Ceiling Computation (`intelligence_bound.py`)

**Core Formula:**
```
I_ceiling = P·D/(k_B·T·ln 2)

Methods:
- compute_intelligence_ceiling(d_score, temperature_k, solar_irradiance)
  → Information bits/sec for a region

- marginal_value_per_d_increase(temperature_k)
  → ∂I_ceiling/∂D = P/(k_B·T·ln 2) in J/K

- solar_irradiance_by_latitude(latitude, season, cloud_fraction)
  → I = I_0 × cos(lat) × (1 - cloud) with seasonal adjustment
```

**Features:**
- Latitude-aware solar irradiance (equator vs poles)
- Seasonal adjustments (equinox, summer, winter, annual)
- Cloud attenuation (Beer-Lambert model)
- Temperature effects on entropy/information capacity
- Uncertainty quantification (95% confidence intervals)

#### 2. Regional Comparison & Ranking
```
regional_ranking(regions) → List[(region, i_ceiling)]

Sorted by information ceiling (highest first)
Reveals which regions have highest ecological information processing capacity
```

#### 3. Climate Scenario Analysis
```
climate_scenario_analysis(region, baseline_temp, baseline_d, scenarios)

Scenarios:
- Current conditions (baseline)
- +1K warming
- +2K warming
- +3K warming

Output: I_ceiling change per scenario
Shows how climate × biodiversity loss affects information ceiling
```

#### 4. Market Pricing Estimation
Estimates what market currently prices region at:

**Components:**
- **Carbon market:** area × CO2/hectare × years × carbon price
- **Land value:** area × market land price per km²
- **Ecosystem services:** ~15% of land value
- **Market risk discount:** Sovereign risk × 0.5

**Typical:** $100K-$500K/km² depending on region & risk

#### 5. Mispricing Detection
```
Gap = Ecological_Value (I_ceiling) - Market_Price
Mispricing_Score = (gap_magnitude / ecological_value) × (1 - sovereign_risk × 0.3)

Direction: "undervalued" if gap > 0, "overvalued" if gap < 0
```

#### 6. Opportunity Scanning
```
scan_opportunities(regions, top_n=20) → Ranked list

Expected Value = Gap × Repricing_Probability × Time_Discount

Repricing_Probability ≈ 0.7 × (1 - sovereign_risk)
Time_to_Repricing ≈ 5 years (catalyst-dependent)
```

#### 7. Signal Generation
```
generate_signal(opportunity) → Investment recommendation

Signal Logic:
- STRONG_BUY: gap > 50%, score > 0.6, repricing_prob > 0.6 (5% of portfolio)
- BUY: gap > 30%, score > 0.4 (3% of portfolio)
- MONITOR: gap > 10% (1% of portfolio)
- HOLD: gap ≤ 10% (0% allocation)

Returns:
- Position sizing (% of portfolio)
- Expected return (% p.a.)
- Risk factors (sovereign, regulatory, liquidity, execution)
- Entry/exit strategy
```

#### 8. Portfolio Construction
```
portfolio_construction(opportunities, risk_budget=0.15)

Constraints:
- Total risk < risk_budget
- Diversification across regions/ecosystems
- Max position size caps
- Only STRONG_BUY and BUY signals

Output:
- Portfolio positions (with weights)
- Expected return %
- Risk score
- Diversification metrics
```

#### 9. Repricing Catalyst Model (`repricing_model.py`)

**Five Catalysts:**

1. **TNFD (Taskforce Nature-related Financial Disclosure)**
   - Current adoption: 15%
   - Target: 100% (mandatory)
   - Adoption rate: 8%/year
   - Impact: +40% repricing
   - Timeline: ~8-10 years

2. **EU Taxonomy Expansion**
   - Current: 60%
   - Target: 100%
   - Rate: 10%/year
   - Impact: +30%
   - Timeline: ~4 years

3. **Insurance Repricing**
   - Current: 5%
   - Target: 100%
   - Rate: 12%/year
   - Impact: +50% (highest!)
   - Timeline: ~7 years

4. **Carbon Market Convergence**
   - Voluntary ↔ Compliance price gap narrowing
   - Nature credits integrate alongside carbon
   - Impact: +35% via market integration

5. **Sovereign Risk Repricing**
   - Biodiversity-dependent countries face higher debt costs
   - Current: 10% adoption
   - Impact: +25%

**Composite Repricing Score:**
```
Weighted average of catalyst distances:
- Regulatory: 40%
- Insurance: 30%
- Carbon market: 20%
- Sovereign: 10%

Result: "early_stage", "building", or "accelerating"
```

#### 10. Strategy Backtesting
```
backtest(historical_data, strategy="momentum")

Outputs:
- Cumulative return %
- Win rate %
- Sharpe ratio
- Average return per trade
```

### REST API Endpoints

**Thermo Arbitrage Agent** runs on `localhost:8001`

```
GET /health
  Output: {status, agent, version, timestamp}

GET /describe
  Output: {capabilities, inputs, outputs}

POST /compute-ceiling
  Input: {region}
  Output: {i_ceiling_bits_per_sec, estimated_ecological_value_usd, solar_factor}

POST /detect-mispricing
  Input: {region}
  Output: {ecological_value, market_price, gap_usd, gap_percent, mispricing_score}

POST /scan-opportunities
  Input: {regions[], top_n}
  Output: {opportunities[], total_portfolio_ev, top_region}

POST /generate-signal
  Input: {opportunity}
  Output: {signal, position_sizing, expected_return%, risk_factors}

POST /portfolio
  Input: {opportunities[], risk_budget}
  Output: {positions[], portfolio_return%, portfolio_risk, diversification}

POST /backtest
  Input: {historical_data, strategy}
  Output: {cumulative_return%, win_rate, sharpe_ratio}

GET /intelligence-ceiling/marginal-value?temperature_k=288.15
  Output: {marginal_value_j_per_k, usd_per_d_unit}

POST /climate-scenario
  Input: {region_name, baseline_temp, baseline_d, warming_scenarios[]}
  Output: {scenario_analysis[]}

GET /repricing/timeline?jurisdiction=EU
  Output: {years_to_repricing, key_catalysts, timeline_breakdown}

POST /repricing/impact
  Input: {current_market_price, ecological_value}
  Output: {repricing_impact_usd, repricing_impact%, revised_price}

GET /regional-ranking
  Input: {regions[]}
  Output: {regional_ranking[]}
```

### Test Coverage (`test_core.py` — 250+ lines)

**Intelligence Ceiling Tests:**
- `test_intelligence_ceiling_basic()` — Computation
- `test_intelligence_ceiling_physical_constants()` — Verification against formula
- `test_intelligence_ceiling_latitude_adjustment()` — Solar irradiance by latitude
- `test_intelligence_ceiling_increases_with_biodiversity()` — D_score sensitivity
- `test_intelligence_ceiling_decreases_with_temperature()` — T sensitivity
- `test_marginal_value_of_biodiversity()` — ∂I/∂D
- `test_marginal_value_curve()` — Sensitivity curves
- `test_regional_ranking()` — Comparative ranking
- `test_uncertainty_quantification()` — Confidence bounds

**Market & Mispricing Tests:**
- `test_compute_market_price()` — Component breakdown
- `test_detect_mispricing()` — Gap detection
- `test_mispricing_direction()` — Undervalued/overvalued

**Opportunity Scanning Tests:**
- `test_scan_opportunities()` — Batch scanning & ranking

**Signal & Portfolio Tests:**
- `test_generate_signal()` — STRONG_BUY/BUY/MONITOR/HOLD
- `test_portfolio_construction()` — Constrained optimization

**Repricing Catalyst Tests:**
- `test_years_to_adoption()` — Timeline estimation
- `test_regulatory_distance_score()` — Adoption proximity
- `test_repricing_impact()` — Price correction estimation
- `test_insurance_repricing_signal()` — Insurance catalyst
- `test_carbon_market_convergence_signal()` — Market integration

**Integration Tests:**
- `test_end_to_end_arbitrage_workflow()` — Full detection pipeline
- `test_backtest()` — Strategy backtesting

---

## Deployment Instructions

### Prerequisites
- Python 3.10+
- pip

### Installation

**Carbon Bridge Agent:**
```bash
cd carbon-bridge-agent
pip install -r requirements.txt
python -m pytest tests/test_core.py -v  # Run tests
python adapters/fastapi_server.py       # Start API on :8000
```

**Thermo Arbitrage Agent:**
```bash
cd thermo-arbitrage-agent
pip install -r requirements.txt
python -m pytest tests/test_core.py -v  # Run tests
python adapters/fastapi_server.py       # Start API on :8001
```

### Configuration
Both agents read from environment:
- `SUPABASE_URL` (Carbon Bridge only)
- `SUPABASE_KEY` (Carbon Bridge only)
- Optional: `.env` file in agent directory

---

## Key Innovation Points

### 1. TFAC Pricing (Carbon Bridge)
- First implementation of Intelligence Bound theorem as financial instrument
- Thermodynamically consistent valuation
- 5x premium over carbon due to irreversibility
- Addresses biodiversity loss (non-reversible) vs carbon (can be emitted again)

### 2. Arbitrage Detection (Thermo Arbitrage)
- Systematic mispricing detection via physical constants
- Repricing catalyst modeling (TNFD, insurance, carbon market)
- Expected timeline estimation (3-8 years for repricing)
- Portfolio optimization under risk constraints

### 3. Production Quality
- Full type hints (Pydantic models, async)
- Comprehensive error handling
- 2,833 lines of production code
- 250+ lines of unit tests per agent
- Real physics (Boltzmann, solar irradiance, entropy)
- Real finance (NPV, discount rates, portfolio theory)

---

## Integration Points

**Carbon Bridge connects to:**
- Evoterra agent (restoration project data)
- Viridis Science Agent (D-Score assessments)
- Sentinel/Watch agent (verification evidence)
- Viridis Trading agent (market execution)

**Thermo Arbitrage connects to:**
- Viridis Science Agent (biodiversity data)
- GaiaSim agent (climate scenarios)
- Regulatory Radar agent (TNFD/policy signals)
- EcoInvest agent (market price feeds)
- Viridis Trading agent (execution)

---

## File Locations

**Carbon Bridge Agent:**
- Agent manifest: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/carbon-bridge-agent/agent.yaml`
- Core logic: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/carbon-bridge-agent/src/core.py` (590 lines)
- TFAC engine: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/carbon-bridge-agent/src/tfac_pricing.py` (363 lines)
- Registry: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/carbon-bridge-agent/src/credit_registry.py` (474 lines)
- API: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/carbon-bridge-agent/adapters/fastapi_server.py`
- Tests: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/carbon-bridge-agent/tests/test_core.py`

**Thermo Arbitrage Agent:**
- Agent manifest: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/thermo-arbitrage-agent/agent.yaml`
- Core logic: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/thermo-arbitrage-agent/src/core.py` (607 lines)
- I_ceiling engine: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/thermo-arbitrage-agent/src/intelligence_bound.py` (398 lines)
- Repricing model: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/thermo-arbitrage-agent/src/repricing_model.py` (401 lines)
- API: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/thermo-arbitrage-agent/adapters/fastapi_server.py`
- Tests: `/sessions/sweet-zen-knuth/mnt/Agents to deploy  copy/thermo-arbitrage-agent/tests/test_core.py`

---

## Next Steps

1. **Deploy both agents** to FastAPI infrastructure
2. **Wire into agent fleet** via messaging (gRPC / MCP)
3. **Run comprehensive integration tests** against upstream agents (Science, Trading)
4. **Backtest arbitrage strategy** on 5 years of historical carbon market data
5. **Monitor TFAC market adoption** as issue volume grows
6. **Refine repricing timelines** based on regulatory momentum tracking

---

**Status:** Ready for production deployment.
