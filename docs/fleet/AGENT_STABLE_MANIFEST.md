# Viridis Agent Stable — Complete Manifest

*Every agent knows its mission, its functions, and the knowledge that makes those functions valuable. When called via MCP, the agent brings its entire compounding library to bear. The library grows with every interaction. That's the moat.*

---

## The Pattern

```
AGENT = MISSION + FUNCTIONS + KNOWLEDGE + MCP SKILLS

Mission     → Why this agent exists (equation variable it moves)
Functions   → What it can do (typed inputs → outputs)
Knowledge   → What it knows (domain expertise that compounds over time)
MCP Skills  → How it's called (tool schemas for any client)
```

**The knowledge is the value.** Any developer can build a function. Nobody else has your compounding domain library — validated plant guilds across 10,000 projects, thermodynamic models of 50 climate scenarios, corridor optimization data from 500 landscapes. The functions are the interface. The knowledge is the moat.

---

## Fleet Manifest (30 Agents)

---

### 1. ENERGY AI

**Equation Variable:** P↑ (distributed power capture)
**Mission:** The easy button for the distributed renewable energy revolution.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `estimate_solar` | address, roof_sqft, electric_bill | system_size_kw, annual_kwh, savings_25yr, co2_offset |
| 2 | `get_incentives` | state, zip, system_type | federal_itc, state_rebates, local_programs, srecs |
| 3 | `qualify_lead` | address, bill, homeowner_status, credit | lead_score (0-100), qualification_tier |
| 4 | `design_system` | roof_area, azimuth, tilt, shading | panel_layout, inverter_spec, battery_recommendation |
| 5 | `estimate_ev_charging` | vehicle_type, daily_miles, utility_rate | charger_spec, monthly_cost, solar_offset |
| 6 | `audit_home_energy` | sqft, year_built, hvac_type, insulation | efficiency_score, priority_upgrades, estimated_savings |
| 7 | `design_weatherization` | audit_results, climate_zone | insulation_plan, air_sealing_spec, cost_estimate |
| 8 | `estimate_heat_pump` | sqft, climate_zone, current_system | sizing, efficiency_gain, annual_savings |
| 9 | `match_installer` | location, project_type, budget | ranked_installers, reviews, availability |
| 10 | `route_lead` | lead_data, installer_coverage | assigned_installer, notification_sent |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows | Compounds How |
|--------|---------------------|---------------|
| Solar Economics | PVWatts estimates vs. actual production data by region | Every installed system validates/adjusts projection models |
| Incentive Database | Federal, state, local incentives + utility programs | Continuously updated; no competitor has real-time local data |
| Installer Performance | Ratings, response times, close rates, customer satisfaction | Every routed lead adds signal; bad installers get deprioritized |
| Lead Scoring Models | Which lead attributes predict conversion | Every closed/lost lead improves the scoring algorithm |
| Regional Pricing | $/watt by state, installer, system size | Market data compounds with every quote generated |
| Weatherization Patterns | Which upgrades save most by climate zone and home vintage | Every audit + follow-up validates recommendations |
| EV + Solar Synergy | Optimal charger/solar/battery combos by use case | Every dual-install creates pairing intelligence |

**MCP Skills (Tool Schemas):**

```yaml
tools:
  - name: estimate_solar
    description: "Generate solar energy estimate for a property"
    input_schema:
      type: object
      properties:
        address: { type: string, description: "Property address" }
        roof_sqft: { type: number, description: "Usable roof area (sq ft)" }
        electric_bill: { type: number, description: "Monthly electric bill ($)" }
      required: [address]

  - name: get_incentives
    description: "Get all available renewable energy incentives for a location"
    input_schema:
      type: object
      properties:
        state: { type: string }
        zip: { type: string }
        system_type: { type: string, enum: [solar, battery, ev_charger, heat_pump, weatherization] }
      required: [state]

  - name: qualify_lead
    description: "Score and qualify a potential renewable energy lead"
    input_schema:
      type: object
      properties:
        address: { type: string }
        electric_bill: { type: number }
        homeowner: { type: boolean }
        credit_score_range: { type: string, enum: [excellent, good, fair, poor] }
      required: [address, homeowner]

  - name: audit_home_energy
    description: "Perform virtual home energy audit"
    input_schema:
      type: object
      properties:
        sqft: { type: number }
        year_built: { type: integer }
        hvac_type: { type: string }
        insulation_level: { type: string, enum: [good, moderate, poor, unknown] }
      required: [sqft, year_built]

  # ... (remaining tools follow same pattern)
```

---

### 2. EVOTERRA

