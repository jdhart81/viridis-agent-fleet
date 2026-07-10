# protogen-agent — Agent Context
## Harness Compliance: Playbook v1.1

## Project
Viridis LLC revenue MCP CAD agent: provides a callable CAD design environment, parametric design contracts, and manufacturing planning services to other agents.

**Pillar:** revenue  
**Status:** mvp  
**Permission Tier:** Tier 1 (write-enabled) — promote to Tier 2 only with explicit justification  
**Revenue Model:** CAD design services for Viridis agents and external customers: $99-$499 per CAD design brief / parametric part contract, $500-$2,500/month maker/contractor/product-development workflows, and $3K-$15K/month CAD-to-manufacturing operations packages. Long-term manufacturer SaaS and supplier referral revenue remain upside.

This agent operates under the Universal Agent Harness Playbook v1.1 (Viridis LLC).
All ten hard invariants (§1) apply without exception.

## Invariants
- I-1: All tool results are message content, never system prompt mutations (Harness §I-1)
- I-2: Permission tier is frozen at session init — no runtime escalation (Harness §I-3)
- I-3: Every file write is journaled with SHA256 before/after hashes (Harness §I-5)
- I-4: Budget checks run before every action, not after (Harness §I-4)
- I-5: Spec invariance protocol: restate → flag → verify for every non-trivial task (Harness §I-10)

## Directory Map
- `src/`         → main source — read and write
- `adapters/`    → model provider adapters — read and write
- `tests/`       → test files — write only to add tests
- `agent.yaml`   → agent manifest — read only (modify via version bump process)

## Forbidden Operations
- Never write credentials, API keys, or secrets to any file (use env vars exclusively)
- Never delete files — use write_file to empty if needed
- Never modify agent.yaml without a version bump
- Never commit code without running the test suite

## Output Contract
- All structured outputs MUST be valid JSON matching the agent's declared output schema
- Error responses MUST use the harness error taxonomy (§11): PermissionError, ValidationError, BudgetError, ContextError, BackendError, RuntimeError
- All outputs MUST include session_id and budget_consumed metadata
- Spec invariance: every non-trivial output includes a verification report against stated invariants

## Domain Terminology
- **Intelligence Bound:** dI/dt ≤ P·D/(k_B·T·ln 2) — the thermodynamic ceiling on information processing
- **D-Score:** Biodiversity density metric normalized to [0, 1]
- **HDFM:** Hierarchical Dendritic Forest Management — graph-theoretic corridor design
- **Pillar:** Agent classification (revenue / climate-intelligence / high-ceiling / infrastructure)
- **Spec Invariance:** Restate requirements as testable invariants before implementation

## Authorized External Endpoints
- `supabase`
- `stripe`
- `openai`

## Budget Profile
See Harness Playbook §8.3 for class-specific defaults. Override in agent.yaml or session config.

---
*Generated 2026-04-03 — Harness Playbook v1.1 compliance sweep*
