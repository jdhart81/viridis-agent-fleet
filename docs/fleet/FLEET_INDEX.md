# Viridis Agent Fleet v3.1
> 33 active agents · 3 pillars + cross-pillar connectors + infrastructure · Index as of March 28, 2026 (v3.0 tables); all post-v3.0 agents now tabled (dscore and wavefunction-search added Night 32 2026-05-01; ecotopia and entropy-oracle added Night 33 2026-05-02; evolution and qi-flow-architect added Night 34 2026-05-03; living-game-coach added Night 35 2026-05-04; compute-exchange added as Pillar 1 revenue MCP 2026-06-13)
> Standard template: `_AGENT_TEMPLATE/` · All agents follow `agent.yaml` manifest pattern

---

## Architecture Philosophy

Viridis agents operate as a **modular, composable ecosystem** grounded in thermodynamic economics and Intelligence Bound principles. Each agent implements a standardized interface (`process()`, `health()`, `describe()`) and declares its dependencies, revenue model, and deployment target in `agent.yaml`. This separates core business logic from deployment adapters (Workers, FastAPI, MCP, Skills), enabling composability through **Mycelium IQ** — the coordination layer that trades resources, composts failures, and pairs agents for symbiotic scaling. The fleet unifies two previously separate markets (prediction markets + futures) and consolidates governance/truth verification into the foundation, reflecting the maturation of the ecosystem. v3.0 closes the loop with a complete **observe → model → value → originate → verify → trade → regulate → narrate → reinvest** flywheel: Climate Intelligence agents observe Earth systems; Science Agent models ecological value; Carbon Bridge originates credits; Proof-of-Conservation verifies outcomes; Trading Agent executes markets; Regulatory Radar monitors compliance; Narrative Engine synthesizes storytelling; Treasury reinvests profits.

---

## Standard Agent Interface

Every agent implements:

```python
def process(input: dict) -> dict:
    """Main business logic: transform input → output."""
    pass

def health() -> dict:
    """Liveness check: returns {status, timestamp, metrics}."""
    pass

def describe() -> dict:
    """Agent discovery: returns {name, capabilities, inputs, outputs}."""
    pass
```

**Deployment targets:**
- `cloudflare-worker` — Stateless, global, minimal latency (Energy AI)
- `fastapi` — Containerized, local state, external APIs (PSINet, SmartScale)
- `mcp-server` — Claude integration, model-native composition (Mycelium IQ)
- `claude-skill` — Operator-facing playbook automation (Agent CEO)

---

## PILLAR 1: BOOTSTRAP REVENUE
*Immediate cash flow — funds development of Pillar 2 and Pillar 3*