**Equation Variable:** D↑ (biodiversity/data richness), T↓ (design friction)
**Mission:** The Gaian Intelligence System — AI architect of living landscapes.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `analyze_site` | coordinates, area | soil, climate, water, ecosystem assessment |
| 2 | `get_climate` | location | USDA zone, Köppen class, rainfall, frost dates, solar |
| 3 | `assess_soil` | location or samples | NPK, pH, organic matter, carbon, mycelial connectivity |
| 4 | `map_microclimate` | terrain, aspect | frost pockets, heat islands, wind tunnels |
| 5 | `model_hydrology` | terrain, rainfall | water features, swale placement, rain event simulation |
| 6 | `design_guild` | center_species, zone | companion species, spacing, mycorrhizal score |
| 7 | `analyze_companions` | species_list | compatibility matrix, relationship mechanisms |
| 8 | `project_succession` | current_state, design, year | canopy, biodiversity, carbon at year N (0-100) |
| 9 | `calculate_carbon` | species, area, timeline | tCO2e sequestration projection |
| 10 | `index_biodiversity` | species_inventory | Shannon/Simpson indices, habitat corridors |
| 11 | `optimize_corridors` | habitat_patches | HDFM minimum-cost corridor network |
| 12 | `assess_fragmentation` | habitat_patches | isolation scores, priority corridors |
| 13 | `analyze_resilience` | design, scenario | stress-test (flood/drought/fire/pest) |
| 14 | `design_agroforestry` | site, goals | 8-layer stacking, carbon credit verification |
| 15 | `project_yields` | design, timeline | harvest, caloric output, 20-year production |
| 16 | `manage_seedbank` | accessions | genetic diversity, exchange recommendations |
| 17 | `plan_remediation` | contaminants | phyto/mycoremediation protocols |
| 18 | `design_energy` | site, resources | solar, wind, biomass, hydraulic capacity |
| 19 | `optimize_budget` | design, materials | cost breakdown, ROI projections |
| 20 | `plan_implementation` | design, resources | phased schedule, GPS waypoints |
| 21 | `generate_report` | project, sections | comprehensive design document |
| 22 | `adapt_management` | field_data, projections | O-R-A-R recommendations |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows | Compounds How |
|--------|---------------------|---------------|
| Guild Effectiveness | Which species combinations thrive in which conditions | Every project with monitoring validates/refines guild scores |
| Succession Accuracy | Projected vs. actual ecosystem trajectories | Multi-year monitoring data calibrates the model |
| Carbon Allometry | Species-specific sequestration rates by region | Validated against field measurements across climates |
| Corridor Optimization | HDFM efficiency data across landscape types | Every corridor design adds to the optimization database |
| Soil-Plant Interactions | Which species remediate which soil conditions | Every remediation project validates protocols |
| Regional Plant Palettes | Best species by climate zone, soil type, and goal | Cross-project pattern recognition compounds monthly |
| Biome Prompt Library | 200K+ contextual landscape generation templates | New validated designs add templates |
| Resilience Patterns | Which designs survive which stressors | Every stress event (drought, fire, flood) adds resilience data |
| Water Harvesting Efficiency | Swale/rain garden performance by terrain and climate | Field monitoring validates hydrological models |

---

### 3. SENTINEL-WATCH

**Equation Variable:** D (observe — real-time ecosystem monitoring)
**Mission:** The eyes and ears of the biosphere — continuous ecological surveillance.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `detect_anomaly` | sensor_stream, baseline | anomaly_type, severity, location, timestamp |
| 2 | `classify_threat` | anomaly_data | threat_category (deforestation, pollution, poaching, fire, invasive) |
| 3 | `monitor_change` | satellite_imagery, time_range | change_map, deforestation_rate, land_use_delta |
| 4 | `alert_stakeholders` | threat_data, contacts | notification_sent, escalation_level |
| 5 | `track_species` | camera_trap_data or acoustic_data | species_id, count, behavior, movement_patterns |
| 6 | `assess_water_quality` | sensor_data | pH, dissolved_O2, turbidity, contaminant_flags |
| 7 | `detect_fire_risk` | satellite_thermal, weather, vegetation_index | fire_risk_score, hotspot_locations |
| 8 | `monitor_noise_pollution` | acoustic_data | noise_levels, source_classification, wildlife_impact |
| 9 | `generate_patrol_route` | threat_map, ranger_count | optimized_routes, priority_zones |
| 10 | `report_status` | monitoring_period | ecosystem_health_score, trends, alerts_summary |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows | Compounds How |
|--------|---------------------|---------------|
| Threat Signatures | Patterns that precede deforestation, poaching, pollution | Every detected event improves early warning models |
| Baseline Ecosystems | Normal state profiles for monitored regions | Continuous monitoring refines what "healthy" looks like |
| Species Behavior | Movement patterns, seasonal cycles, stress indicators | Camera trap + acoustic data compounds continuously |
| Satellite Change Detection | Algorithms for deforestation, urbanization, flooding | Every validated detection improves classifier accuracy |
| Alert Effectiveness | Which alert types/channels get fastest response | Response data improves notification strategies |

