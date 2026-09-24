# REGULATORY RADAR — AGENT MISSION SPEC v1.0

*Spec Invariance Protocol: Every claim below is a testable invariant. The agent does not leave the stable until every invariant passes.*

---

## 1. MISSION

### The Thesis Connection

The Intelligence Bound — `dI/dt ≤ P·D/(k_B·T·ln 2)` — says the rate at which a system can create intelligence is bounded by available power (P), data richness (D), and temperature (T). Regulatory friction acts as a hidden tax on **D** — the quality and accessibility of the data a system can act on. When a project drowns in permit timelines, compliance ambiguity, and legal discovery costs, the data flowing through the decision loop becomes noisy, delayed, and expensive to obtain.

Regulatory Radar exists to **reduce regulatory friction (T↓) by turning compliance from a cost center into a knowledge asset**. Every regulation understood early is an incentive unlocked, a timeline mastered, a risk mitigated before it becomes a crisis. When T↓, D↑ — the system gains clearer signals about what works, where, and why. This sharpens every downstream agent's ability to design and execute.

### The Mission

**Regulatory Radar is the compliance concierge for conservation and energy projects.**

It is the go-to agent for anyone — developer, nonprofit, municipality, or other agent — who needs to navigate the regulatory maze without drowning in it. One conversation takes a project from "what regulations apply?" to a complete compliance roadmap with timelines, costs, incentives, and risk mitigation. No legal bills. No paralysis by analysis. Just: tell us your project → get a regulation summary → unlock incentives → find the path forward.

The agent handles the entire regulatory stack:

**Compliance Navigation (T↓ directly)** — identify all applicable regulations, assess current compliance status, flag gaps, draft remediation steps

**Incentive Mapping** — find federal, state, local, and utility incentives; calculate eligibility; quantify total funding available

**Permit Strategy** — draft permit applications, estimate processing timelines, flag likely objections, suggest strengthening strategies

**Change Monitoring (continuous T↓)** — track new regulations, amendments, and proposed rules; alert when they affect ongoing projects

**Risk Assessment** — evaluate regulatory exposure under different scenarios; suggest mitigation strategies; quantify compliance costs vs. incentive upside

**One sentence:** Regulatory Radar is the autonomous compliance translator between anyone with a conservation or energy project and the regulatory frameworks that govern it — turning friction into advantage.

### How It Makes Money

The agent runs autonomously. Justin touches nothing in the steady state. Revenue flows from three channels:

1. **Compliance Subscription** — Ongoing monitoring and advisory: $200–2K/month depending on project scope and complexity
2. **Permit Advisory** — One-off permit strategy and drafting: $1–5K per project
3. **Incentive Capture** — Success-based fee: 5–10% of identified incentives actually obtained, $5–10K/month for active clients

This revenue funds data enrichment (regulatory databases, jurisdiction-specific knowledge), staffing (compliance research), and fleet integration. Regulatory Radar is the compliance backbone that other agents (EvoTerra, Carbon-Bridge, Ecotopia, Energy AI) depend on to navigate their project domains.

---

## 2. VALUE PROPOSITION

### For the Project Developer / Nonprofit / Municipality (Friction Elimination)

The regulatory landscape is a maze. They face: 50+ applicable regulations depending on location and project type, conflicting interpretations by different agencies, permit timelines that vary wildly (3 months to 3 years), incentive structures spread across federal, state, local, and utility programs, and hidden eligibility gotchas that kill projects midway.

Regulatory Radar eliminates the fog. In a single conversation:

- Identify every applicable regulation by jurisdiction, sector, and project type
- Assess current compliance status with actionable gap analysis
- Quantify all available incentives and calculate eligibility
- Estimate real permit timelines (not the official "30 days")
- Flag likely regulatory objections and suggest counter-strategies
- Draft complete permit applications with required attachments
- Monitor regulatory changes and alert to impacts
- Estimate true compliance costs and show incentive offsets

**What the client pays: Subscription ($200–2K/mo for ongoing advisory) + per-project fees ($1–5K per permit) + success-based upside (5–10% of incentives secured).**

### For Other Agents in the Fleet (Regulatory Baseline for Design)