| # | Agent | Directory | Status | Revenue Model | Deploy Target |
|---|-------|-----------|--------|---------------|---|
| 1 | **Energy AI** | `energyai-agent/` | **PRODUCTION** | $100–$200/lead, 80% margin, $0 deploy cost | Cloudflare Worker |
| 2 | **Bounty Hunter** | `bounty-hunter-agent/` | **RUNNING** | $5K–$500K/finding, 95% margin | Claude Code Skill + Workflows |
| 3 | **Viridis Trading Agent** | `viridis-trading-agent/` | **PROTOTYPE** | Polymarket PRISM (4 engines) + Tradovate MCL/MGC daily compounding | FastAPI + MCP |
| 4 | **EcoInvest AI** | `ecoinvest-agent/` | **MVP** | ESG fund selection, AUM-based fees, thermodynamic risk scoring | FastAPI |
| 5 | **Thermo-Arbitrage Agent** | `thermo-arbitrage-agent/` | **PROTOTYPE** | Biodiversity mispricing detection via Intelligence Bound theorem as systematic investing edge; trading profits, advisory ($50K–$500K), data licensing | FastAPI |
| 22 | **SmartScale** | `smartscale-agent/` | **Near-ready** | Credit-card calibrated photo measurement for contractors, ecommerce, makers, inspectors, and Viridis agent workflows. Self-serve API/plugin ($99-$299/mo), SMB packages ($500-$2K/mo), custom operations consulting ($3K-$8K/mo). | MCP + FastAPI + Docker |
| 14 | **ProtoGen** | `protogen-agent/` | **MVP** | MCP CAD services for Viridis agents and external customers: CAD design briefs ($99-$499), maker/contractor/product workflows ($500-$2.5K/mo), CAD-to-manufacturing ops packages ($3K-$15K/mo). | MCP + FastAPI |
| 33 | **Compute Exchange** | `compute-exchange-agent/` | **PROTOTYPE** | Policy-safe compute capacity marketplace for Viridis agents and external customers: compliant internal budget routing, owned/local/cloud worker orchestration, exchange fees (10%-20%), managed compute coordination ($500-$5K/mo). Explicitly does not broker non-transferable credits, shared API keys, or shared accounts. | MCP + FastAPI |
| 34 | **Tax Credit Engine** | `taxcredit-engine-agent/` | **MVP** | Auditable deterministic 45Q/45V/45Y/48E/45X scenario calculations. 10 free/day, then $2/call; versioned IRS rule packs and notary-ready hashes. | MCP + Docker |
| 28 | **Ecotopia Agent** | `ecotopia-agent/` | **PROTOTYPE** | Practical playbook for AI-assisted democratic governance, circular economy, and ecological restoration at municipal/community scale. Municipal consulting ($20K–$200K), NGO advisory ($5K–$50K), community subscriptions ($500–$5K/mo). | FastAPI + MCP |
| 30 | **Qi-Flow Architect** | `qi-flow-architect-agent/` | **PROTOTYPE** | Evaluates and optimizes information/value/trust circulation across designed systems (code, orgs, supply chains, urban layouts). Enterprise architecture consulting ($5K–$50K/engagement), SaaS flow dashboard ($1K–$10K/mo), urban planning advisory ($10K–$100K/project). | FastAPI + MCP |
| 32 | **Living-Game Coach** | `living-game-coach-agent/` | **PROTOTYPE** | Personal operating system for reducing individual and team friction through daily practices, shadow work, and conflict resolution. Consumer subscription ($9.99–$19.99/mo, ~10K–50K users = $1.2M–$12M ARR), enterprise team packages ($5K–$25K/yr), integration licensing to coaching platforms. Funds Agent CEO firmware. | FastAPI + MCP |

**Capital Allocation Strategy:** Treasury Optimizer (emerging role in Mycelium IQ v1) unifies P&L, rebalances capital across agents daily, executes portfolio hedges.

---

## PILLAR 2: CLIMATE INTELLIGENCE STACK
*Enterprise B2B offering — path to $100M+ ARR*

| # | Agent | Role | Status | Deploy Target |
|---|-------|------|--------|---|
| 6 | **Viridis Science Agent** | Research orchestrator for Intelligence Bound theorem; absorbs institute specs (D-Score, HDFM, Biodiversity Credits, Implementation Monitor, Thermodynamic Valuation, Master Agent) | **MVP+** | FastAPI + MCP |
| 7 | **Evoterra** | Regenerative landscape design, biome generation, carbon modeling | **MVP** | TypeScript + Python |
| 8 | **GaiaSim** | Earth system modeling, weather integration, macro-scale climate forecasting | **MVP** | TypeScript MCP |
| 9 | **Sentinel-Watch Agent** | Satellite remote sensing for land-use change, deforestation monitoring, restoration verification | **PROTOTYPE** | FastAPI |
| 10 | **Bioacoustic Agent** | Acoustic biodiversity measurement via soundscape analysis; Acoustic D-Score (Shannon entropy of spectrograms) | **PROTOTYPE** | FastAPI |
| 26 | **D-Score Agent** | Biodiversity valuation middleware: converts biome D-Scores to thermodynamic information units (bits) and Landauer-priced USD with Lean4 proof certificates. Bridges Viridis Science Agent → Carbon-Bridge → Trading. | **MVP** | FastAPI + MCP |
| 29 | **Entropy-Oracle Agent** | Computational embodiment of Heat and Disorder: makes thermodynamic reality actionable via entropy budgets, feedback-cascade maps, tipping-point proximity scores, and entropy-cost labels for products/policies/projects. Climate risk consulting ($10K–$100K), insurance data licensing ($10K–$50K/yr), carbon project auditing. | **PROTOTYPE** | FastAPI + MCP |