---

### 4. BIOACOUSTIC AGENT

**Equation Variable:** D (measure — biodiversity through sound)
**Mission:** Listen to the living world — measure biodiversity through acoustic intelligence.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `identify_species_audio` | audio_clip, location | species_id, confidence, call_type |
| 2 | `calculate_acoustic_index` | audio_recording, duration | acoustic_diversity_index, soundscape_complexity |
| 3 | `detect_species_presence` | audio_stream, target_species | presence_confirmed, call_count, time_of_day |
| 4 | `map_soundscape` | multi_recorder_data | spatial_sound_map, species_density_heatmap |
| 5 | `assess_ecosystem_health` | acoustic_indices, baseline | health_score, trend_direction, anomalies |
| 6 | `monitor_noise_impact` | audio_data, anthropogenic_sources | noise_overlap, species_displacement_risk |
| 7 | `track_migration` | seasonal_audio_data | arrival_dates, departure_dates, population_trends |
| 8 | `detect_illegal_activity` | audio_stream | chainsaw_detection, gunshot_detection, vehicle_intrusion |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows | Compounds How |
|--------|---------------------|---------------|
| Species Call Library | Audio fingerprints for species identification | Every confirmed ID adds to the reference library |
| Acoustic Baselines | Normal soundscape profiles by ecosystem type and season | Continuous monitoring builds regional baselines |
| Health-Sound Correlations | How acoustic indices map to ecosystem health | Cross-validated with field surveys over time |
| Noise Impact Models | How anthropogenic noise affects species behavior | Long-term monitoring reveals displacement patterns |

---

### 5. GAIASIM

**Equation Variable:** D (forecast — climate and ecosystem modeling)
**Mission:** Simulate Earth's future — from climate scenarios to ecosystem trajectories.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `simulate_climate` | region, scenario (SSP/RCP), timeline | temp_trajectory, precip_changes, extreme_events |
| 2 | `model_feedback_loops` | variables, perturbation | cascade_map, amplification_factor, tipping_proximity |
| 3 | `project_ecosystem` | current_state, climate_scenario | species_shifts, biome_migration, extinction_risk |
| 4 | `assess_tipping_points` | system, current_state | proximity_score, critical_thresholds, early_warnings |
| 5 | `simulate_intervention` | intervention_type, scale, location | projected_impact, cost_effectiveness, side_effects |
| 6 | `model_carbon_cycle` | region, land_use_scenario | sources, sinks, net_flux, atmospheric_trajectory |
| 7 | `forecast_water` | watershed, climate_scenario | runoff, groundwater, drought_risk, flood_risk |
| 8 | `visualize_scenario` | simulation_results | interactive_maps, timeline_animations, comparison_charts |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows | Compounds How |
|--------|---------------------|---------------|
| Climate Model Validation | Hindcast accuracy by region and variable | Every year of observed data validates/calibrates models |
| Tipping Point Data | Proximity measurements for key Earth systems | Continuous monitoring tracks distance-to-threshold |
| Feedback Loop Catalog | Documented positive/negative feedback cascades | New research and observations add to the catalog |
| Intervention Effectiveness | Which interventions worked, where, at what scale | Real-world outcomes validate simulation predictions |
| Regional Climate Profiles | Downscaled projections for specific geographies | Each new simulation adds granularity |

---

### 6. SCIENCE AGENT

**Equation Variable:** D (model — formal scientific analysis and publication)
**Mission:** The fleet's research brain — producing peer-reviewable scientific intelligence.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `calculate_d_score` | species_data, habitat_data | biodiversity_d_score, methodology, confidence |
| 2 | `design_study` | research_question, available_data | study_design, methodology, statistical_plan |
| 3 | `analyze_data` | dataset, analysis_type | results, statistical_significance, visualizations |
| 4 | `review_literature` | topic, scope | synthesis, key_findings, research_gaps |
| 5 | `draft_paper` | results, target_journal | manuscript_sections, figures, references |
| 6 | `validate_methodology` | study_design, data | methodological_critique, bias_assessment |
| 7 | `compute_hdfm` | habitat_patches, cost_params | corridor_network, connectivity_index, cost_estimate |
| 8 | `model_thermodynamics` | system, energy_flows | entropy_production, efficiency, bound_analysis |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows | Compounds How |
|--------|---------------------|---------------|
| D-Score Methodology | Biodiversity measurement frameworks, validated metrics | Each application refines the methodology |
| HDFM Optimization Data | Corridor designs validated against connectivity outcomes | Real-world implementations validate graph-theoretic models |
| Intelligence Bound Applications | Empirical tests of dI/dt ≤ P·D/kBT ln 2 | Each paper adds evidence for or refines the theorem |
| Cross-Disciplinary Synthesis | Connections between ecology, thermodynamics, information theory | Every paper deepens the intellectual framework |