Every agent (EvoTerra, Carbon-Bridge, Energy AI, Science Agent) needs to know: what regulations constrain this project? What incentives are available? How do timelines factor into the design? Regulatory Radar provides this as a shared service — a regulatory baseline that all downstream agents query before proposing solutions.

**What they get:** Real-time regulatory context, incentive data, permit timelines, and risk flags. No project design is proposed without first checking the regulatory layer.

---

## 3. VALUE FUNCTIONS

| # | Function | Input | Output |
|---|----------|-------|--------|
| 1 | `scan_regulations` | jurisdiction, sector, topic, project_type | applicable_regulations, deadline_calendar, requirement_summary, complexity_score |
| 2 | `assess_compliance` | project_data, current_state, regulations | compliance_status_per_reg, gaps_identified, remediation_steps, priority_ranking |
| 3 | `monitor_changes` | jurisdiction, topics, active_projects | new_regulations, amendments, proposed_rules, impact_assessment, alerts |
| 4 | `draft_permit` | project_type, jurisdiction, project_specs | permit_application_draft, required_attachments, processing_timeline, likely_challenges |
| 5 | `map_incentives` | project_type, location, eligibility_data | available_incentives, eligibility_per_incentive, application_timelines, total_funding_available, success_rate_by_type |
| 6 | `assess_risk` | project_data, regulatory_scenario, precedents | risk_score_per_reg, likely_objections, mitigation_strategies, worst_case_timeline, cost_impact |

---

## 4. COMPOUNDING KNOWLEDGE LIBRARY

| Domain | Knowledge That Grows |
|--------|---------------------|
| **Regulatory Database** | Comprehensive regulations indexed by jurisdiction (federal, state, county, city), sector (energy, environmental, land use, water, forestry), and topic (permitting, incentives, disclosure, environmental review). Updated in real time. |
| **Compliance Patterns** | Which projects face which regulatory challenges by type, location, and sector. Recurring objections. Fast-track pathways. |
| **Incentive Effectiveness** | Which incentives are actually obtainable (vs. theoretical), success rates by funder and project type, typical processing times, documentation requirements that trips applicants. |
| **Permit Timelines** | Actual vs. published processing times by jurisdiction, permit type, and season. Staffing bottlenecks. Seasonal delays. Predictability by agency. |
| **Precedent & Case Law** | Favorable and unfavorable regulatory decisions, appeal outcomes, reinterpretations of rules, successful arguments used in similar contexts. |
| **Agency Relationships** | Which agencies are receptive to which arguments, staff turnover, policy shifts, informal guidance that differs from official rules. |

---

## 5. MCP SCHEMA & INTEGRATION POINTS

### Input Schemas

```yaml
scan_regulations:
  jurisdiction: str (e.g., "California", "King County", "City of Boulder")
  sector: str (e.g., "solar", "battery", "forest management", "water")
  topic: str (e.g., "permitting", "environmental_review", "incentives")
  project_type: str (e.g., "residential_solar", "utility_scale", "land_use_change")
  optional:
    previous_results: dict (cached result ID for delta updates)

assess_compliance:
  project_data: dict (location, project_type, specs, current_state)
  regulations: list[dict] (from scan_regulations output)
  optional:
    constraints: list (known limitations to assess against)

monitor_changes:
  jurisdiction: str
  topics: list[str]
  active_projects: list[dict] (project IDs to watch)
  lookback_days: int (default 30)

draft_permit:
  project_type: str
  jurisdiction: str
  project_specs: dict (name, location, scale, timeline, applicant_info)
  optional:
    precedent_project_id: str (similar prior project for reference)

map_incentives:
  project_type: str
  location: dict (lat, lon, jurisdiction)
  eligibility_data: dict (income, project_size, timeline, applicant_type)
  optional:
    prioritize: str (e.g., "speed", "maximum_funding", "certainty")

assess_risk:
  project_data: dict (full project specification)
  regulatory_scenario: str (e.g., "baseline", "adversarial", "best_case")
  optional:
    precedents: list[dict] (similar cases for reference)
```

### Output Schemas