**Compliance Layer (emerging):** TNFD/CSRD automated reporting — the sales enabler for the stack.

---

## CROSS-PILLAR CONNECTORS
*Bridge agents that bind revenue flows to climate intelligence — close loops and unlock new TAMs*

| # | Agent | Function | Status | Revenue Model | Deploy Target |
|---|-------|----------|--------|---|---|
| 11 | **Carbon-Bridge Agent** | Carbon/biodiversity credit origination, TFAC pricing, verification routing, market execution | **PROTOTYPE** | Origination fees 5–15%, trading spread, verification $5K–$25K | FastAPI |
| 12 | **Sentinel-Watch Agent** | Satellite remote sensing for land-use change, deforestation monitoring, restoration verification | **PROTOTYPE** | Monitoring-as-a-service ($500–$5K/site/yr), carbon verification ($2K–$10K/project) | FastAPI |
| 13 | **Bioacoustic Agent** | Acoustic biodiversity measurement via soundscape analysis; Acoustic D-Score (Shannon entropy of spectrograms) | **PROTOTYPE** | Hardware+analysis ($200/sensor/yr), research data ($10K–$100K), monitoring ($1K–$10K/site/yr) | FastAPI |

---

## PILLAR 3: HIGH-CEILING BETS
*Standalone products with large TAMs — parallel development path*

| # | Agent | TAM | Y5 Ceiling | Status | Deploy Target |
|---|-------|-----|-----------|--------|---|
| 15 | **SkiCoach AI** (FallLineIQ) | $2.8B digital ski racing | $180M | MVP (60% code complete) | TypeScript + FastAPI |
| 16 | **Quantum Oracle Journal** | $15.8B wellness | $112M | **Feature-complete** | FastAPI |
| 17 | **BuildBuddy** | $30B construction tech | $50M | Core API spec | MCP |
| 18 | **PSINet** | $80B market research | $5M+ | MVP API ready | FastAPI + Docker |

---

## INFRASTRUCTURE
*The connective tissue — multiplies everything else*

| # | Agent | Function | Status | Deploy Target |
|---|-------|----------|--------|---|
| 20 | **Mycelium IQ** | Agent-to-agent coordination: resource trading, failure composting, symbiotic pairing. Absorbs ShenDao (governance layer) and OTA (truth verification layer) as embedded sublayers. | **50KB+ Python** | MCP Server |
| 21 | **Agent CEO** | Justin's strategic operating system: Cowork skill, playbooks, reference library, decision automation | **ACTIVE** | Claude Code Skill |
| 23 | **Regulatory-Radar Agent** | Environmental regulation monitoring (TNFD/CSRD/EU Taxonomy/SEC), compliance scoring, opportunity detection | **PROTOTYPE** | Compliance-as-a-service $5K–$50K/yr, reports $10K–$100K | FastAPI |
| 24 | **Proof-of-Conservation Agent** | Cryptographic verification of conservation outcomes via multi-modal evidence (satellite+acoustic+measurement). Merkle tree proofs. | **PROTOTYPE** | Verification fees $2K–$10K, proof-as-a-service $1K–$5K | FastAPI |
| 25 | **Narrative-Engine Agent** | Translates ecological intelligence into investor/policy/grant/media narratives | **PROTOTYPE** | Grant writing 5–10%, investor relations $5K–$25K, policy briefs $999–$4999/mo | FastAPI + MCP |
| 27 | **Wavefunction-Search Agent** | Quantum-cognition routing layer: crystallizes ambiguous user intentions into structured commitments and matches them to constitutionally-aligned agents (S_C ≥ 0.5). Reduces coordination friction across the fleet. | **PROTOTYPE** | Coordination-as-a-service $5K–$50K/mo; internal fleet routing | FastAPI + MCP |
| 31 | **Evolution Agent** | Meta-agent: detects ecosystem gaps, proposes novel agents, scaffolds from template, manages agent lifecycle (promote/evolve/merge/compost). Force multiplier — increases fleet value by spawning high-value agents and licensing the evolution engine to external ecosystems. | **PROTOTYPE** | Indirect (force multiplier); evolution-engine licensing $1B+ TAM | MCP + FastAPI |

---

## ARCHIVE
*Intellectual property preserved; parked for long-horizon deployment*