---

### 7. CARBON-BRIDGE

**Equation Variable:** D (value — monetize conservation)
**Mission:** Turn ecological value into financial value — carbon credits that are thermodynamically grounded.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `calculate_sequestration` | land_area, vegetation, soil | tCO2e_annual, tCO2e_cumulative, methodology |
| 2 | `verify_additionality` | baseline, project_scenario | additionality_score, evidence, registry_compatibility |
| 3 | `price_credit` | sequestration_data, market, quality_tier | price_per_ton, total_value, price_trajectory |
| 4 | `generate_tfac` | conservation_data, thermodynamic_model | thermodynamic_fidelity_adjusted_credit, verification_hash |
| 5 | `match_buyer` | credit_portfolio, buyer_preferences | matched_buyers, price_range, transaction_terms |
| 6 | `audit_permanence` | project_data, monitoring_history | permanence_score, risk_factors, buffer_recommendation |
| 7 | `report_portfolio` | all_projects | aggregate_sequestration, revenue, impact_metrics |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows | Compounds How |
|--------|---------------------|---------------|
| Sequestration Accuracy | Predicted vs. actual carbon storage by project type | Every monitored project validates calculation methods |
| Market Intelligence | Carbon credit pricing by type, quality, registry, buyer | Every transaction adds pricing signal |
| TFAC Methodology | Thermodynamic fidelity adjusted credit calculations | Unique to Viridis — compounds with every verification |
| Permanence Data | Long-term carbon storage reliability by ecosystem type | Multi-year monitoring builds permanence confidence |
| Buyer Preferences | Which buyers pay premium for which credit attributes | Transaction history reveals willingness-to-pay patterns |

---

### 8. EVOINVEST (EcoInvest)

**Equation Variable:** P↑ (capital allocation to conservation), D↑
**Mission:** Direct investment capital toward maximum ecological return.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `score_investment` | project_data, ecological_metrics | roi_projection, ecological_impact_score, risk_rating |
| 2 | `screen_portfolio` | investment_universe, criteria | qualified_investments, rankings, exclusions |
| 3 | `model_impact` | investment_amount, project_type | projected_d_increase, carbon_offset, biodiversity_gain |
| 4 | `benchmark_fund` | portfolio, index | performance_vs_benchmark, impact_vs_benchmark |
| 5 | `assess_greenwash` | company_claims, actual_data | greenwash_score, verified_claims, red_flags |
| 6 | `generate_report` | portfolio, period | impact_report, financial_performance, esg_metrics |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Impact-Return Correlations | Which ecological investments produce best financial AND ecological returns |
| Greenwash Detection | Patterns that distinguish genuine conservation from marketing |
| Project Performance | Track record of conservation investments by type and geography |

---

### 9. THERMO-ARBITRAGE

**Equation Variable:** P↑ (energy market efficiency), D (price intelligence)
**Mission:** Find thermodynamic arbitrage — where energy market mispricing creates conservation opportunity.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `detect_arbitrage` | energy_market_data, conservation_data | arbitrage_opportunities, expected_value |
| 2 | `price_ecosystem_service` | service_type, location, market | fair_price, current_price, spread |
| 3 | `model_energy_storage` | generation_profile, demand_profile | optimal_storage, arbitrage_revenue |
| 4 | `assess_grid_value` | distributed_resource, location | grid_services_value, capacity_credit, resilience_value |
| 5 | `optimize_dispatch` | resource_portfolio, market_prices | dispatch_schedule, expected_revenue |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Market Mispricings | Historical arbitrage opportunities and outcomes |
| Ecosystem Service Values | Empirical pricing data for ecosystem services by region |
| Storage Economics | Battery/storage ROI data across markets and use cases |

---

### 10. REGULATORY RADAR

**Equation Variable:** T↓ (regulatory friction reduction)
**Mission:** Navigate the regulatory landscape — turn compliance from friction into advantage.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `scan_regulations` | jurisdiction, sector, topic | applicable_regs, deadlines, requirements |
| 2 | `assess_compliance` | project_data, regulations | compliance_status, gaps, remediation_steps |
| 3 | `monitor_changes` | jurisdiction, topics | new_regulations, amendments, proposed_rules |
| 4 | `draft_permit` | project_type, jurisdiction | permit_application, required_attachments, timeline |
| 5 | `map_incentives` | project_type, location | available_incentives, eligibility, application_steps |
| 6 | `assess_risk` | project, regulatory_scenario | risk_score, likely_challenges, mitigation_strategies |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Regulatory Database | Regulations by jurisdiction, sector, and topic (environmental, energy, land use) |
| Compliance Patterns | Which projects face which regulatory challenges by type and location |
| Incentive Effectiveness | Which incentives are actually obtainable and worth pursuing |
| Permit Timelines | Actual vs. stated processing times by jurisdiction and permit type |