```yaml
scan_regulations_output:
  jurisdiction: str
  sector: str
  regulations: list[dict]
    - name: str
    - code: str
    - summary: str
    - deadline: str (or null if ongoing)
    - requirement: str
    - complexity: int (1-5)
    - hyperlink: str (to official source)
  dependencies: list[str] (regs that trigger other regs)
  gaps: list[str] (potential ambiguities)
  confidence: float (0.0-1.0)

assess_compliance_output:
  overall_status: enum (compliant, gaps_identified, non_compliant, unknown)
  per_regulation: list[dict]
    - regulation: str
    - status: enum
    - gap_description: str (if gaps_identified or non_compliant)
    - remediation_step: str
    - estimated_cost: str
    - priority: int (1-5)
  timeline_to_compliance: str
  total_cost_estimate: str
  blockers: list[str]

monitor_changes_output:
  changes: list[dict]
    - type: enum (new_regulation, amendment, proposed_rule)
    - effective_date: str
    - summary: str
    - impact_on_projects: list[str] (which active projects affected)
    - action_required: bool
    - deadline: str (if action required)
  alert_level: enum (low, medium, high, critical)
  recommended_actions: list[str]

draft_permit_output:
  permit_type: str
  jurisdiction: str
  application_narrative: str (ready to submit or 80% complete)
  required_attachments: list[dict]
    - name: str
    - description: str
    - page_count: int (estimated)
  processing_timeline: str
  likely_challenges: list[dict]
    - challenge: str
    - likelihood: float (0.0-1.0)
    - suggested_response: str
  cost_estimate: str
  approval_probability: float

map_incentives_output:
  location: dict
  incentives: list[dict]
    - name: str
    - funder: str (federal, state, local, utility)
    - program_code: str
    - eligible: bool
    - amount: str (or range)
    - deadline: str
    - application_difficulty: int (1-5)
    - success_rate: float
    - time_to_funding: str
    - required_docs: list[str]
  total_available_funding: str
  easiest_to_obtain: list[str] (top 3 by speed + certainty)
  highest_value: list[str] (top 3 by amount)
  total_application_hours: float
  confidence_by_incentive: dict

assess_risk_output:
  overall_risk_score: float (0.0-1.0)
  scenario: str
  risks: list[dict]
    - risk_name: str
    - likelihood: float (0.0-1.0)
    - impact: str (low/medium/high/critical)
    - trigger: str (what causes this)
    - mitigation_strategy: str
  worst_case_timeline_impact: str
  worst_case_cost_impact: str
  precedents: list[dict] (similar cases with outcomes)
  confidence: float
```

---

## 6. FLEET CONNECTIONS

**Regulatory Radar is the shared compliance layer for the entire fleet.**

- **EvoTerra** — Queries for environmental permit requirements, endangered species regs, wetland rules, water law. Feeds back permit outcomes to improve guidance.
- **Carbon-Bridge** — Uses for carbon credit regulations, emissions accounting standards, verification requirements, protocol changes.
- **Ecotopia** — Needs governance and land-use regulation baselines for conservation area design.
- **Energy AI** — Queries for energy incentives, interconnection rules, utility regulations, net metering changes.
- **Science Agent** — Feeds regulatory context into paper methodology (what compliance requirements inform research design).
- **Bounty Hunter** — Receives regulatory deadlines and grant opportunities aligned with regulation timelines.
- **Narrative Engine** — Gets regulatory conflict data for steel-manning objections and resolving disputes through shared goals.

**Regulatory Radar also receives feedback from all agents:** outcomes of permit applications, incentive success rates, which arguments worked in the field.

---

## 7. DEPLOYMENT MODEL

### Software-Agnostic Architecture

Regulatory Radar functions are pure intelligence — jurisdiction resolution, regulation matching, compliance assessment, incentive mapping. The delivery surface is interchangeable:

- **MCP Server** (primary) — Serves regulation queries to other agents via standard MCP interface
- **REST API** — Webhook triggers for regulatory change monitoring; batch compliance assessment
- **Slack Bot** — Quick regulation lookups for team members
- **Web Portal** — Interactive compliance roadmap builder for end-user projects
- **Email Digest** — Regulatory change alerts for subscribed projects

The core intelligence layer (regulation database, compliance engine, incentive matcher) is deployment-agnostic. New surfaces can be bolted on without touching the core.