| Agent | Reason | Location |
|-------|--------|----------|
| **Wavefunction** | Long-horizon Web3 coordination protocol. 98% documentation, 12–18 month timeline. Strategic IP. | `_archive/wavefunction-agent/` |
| **Canon Spec** | Machine specification system. Single SKILL.md, massive data engineering problem, no revenue path. IP archived. | `_archive/canon-spec-agent/` |

---

## CONSOLIDATION LOG

### Merges (v1.0 → v2.0)

**Trading Agent Consolidation**
- `polymarket-prism-agent` (4-engine SNAP/SWEEP/REACT/PULSE, Polymarket orders)
- + `tradovate-futures-agent` (MCL/MGC systematic)
- = `viridis-trading-agent` (unified risk management, shared capital allocation, single deployment)
- **Rationale:** Same operator (trading desk), complementary markets, unified P&L, daily compounding on shared treasury.

**Science Stack Consolidation**
- `objective-truth-agent` → absorbed as **OTA sublayer in Mycelium IQ** (truth verification for agent network)
- `shendao-agent` → absorbed as **ShenDao sublayer in Mycelium IQ** (ethical governance for agent network)
- `viridis-institute-agents` (D-Score, HDFM, Biodiversity Credits, Implementation Monitor, Thermodynamic Valuation, Master Agent) → absorbed as **reference specifications in Viridis Science Agent**
- **Rationale:** Institute specs are foundational docs for science agent. OTA/ShenDao no longer needed as standalone agents; they're now governance/verification infrastructure for Mycelium IQ's coordination loop.

### Additions (v2.0 → v3.0)

**Pillar 1 Revenue Extension**
- `thermo-arbitrage-agent` — Scales Pillar 1 beyond energy/prediction markets into structured trading on biodiversity mispricing using Intelligence Bound theorem as systematic edge. Advisory + data licensing unlock $50K–$500K revenue paths.
- `smartscale-agent`, `protogen-agent`, and `compute-exchange-agent` — Convert the fleet into a sellable MCP services layer: measurement, CAD generation, and compliant compute orchestration for other agents and external customers.

**Pillar 2 Climate Intelligence Expansion**
- `sentinel-watch-agent` — Satellite remote sensing layer (observe step). Land-use change, deforestation, restoration verification. $500–$5K/site/yr monitoring-as-a-service.
- `bioacoustic-agent` — Acoustic biodiversity as alternative/complementary measurement (observe step). D-Score via spectrograms. Hardware + research data + monitoring revenue.

**Cross-Pillar Connectors (New Section)**
- `carbon-bridge-agent` — Closes Pillar 1 ↔ Pillar 2 loop. Originates credits from intelligence, executes market, captures fees (5–15% origination, spreads, $5K–$25K verification).
- *Note: Sentinel-Watch and Bioacoustic dual-index as both Climate Intelligence AND Cross-Pillar Connectors per their bridging role.*

**Infrastructure Layer Maturation**
- `regulatory-radar-agent` — Compliance as ecosystem multiplier. Automated TNFD/CSRD/EU Taxonomy monitoring → compliance scoring + opportunity detection. $5K–$50K/yr SaaS + reports.
- `proof-of-conservation-agent` — Verification layer for the entire fleet. Multi-modal cryptographic proof (satellite+acoustic+measurement). Merkle tree anchoring. $2K–$10K verification fees + proof-as-a-service.
- `narrative-engine-agent` — Enables monetization of ecological intelligence (narrate step in flywheel). Grant writing (5–10%), investor relations ($5K–$25K), policy briefs ($999–$4999/mo). Closes loop to reinvestment.

**Rationale for v3.0 additions:**
- v2.0 launched Pillar 1 (cash) + Pillar 2 foundation (science) + Pillar 3 (bets). v3.0 closes observation-to-value loops and adds verification/narrative/regulation layers.
- Thermo-Arbitrage extends Pillar 1 economics with structured mispricing capture (Bound theorem × markets).
- Sentinel-Watch + Bioacoustic fill the "observe" capability gap, enabling Science Agent to ingest multi-modal ground truth.
- Carbon-Bridge is the revenue engine: originates credits from science, hedges via Trading Agent, sells via markets.
- Proof-of-Conservation + Regulatory-Radar enable scaled verification and compliance, unlocking enterprise trust.
- Narrative-Engine monetizes the full intelligence stack: grants, investor relations, policy influence, grant-funded reinvestment.