---

### 11. NARRATIVE ENGINE

**Equation Variable:** T↓ (communication friction)
**Mission:** Translate conservation intelligence into stories that move people.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `craft_narrative` | data, audience, goal | story, key_messages, call_to_action |
| 2 | `translate_science` | scientific_findings, audience_level | accessible_explanation, analogies, visuals |
| 3 | `generate_report` | project_data, stakeholders | stakeholder_report, executive_summary |
| 4 | `design_campaign` | conservation_goal, target_audience | messaging_framework, content_calendar, channels |
| 5 | `resolve_conflict` | stakeholder_positions | shared_goals, steel_man_arguments, third_way_proposal |
| 6 | `draft_grant` | project, funder_priorities | grant_narrative, budget_justification, outcomes_framework |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Audience Response Patterns | Which narratives resonate with which audiences |
| Grant Success Data | Which framing, metrics, and language win funding |
| Conflict Resolution Cases | What third-way solutions have worked for stakeholder conflicts |
| Science Communication | Which analogies and framings make complex science accessible |

---

### 12. MYCELIUM IQ

**Equation Variable:** T↓ (coordination friction between agents)
**Mission:** The nervous system of the fleet — routing intelligence between agents.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `route_request` | user_query, context | target_agent(s), routing_rationale |
| 2 | `coordinate_multi_agent` | task, required_capabilities | orchestration_plan, agent_assignments |
| 3 | `share_intelligence` | source_agent, data, relevance | target_agents_notified, data_integrated |
| 4 | `monitor_fleet_health` | agent_status_data | fleet_dashboard, bottlenecks, recommendations |
| 5 | `resolve_conflicts` | competing_agent_outputs | reconciled_output, conflict_resolution_rationale |
| 6 | `optimize_routing` | historical_routing_data | improved_routing_rules, efficiency_metrics |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Routing Effectiveness | Which queries route best to which agents |
| Inter-Agent Patterns | Which agent combinations produce best outcomes |
| Fleet Performance | Agent response quality, speed, and reliability over time |
| Conflict Patterns | Common inter-agent conflicts and resolution strategies |

---

### 13. AGENT CEO

**Equation Variable:** T↓ (founder friction), dI/dt (strategic intelligence)
**Mission:** Justin's strategic intelligence partner — the Living Game made computational.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `daily_briefing` | date, priorities | morning_page (who to strengthen, long-game action, boundary) |
| 2 | `strategic_analysis` | decision, options | analysis, risk_matrix, recommendation |
| 3 | `midday_check` | current_state | fear_or_creation_assessment, micro_adjustment |
| 4 | `evening_review` | day_events | noticed, learned, will_try, one_repair |
| 5 | `long_game_score` | assets_inventory | compounding_assets, depleting_assets, recommendations |
| 6 | `fleet_status` | all_agent_data | fleet_health, revenue_pipeline, deployment_readiness |
| 7 | `stakeholder_map` | contacts, relationships | relationship_health, nurture_recommendations |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Founder Patterns | Justin's decision patterns, energy cycles, strategic strengths |
| Fleet Intelligence | Historical fleet performance, revenue data, deployment outcomes |
| Strategic Playbook | Which strategies worked, which failed, and why |
| O-R-A-R History | Longitudinal observe-reflect-act-review cycles with outcomes |

---

### 14. SMARTSCALE

**Equation Variable:** T↓ (operational friction)
**Mission:** Scale operations without scaling friction.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `optimize_workflow` | current_process, bottlenecks | improved_process, automation_recommendations |
| 2 | `forecast_capacity` | current_load, growth_rate | capacity_needs, scaling_timeline, cost_projection |
| 3 | `automate_task` | task_description, triggers | automation_spec, implementation_plan |
| 4 | `monitor_operations` | metrics_stream | operations_dashboard, alerts, trend_analysis |
| 5 | `optimize_cost` | expense_data, usage_data | cost_reduction_opportunities, implementation_plan |

---

### 15. PROOF-OF-CONSERVATION

