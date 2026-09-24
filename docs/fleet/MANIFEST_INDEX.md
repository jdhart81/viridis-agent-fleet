# Agent Manifest Index
> Quick reference for the priority agent.yaml files in the Viridis fleet

---

## Pillar 1: Bootstrap Revenue (8 agents)

| Agent | Status | Deploy | Notes |
|-------|--------|--------|-------|
| [energyai-agent](energyai-agent/agent.yaml) | Production | Cloudflare Worker | $100–$200/lead, already live |
| [bounty-hunter-agent](bounty-hunter-agent/agent.yaml) | Running | Claude Skill | $5K–$500K/finding, active ops |
| [viridis-trading-agent](viridis-trading-agent/agent.yaml) | Prototype | FastAPI/MCP | Polymarket + Tradovate unified |
| [ecoinvest-agent](ecoinvest-agent/agent.yaml) | MVP | FastAPI | ESG + thermodynamic valuation |
| [smartscale-agent](smartscale-agent/agent.yaml) | Near-deploy | MCP/FastAPI/Docker | Credit-card calibrated photo measurement revenue agent |
| [protogen-agent](protogen-agent/agent.yaml) | MVP | MCP/FastAPI | CAD design environment and manufacturing planning revenue agent |
| [compute-exchange-agent](compute-exchange-agent/agent.yaml) | Prototype | MCP/FastAPI | Policy-safe compute capacity exchange for agents; no resale of non-transferable credits or shared accounts |
| [taxcredit-engine-agent](../../taxcredit-engine-agent/agent.yaml) | MVP | MCP/Docker | Auditable clean-energy tax-credit scenarios; $2/call after free tier |

---

## Pillar 2: Climate Intelligence (3 agents)

| Agent | Status | Deploy | Notes |
|-------|--------|--------|-------|
| [viridis-science-agent](viridis-science-agent%20copy/agent.yaml) | MVP+ | FastAPI/MCP | Absorbs institute specs |
| [evoterra-agent](evoterra-agent/agent.yaml) | MVP | FastAPI/TypeScript | Regenerative landscape design |
| [gaiasim-agent](gaiasim-agent/agent.yaml) | MVP | TypeScript MCP | Earth system modeling |

---

## Pillar 3: High-Ceiling Bets (6 agents)

| Agent | TAM | Status | Deploy | Notes |
|-------|-----|--------|--------|-------|
| [skicoach-agent](skicoach-agent/agent.yaml) | $2.8B | MVP | FastAPI/TypeScript | FallLineIQ, 60% code |
| [quantum-oracle-journal](quantum-oracle-journal/agent.yaml) | $15.8B | Feature-complete | FastAPI/TypeScript | Therapeutic journaling |
| [buildbuddy-agent](buildbuddy-agent/agent.yaml) | $30B | Core API | MCP | Construction tech |
| [psinet-agent](psinet-agent/agent.yaml) | $80B | Near-deploy | FastAPI/Docker | Quantum probability analytics |

---

## Infrastructure (2 agents)

| Agent | Status | Deploy | Notes |
|-------|--------|--------|-------|
| [mycelium-iq-agent](mycelium-iq-agent/agent.yaml) | Prototype | MCP | Absorbs ShenDao + OTA |
| [agent-ceo](AGENT_CEO%20copy/agent.yaml) | Active | Claude Skill | Strategic OS |

---

## How to Read Each Manifest

Each `agent.yaml` contains:

```yaml
name:           Agent identifier (used by Mycelium IQ for discovery)
version:        Version number; indicates maturity/stability
description:    One-line business description
pillar:         "revenue" | "climate-intelligence" | "high-ceiling" | "infrastructure"
status:         "spec" | "prototype" | "mvp" | "production" | "feature-complete" | "near-deploy" | "core-api" | "pipeline-ready"
owner:          justin@viridis.earth

revenue_model:  How this agent makes money (explicit targets + metrics)

deploy_targets:
  primary:      Main deployment environment
  secondary:    Alternate/fallback targets

dependencies:
  services:     External APIs/platforms required (Stripe, Supabase, etc.)
  agents:       Other Viridis agents this depends on

env_vars:       Environment variable names required for secrets

capabilities:
  inputs:       Data types this agent accepts
  outputs:      Data types this agent produces

documentation:
  readme:       Entry point documentation
  deploy:       Deployment instructions
  business_plan: Revenue/market documentation

notes:          Context on maturity, consolidation decisions, etc.
```

---

## Consolidation Summary

**Merged (v1.0 → v2.0):**
- polymarket-prism-agent + tradovate-futures-agent → viridis-trading-agent
- objective-truth-agent + shendao-agent → Mycelium IQ sublayers
- viridis-institute-agents → Viridis Science Agent reference specs

**Archived (IP preserved):**
- wavefunction-agent → `_archive/` (Web3 protocol, 12–18 month horizon)
- canon-spec-agent → `_archive/` (Machine spec system)

**Renames:**
- AGENT_CEO copy → agent-ceo
- viridis-science-agent copy → viridis-science-agent

**Result:** Consolidated priority manifest index with Pillar 1 expanded for near-term revenue MCP agents.

---

## Using This Index

1. **Discovery**: Find an agent by pillar or TAM size
2. **Integration**: Check `dependencies.agents` to see what other agents it needs
3. **Deployment**: Cross-reference `deploy_targets` with infrastructure (Cloudflare, FastAPI servers, Docker)
4. **Revenue**: See `revenue_model` for each agent's path to profitability
5. **Status**: Quick glance at maturity (Production = live, Prototype = early, Feature-complete = close to ship)

---

## Links

- Full architecture: [FLEET_INDEX.md](FLEET_INDEX.md)
- Trading agent details: [viridis-trading-agent/README.md](../../viridis-trading-agent/README.md)
- Deployment sequence: See FLEET_INDEX.md section "DEPLOY SEQUENCE"

---

*Last updated: March 28, 2026*