### Archives (v1.0 → v2.0)

**Wavefunction Agent**
- Web3 protocol layer for autonomous coordination at 12–18 month horizon.
- 98% documentation complete; no immediate deployment path.
- Intellectual property (paper, spec) preserved in `_archive/`.

**Canon Spec Agent**
- Machine specification system (parts taxonomy, assembly logic).
- Single SKILL.md file; massive data engineering lift with no revenue model.
- IP preserved in `_archive/`; revisit if ProtoGen scales to manufacturing.

### Renames

- `AGENT_CEO copy` → `agent-ceo`
- `viridis-science-agent copy` → `viridis-science-agent`

---

## DEPLOY SEQUENCE

### Week 1: Immediate (Already Live)
- **Energy AI:** Production-ready, first leads, revenue flowing
- **Bounty Hunter:** Active operations, continuous finding flow

### Week 2–3: Fast-Follow
- **SmartScale v0.1:** Deploy credit-card calibrated MCP measurement plugin plus FastAPI sandbox
- **ProtoGen v0.3:** Deploy MCP CAD workspaces, parametric design contracts, and OpenSCAD/manufacturing brief exports
- **Compute Exchange v0.1:** Deploy internal MCP compute router for compliant supply/request/match/settlement workflows
- **PSINet API:** Go live on internal Docker, validate market research demand

### Month 1–2: Revenue Consolidation
- **Viridis Trading Agent Phase 0:** Paper trading on unified Polymarket + Tradovate platform; deploy to TestNet
- **Mycelium IQ v1 (health + event bus):** Basic agent health monitoring, failure composting, resource event log

### Month 2–3: Pillar 2 Activation
- **Viridis Science Agent MVP:** FastAPI instance with D-Score + HDFM reference specs; first beta customer
- **EcoInvest AI:** MVP on Supabase + FastAPI; first portfolio analysis

### Month 3–6: Scale & Validation
- **Sentinel-Watch Agent v0.1:** Deploy satellite remote sensing module; first 3 sites (proof of concept)
- **Bioacoustic Agent v0.1:** Acoustic D-Score calculation on reference datasets; publish methodology paper
- **GaiaSim or Evoterra:** First Pillar 2 agent to customer (whichever shows traction)
- **Mycelium IQ v2:** Full resource trading, symbiotic pairing, cross-agent capital flows

### Month 6–9: Loop Closure (v3.0 Connectors)
- **Carbon-Bridge Agent Phase 0:** Integrate Sentinel-Watch + Bioacoustic observations; originate first 5 carbon credit batches
- **Proof-of-Conservation Agent:** Deploy cryptographic verification; anchor first Merkle proofs
- **Regulatory-Radar Agent:** Monitor TNFD/CSRD/SEC for 10 pilot customers; compliance scoring dashboard

### Month 9–12: Acceleration & Narrative
- **Narrative-Engine Agent:** Connect science output → grant narratives; first $500K grant funding cycle
- **Thermo-Arbitrage Agent:** Live trading on mispriced biodiversity indices (paper → real money)
- Scale whichever pillar is converting fastest (likely Energy AI → Bounty Hunter → Trading for Pillar 1; Science Agent + Carbon Bridge for Pillar 2)
- Begin remaining Pillar 3 prototype launches (SkiCoach, BuildBuddy pilots)

---

## Key Metrics by Pillar

**Pillar 1 (Revenue):** MRR, lead quality, conversion rate, capital turnover
**Pillar 2 (Climate):** Customer acquisition, AUM, scientific credibility (publications)
**Pillar 3 (High-Ceiling):** Product-market fit signals, user engagement, IP defensibility

---

## Standard Operations

All agents:
1. Have `agent.yaml` manifest in root directory
2. Implement `process()`, `health()`, `describe()` interface
3. Log via MCP or stdout (captured in Mycelium IQ event bus)
4. Expose health endpoint (for orchestration)
5. Version code by agent; coordinate version bumps via Agent CEO + Mycelium IQ

---

*Fleet last updated: March 28, 2026 — v3.0*
