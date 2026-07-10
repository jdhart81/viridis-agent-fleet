# narrative-engine — Agent Context
## Harness Compliance: Playbook v1.1

## Project
Translates ecological intelligence into investor, policy, grant, and media-ready narratives

**Pillar:** infrastructure  
**Status:** prototype  
**Permission Tier:** Tier 0 (read-only) — promote to Tier 1 when entering MVP  
**Revenue Model:** Grant writing 5-10% of award, investor relations $5K-$25K, policy briefs $999-$4999/mo

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
No external network calls are authorized in this workspace unless explicitly configured in env vars.

## Budget Profile
See Harness Playbook §8.3 for class-specific defaults. Override in agent.yaml or session config.

---
*Generated 2026-04-03 — Harness Playbook v1.1 compliance sweep*
