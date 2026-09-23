# agent-arbitration-agent

**Role in the A2A economy:** arbitration. Deterministic, machine-verifiable dispute resolution for A2A escrows.

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises (returns an error envelope).
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
file_case, submit_evidence, set_trust_scores, rule, verify_ruling, get_case, list_cases

Full input/output shapes: `describe()` and the action handlers in `src/core.py`.

## Invariants (A1–A8)
See the `src/core.py` module docstring for the authoritative list — one test
per invariant in `tests/test_core.py`.

## Deploy
Primary: MCP server (`adapters/mcp_server.py`). Secondary: FastAPI. Core is
stdlib-only. Tests: `PYTHONPATH=. pytest tests/ --override-ini=asyncio_mode=auto`.