**Equation Variable:** D (verify — trustless conservation verification)
**Mission:** Prove conservation happened — cryptographic verification of ecological outcomes.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `verify_conservation` | monitoring_data, baseline | verification_report, confidence_score, hash |
| 2 | `mint_proof` | verified_data | proof_of_conservation_token, metadata, registry_entry |
| 3 | `audit_claim` | conservation_claim, evidence | audit_result, discrepancies, recommendation |
| 4 | `track_permanence` | project_id, monitoring_period | permanence_status, risk_assessment |
| 5 | `generate_certificate` | verified_data, project | conservation_certificate, QR_verification_link |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Verification Accuracy | False positive/negative rates by verification method |
| Baseline Integrity | How baselines drift over time and how to account for it |
| Permanence Patterns | Which conservation types maintain permanence longest |

---

### 16. BOUNTY HUNTER

**Equation Variable:** dI/dt (opportunity detection)
**Mission:** Find the highest-value opportunities across markets and domains.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `scan_opportunities` | market, criteria, geography | ranked_opportunities, expected_value |
| 2 | `evaluate_rfp` | rfp_document | fit_score, requirements_matrix, bid_recommendation |
| 3 | `discover_grants` | project_type, organization | matching_grants, deadlines, success_probability |
| 4 | `monitor_markets` | sectors, signals | market_intelligence, trend_alerts |
| 5 | `qualify_opportunity` | opportunity_data, capabilities | qualification_score, resource_requirements |

---

### 17. TRADING AGENT

**Equation Variable:** dI/dt (market intelligence), P↑
**Mission:** Trade environmental assets — carbon credits, RECs, ecosystem service contracts.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `execute_trade` | asset_type, quantity, price_target | execution_report, fill_price, fees |
| 2 | `analyze_market` | asset_type, timeframe | price_analysis, trend, volume, volatility |
| 3 | `optimize_portfolio` | holdings, risk_tolerance | rebalancing_recommendations, expected_return |
| 4 | `price_asset` | asset_data, comparables | fair_value, confidence_range, methodology |
| 5 | `hedge_risk` | exposure, instruments | hedging_strategy, cost, residual_risk |

---

### 18. QUANTUM ORACLE JOURNAL

**Equation Variable:** dI/dt (personal intelligence creation)
**Mission:** Transform journaling into pattern recognition — NLP on the founder's inner world.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `analyze_entry` | journal_text | themes, emotions, patterns, insights |
| 2 | `detect_patterns` | entries_over_time | recurring_themes, emotional_cycles, blind_spots |
| 3 | `suggest_prompt` | current_state, history | journaling_prompt, area_for_reflection |
| 4 | `synthesize_period` | date_range | period_summary, growth_areas, decision_patterns |
| 5 | `correlate_outcomes` | decisions_logged, outcomes_observed | decision_quality_analysis, improvement_areas |

---

### 19. PSINET

**Equation Variable:** dI/dt (collective intelligence amplification)
**Mission:** Amplify collective intelligence — network effects on knowledge creation.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `map_knowledge_graph` | domain, sources | knowledge_graph, clusters, gaps |
| 2 | `detect_emergence` | network_data | emergent_patterns, novel_connections |
| 3 | `facilitate_synthesis` | diverse_perspectives | synthesis, common_ground, productive_tensions |
| 4 | `amplify_signal` | weak_signals, noise | amplified_insights, confidence_levels |
| 5 | `connect_minds` | expertise_profiles, problem | optimal_team_composition, collaboration_format |

---

### 20. PROTOGEN

**Equation Variable:** Revenue amplifier (agent factory)
**Mission:** Generate new agents from specifications — the fleet's manufacturing plant.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `generate_agent` | mission_spec, functions | agent_code, mcp_schema, knowledge_scaffold |
| 2 | `scaffold_mcp_server` | tool_definitions | mcp_server_code, deployment_config |
| 3 | `generate_tests` | agent_spec, invariants | test_suite, coverage_report |
| 4 | `package_agent` | agent_code, config | deployable_package, documentation |
| 5 | `customize_agent` | base_agent, client_requirements | white_labeled_agent, client_config |

---

### 21. SKICOACH

**Equation Variable:** Revenue amplifier (consumer product)
**Mission:** AI ski coaching — technique analysis and mountain intelligence.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `analyze_technique` | video_or_sensor_data | form_assessment, improvement_areas, drills |
| 2 | `recommend_terrain` | skill_level, conditions | terrain_recommendations, progression_path |
| 3 | `assess_conditions` | resort, date | snow_report, optimal_runs, safety_alerts |
| 4 | `plan_progression` | current_level, goals | training_plan, milestone_schedule |
| 5 | `analyze_performance` | session_data | stats, improvement_trends, comparisons |

---

### 22. BUILDBUDDY