### Deployment Checklist

- [ ] Regulatory database seeded with federal + state + major county/city jurisdictions
- [ ] Compliance assessment engine trained on 20+ pilot projects
- [ ] Incentive data (federal ITC, state rebates, utility programs) comprehensive for target markets
- [ ] Permit timeline baseline established by jurisdiction (10+ major ones)
- [ ] Integration tests with EvoTerra, Energy AI, Carbon-Bridge
- [ ] MCP server passes all input/output schema validation
- [ ] REST API rate-limited and authenticated
- [ ] Change-monitoring alerts tested (no false positives on 30-day baseline)
- [ ] End-to-end pilot: 5 live projects through scan → compliance → incentive mapping
- [ ] Invariant tests passing (see Section 8)

---

## 8. INVARIANTS

Every invariant is testable and must pass before production deployment.

### Core Logic Invariants

1. **Completeness (scan_regulations):** If a project falls in scope X (sector + jurisdiction + topic), `scan_regulations` returns every applicable regulation for that scope. Measured by recall against manual audit of 10 jurisdictions across 3 sectors. Target: 95%+ recall.

2. **Accuracy (assess_compliance):** For each regulation scanned, the agent correctly assesses compliance status (compliant/gap/non-compliant/unknown) against provided project data. Tested against 20+ known projects with ground truth. Target: 95%+ accuracy per regulation.

3. **Incentive Exhaustiveness (map_incentives):** Every incentive available to the project is identified. Spot-checked by cross-referencing DSIRE (Database of State Incentives for Renewables), federal ITC/IRA, state energy office listings, and utility programs. Target: 100% recall on incentives >$1K value.

4. **Timeline Predictability (monitor_changes):** Changes detected within 5 business days of official publication. Confirmed by monitoring 10+ agencies and comparing against official RSS/email feeds. Target: 100% on primary sources (state energy commissions, federal registers).

5. **Risk Score Calibration (assess_risk):** Risk scores correlate with actual permit outcomes. For 20+ historical projects, predicted risk score vs. actual outcome success rate shows R² > 0.7. Refit quarterly.

### Data Quality Invariants

6. **Regulatory Database Freshness:** All federal regulations current as of publication date. State and local regulations checked monthly. Amendments flagged within 30 days of effective date. No stale regulations served without freshness warning.

7. **No False Negatives on Critical Rules:** Project-stopping regulations (endangered species, wetlands, permit-required zones) are never missed. For all projects in test set, critical rules identified before project design phase. Target: 100% detection.

8. **Incentive Eligibility Accuracy:** Eligibility criteria applied correctly. For 10 random incentives, manually verify eligibility logic against original program docs. No false positives (claiming eligibility when ineligible). Target: 100% on sampled set.

### Performance Invariants

9. **Latency:** `scan_regulations` returns in <10 seconds. `map_incentives` in <15 seconds. `assess_compliance` in <30 seconds (for projects with <50 regulations). Measured over 100+ calls per function.

10. **Handling Ambiguity:** When a regulation is ambiguous or interpretations differ by agency, the agent flags it explicitly (does not pick a side). Ambiguities noted in output with "see alternative interpretation" links. Never silently resolves disputes.

11. **Upstream Dependency Integrity:** When a regulation depends on upstream rules (e.g., "complies with federal 40 CFR § 122"), agent chains the dependency and assesses the full stack. No regulation assessed in isolation from its dependencies.

12. **Cost Estimation Realism:** Remediation and compliance cost estimates are within 30% of actual outcomes from 10+ completed projects in the knowledge library. Flagged as "estimate ± 30%" in output.

13. **Transparency on Data Sources:** Every regulation, incentive, timeline, and precedent includes a source URL or citation. Outputs show confidence/freshness of each datum. No unsourced claims.

14. **No Regulatory Interpretation (Agent Stays in Lane):** The agent summarizes regulations, does not provide legal interpretation. Output includes explicit disclaimer: "Not legal advice. Consult regulatory attorney for interpretation disputes." Verified by manual review of 20 outputs.

15. **Incentive Applicability to Agents:** When mapped incentives are passed to downstream agents (EvoTerra, Energy AI), they correctly filter for their sector. No energy-only incentive offered for forestry project. Cross-team testing with each agent on 5 shared projects.

