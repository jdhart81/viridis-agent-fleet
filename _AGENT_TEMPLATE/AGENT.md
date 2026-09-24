# [AGENT_NAME] — Agent Context
## Harness Compliance: Playbook v1.1

## Project
[One paragraph: purpose, domain, what the agent does, what it is NOT authorized to do]

**Pillar:** [revenue | climate-intelligence | high-ceiling | infrastructure]
**Status:** [spec | prototype | mvp | production]
**Permission Tier:** [Tier 0-3 per §3.3 — start at Tier 0, escalate with justification]
**Revenue Model:** [From agent.yaml]

This agent operates under the Universal Agent Harness Playbook v1.1 (Viridis LLC).
All ten hard invariants (§1) apply without exception.

## Invariants
- I-1: All tool results are message content, never system prompt mutations (Harness §I-1)
- I-2: Permission tier is frozen at session init — no runtime escalation (Harness §I-3)
- I-3: Every file write is journaled with SHA256 before/after hashes (Harness §I-5)
- I-4: Budget checks run before every action, not after (Harness §I-4)
- I-5: Spec invariance protocol: restate → flag → verify for every non-trivial task (Harness §I-10)
- I-6: [Agent-specific invariant — add at least one]
- I-7: [Agent-specific invariant — add more as needed]

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
- [Add domain-specific forbidden operations]

## Output Contract
- All structured outputs MUST be valid JSON matching the agent's declared output schema
- Error responses MUST use the harness error taxonomy (§11)
- All outputs MUST include session_id and budget_consumed metadata
- Spec invariance: every non-trivial output includes a verification report against stated invariants

## Domain Terminology
- **Intelligence Bound:** dI/dt ≤ P·D/(k_B·T·ln 2) — the thermodynamic ceiling on information processing
- **D-Score:** Biodiversity density metric normalized to [0, 1]
- **HDFM:** Hierarchical Dendritic Forest Management
- **Spec Invariance:** Restate requirements as testable invariants before implementation
- [Add agent-specific terminology]

## Authorized External Endpoints
[List exact endpoints or: "No external network calls are authorized in this workspace"]

## Budget Profile
See Harness Playbook §8.3 for class-specific defaults. Override in agent.yaml or session config.

---
*Template — Harness Playbook v1.1*