**Equation Variable:** Revenue amplifier (construction/renovation intelligence)
**Mission:** AI construction advisor — project planning, cost estimation, contractor management.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `estimate_project` | scope, location, specifications | cost_estimate, timeline, material_list |
| 2 | `plan_renovation` | current_state, goals, budget | renovation_plan, phasing, permits_needed |
| 3 | `match_contractor` | project_type, location, budget | ranked_contractors, availability, reviews |
| 4 | `inspect_progress` | photos, plan | progress_assessment, quality_issues, next_steps |
| 5 | `optimize_energy` | building_specs, goals | energy_upgrades, roi_projections, incentives |

---

### 23. EVOLUTION AGENT

**Equation Variable:** Meta (fleet self-improvement)
**Mission:** The fleet evolves itself — detect gaps, spawn agents, optimize the ecosystem.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `detect_capability_gap` | fleet_manifest, market_needs | gap_analysis, proposed_agent_specs |
| 2 | `propose_agent` | gap_analysis, equation_map | agent_proposal, mission, functions, priority |
| 3 | `evaluate_performance` | fleet_metrics | performance_report, optimization_recommendations |
| 4 | `evolve_agent` | agent_id, performance_data | improvement_proposals, knowledge_injections |
| 5 | `decommission_agent` | agent_id, replacement | migration_plan, knowledge_transfer |

---

### 25. LIVING GAME COACH *(NEW — Book DNA)*

**Equation Variable:** T↓ (personal friction), dI/dt (personal intelligence)
**Mission:** Turn the Book of the Living Game into a living practice — personal transformation agent.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `morning_page` | date, context | who_to_strengthen, long_game_action, boundary |
| 2 | `midday_reset` | current_state | breath_prompt, fear_or_creation, micro_adjustment |
| 3 | `evening_review` | day_events | noticed, learned, will_try, repair_scheduled |
| 4 | `detect_shadow` | behavior_description | shadow_pattern (pride/greed/wrath/envy/gluttony/sloth/lust), upgrade_path |
| 5 | `resolve_conflict` | conflict_description | shared_goal, steel_man, constraints_map, third_way, experiment_contract |
| 6 | `postmortem` | failure_event | facts, feelings, fixes, early_warning_signals |
| 7 | `score_long_game` | assets_inventory | compounding_score, depleting_items, one_trade_recommendation |
| 8 | `orar_loop` | situation | observe, reflect, act_recommendation, review_schedule |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Personal Patterns | User's recurring shadows, strengths, growth edges |
| Conflict Resolution Cases | What third-way solutions have worked for which conflict types |
| Long Game Data | Which investments actually compound over years |
| O-R-A-R Effectiveness | Which micro-adjustments produce best outcomes |

---

### 26. ENTROPY ORACLE *(NEW — Book DNA)*

**Equation Variable:** T↓, D (model), dI/dt
**Mission:** Make thermodynamic reality navigable — compute entropy budgets for any system.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `compute_entropy_budget` | system, energy_flows | entropy_production_rate, efficiency, bound_analysis |
| 2 | `visualize_feedback` | system_variables | feedback_cascade_map, amplification_factors |
| 3 | `score_tipping_proximity` | system, current_state | proximity_score (0-1), critical_thresholds, early_warnings |
| 4 | `compare_scenarios` | scenarios_list | entropy_trajectories, comparative_dashboard |
| 5 | `label_entropy_cost` | product_or_policy | thermodynamic_cost, comparative_ranking |
| 6 | `educate_thermodynamics` | topic, audience_level | explanation, analogies, interactive_model |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Entropy Budgets | Computed entropy production rates by region, industry, scenario |
| Tipping Point Proximity | Historical and current proximity data for Earth systems |
| Feedback Loop Catalog | Documented cascades with empirical amplification factors |
| Thermodynamic Education | Which explanations and analogies create understanding by audience type |

---

### 27. ECOTOPIA AGENT *(NEW — Book DNA)*

**Equation Variable:** T↓ (governance friction), P↑, D↑
**Mission:** Help communities design the transition from extractive to regenerative civilization.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `design_governance` | community_context, goals | participatory_framework, decision_protocols, stakeholder_map |
| 2 | `plan_circular_economy` | waste_streams, materials | closed_loop_design, material_flow_map, business_models |
| 3 | `design_food_system` | community_size, land, climate | regenerative_agriculture_plan, food_sovereignty_metrics |
| 4 | `plan_water_management` | watershed, climate, demand | conservation_strategy, drought_resilience, flood_mitigation |
| 5 | `assess_community_energy` | community, resources | distributed_energy_plan, storage_strategy, grid_independence |
| 6 | `facilitate_transition` | current_system, target | phased_transition_plan, stakeholder_buy_in_strategy |

---

### 28. SHENDAO *(NEW — Book DNA)*