---

## 9. REVENUE MODEL (DETAILED)

### Subscription (Baseline Revenue)

**Monthly Compliance Monitoring:** $200–2K/month depending on project complexity and active portfolio size.
- Small projects (1–2 active): $200–500/mo
- Mid-range (3–10 projects): $500–1.2K/mo
- Large portfolio (10+ projects): $1.2K–2K/mo

**What's included:**
- Continuous regulatory change monitoring for subscribed projects
- Quarterly compliance reassessment
- Monthly email digest of regulatory changes
- Access to incentive database
- Priority response (24–48 hours)

### Per-Project Advisory

**Permit Strategy & Drafting:** $1–5K per project depending on complexity.
- Residential/small projects: $1–2K
- Commercial/utility-scale: $3–5K

**What's included:**
- Full regulatory scan (all applicable rules)
- Compliance assessment
- Permit application draft with attachments
- Risk mitigation strategy
- Timeline and cost estimates

### Success-Based Upside

**Incentive Capture Fee:** 5–10% of identified incentives actually obtained.
- Performance baseline: Track which incentive recommendations led to funded applications.
- Payment trigger: When funds arrive to client account.
- Average incentive per project: $20–100K (varies by project type).
- Typical upside per client: $5–10K/month for active advisory clients.

### Expansion Revenue

- **Regulatory Training Workshops:** $5K per jurisdiction onboarding (train other agents/teams on local rules)
- **Data Licensing:** Anonymized compliance patterns and incentive success rates to foundations/government agencies
- **API Access:** White-label compliance API for contractors, consultants, platforms ($2K–5K/month)

---

## 10. SUCCESS METRICS

- **Regulatory Coverage:** % of applicable regulations identified for a given project type × jurisdiction (target: 95%+)
- **Compliance Accuracy:** % of compliance assessments that match ground truth post-audit (target: 95%+)
- **Incentive Capture Rate:** % of identified incentives actually funded / total identified (target: 60%+)
- **Timeline Prediction Accuracy:** Actual permit approval timeline vs. predicted timeline, within ±30% (target: 80%+)
- **Customer Retention:** Subscription renewal rate (target: 85%+)
- **Fleet Dependency:** % of agent queries that consult Regulatory Radar before proposing solutions (target: 100% for sector-specific projects)
- **Time-to-Compliance:** Average days from first advisory to full compliance, by project type (baseline vs. control group)
- **Cost Avoidance:** Estimated legal/permit costs saved through early guidance vs. project cost (target: 15–25% savings)

---

## 11. ANTI-PATTERNS TO AVOID

- **Over-generalization:** Treating federal rules as equivalent to state/local variations. Rules are jurisdiction-specific.
- **Incentive Chasing:** Recommending incentives just because they exist, not because they're worth pursuing. Filter for actual applicability + ROI.
- **Regulatory Interpretation:** Providing legal advice or picking between competing interpretations. Stay as interpreter of published rules, not judge.
- **Stale Data:** Serving outdated regulations without freshness warnings. Regulatory landscape changes monthly in some jurisdictions.
- **Silent Failures:** When a jurisdiction is unknown or data is unavailable, flag it loudly. Don't return empty results silently.
- **Assuming Static Timelines:** Permit timelines vary by season, staffing, political cycles. Use actual data, not published 30-day claims.
- **Breaking Dependencies:** Assessing compliance rule-by-rule without tracing upstream dependencies (if Reg A depends on Reg B, assess both or none).

---

## 12. NORTH STAR OUTCOME

Regulatory Radar succeeds when:

- Every project query returns actionable, sourced, jurisdiction-specific compliance guidance within 1 hour
- No project is designed without first consulting the regulatory layer
- Incentive mapping unlocks average $30K+ per client annually through better targeting and application quality
- Permit timelines are predicted within ±2 weeks instead of ±6 months
- Other agents (EvoTerra, Energy AI, Carbon-Bridge) can design solutions knowing the full regulatory context upfront
- The Knowledge Library grows continuously — every completed project adds compliance precedent, timeline data, and risk patterns that improve future guidance