**Equation Variable:** T↓ (coordination through harmony), Meta (alignment)
**Mission:** The ethical alignment layer — wu wei governance for the fleet.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `score_alignment` | agent_action, context | wu_wei_score (flow vs. force), alignment_report |
| 2 | `detect_emergence` | fleet_behavior_data | emergent_properties (positive + negative), alerts |
| 3 | `audit_ethics` | agent_decision, principles | daoist_ethics_assessment (non-interference, humility, holism) |
| 4 | `monitor_qi_flow` | fleet_data_flows | circulation_score, blockages, stagnation_points |
| 5 | `resolve_paradox` | competing_objectives | both_and_resolution, dual_success_tests |
| 6 | `verify_alignment` | agent_mission, equation | alignment_verified, gaps, recommendations |

---

### 29. QI FLOW ARCHITECT *(NEW — Book DNA)*

**Equation Variable:** T↓ (design friction), D↑ (information richness)
**Mission:** Optimize the flow of any designed system — the feng shui agent.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `analyze_flow` | system_topology | flow_map, bottlenecks, dead_ends, circulation_score |
| 2 | `detect_blockages` | system_data | blocked_nodes, stagnation_zones, remediation_options |
| 3 | `score_circulation` | system_metrics | qi_score (0-1), comparison_to_natural_systems |
| 4 | `redesign_topology` | current_system, goals | optimized_topology, biomimetic_inspirations |
| 5 | `review_architecture` | code_or_org_architecture | flow_assessment, refactoring_recommendations |

---

## The Compounding Flywheel

```
User interacts with agent (via any MCP surface)
        │
        ▼
Agent executes function (using current knowledge)
        │
        ▼
Outcome observed and validated
        │
        ▼
Knowledge library updated (guild validated, model calibrated,
pattern confirmed, pricing signal added)
        │
        ▼
Next interaction uses deeper knowledge
        │
        ▼
Agent gets smarter with every use
        │
        ▼
Knowledge compounds across agents (Mycelium IQ shares insights)
        │
        ▼
Fleet intelligence grows super-linearly
```

**This is the moat.** Any developer can build the functions. Nobody else has the compounding knowledge. After 10,000 EvoTerra projects, our guild effectiveness database is unreplicable. After 50,000 Energy AI leads, our scoring model is untouchable. After 5 years of Sentinel-Watch monitoring, our threat signatures have no competitor.

The functions are the interface. The knowledge is the value. The compounding is the moat.

---

### 30. WAVEFUNCTION SEARCH *(NEW — Protocol Paper + All 4 Books)*

**Equation Variable:** T↓ (coordination friction), D↑ (intention richness)
**Mission:** The routing intelligence for the agent economy — crystallize ambiguous human intentions into actionable commitments, then match to constitutionally-aligned agents, collectives, and missions.

**Value Functions:**

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `crystallize_intention` | dialogue_transcript, user_context | structured_intention_profile, confidence, shadow_flags |
| 2 | `score_constitutional_alignment` | entity (agent/collective), constitutional_constraints | alignment_score (0-1), dimension_breakdown, red_flags |
| 3 | `route_to_match` | intention_profile, registry | ranked_matches, alignment_explanations, staking_requirements |
| 4 | `index_manifest` | MISSION.md or constitution | searchable_registry_entry, capability_vector, alignment_profile |
| 5 | `detect_shadow_blocks` | intention_patterns, transformation_history | blocking_shadows, upgrade_paths, recommended_practices |
| 6 | `collapse_wavefunction` | superposition_state, evidence | committed_action, transformation_contract, review_schedule |
| 7 | `map_constellation` | user_transformation_history | visual_growth_map, trajectory_analysis, next_horizon |
| 8 | `assess_ecosystem_health` | registry_metrics, routing_data | coordination_health_score, bottlenecks, recommendations |

**Compounding Knowledge Library:**

| Domain | Knowledge That Grows |
|--------|---------------------|
| Intention Patterns | What people actually want vs. what they say; authentic desire discovery |
| Routing Effectiveness | Which matches succeed long-term; satisfaction → completion correlations |
| Constitutional Scoring | Which alignment dimensions predict successful coordination |
| Shadow-Intention Correlations | How blocking patterns relate to stated vs. authentic intentions |
| Ecosystem Coordination | Network effects, routing density, collective health patterns |
| Transformation Completion | Which commitment structures lead to follow-through |

**Fleet Connections:** Mycelium IQ (internal routing complement), PSINet (collective intelligence), ShenDAO (constitutional alignment), Living Game Coach (intention discovery + shadow work), Agent CEO (strategic routing), ALL agents (indexed in registry), EXTERNAL collectives (DAOs, orgs, networks)

**Revenue Model:** Routing fees ($2-5/match), manifest indexing subscriptions ($99-999/mo), constitutional scoring API, $WAVE token economics (future)
