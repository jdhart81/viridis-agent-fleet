# agent-covenant-agent

**Role in the A2A economy:** authority. Machine-checkable authority leases: deny-by-default power of attorney for agents.

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises (returns an error envelope).
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
grant, check_act, revoke, status, verify_audit, list

Full input/output shapes: `describe()` and the action handlers in `src/core.py`.

## Invariants (C1–C8)
See the `src/core.py` module docstring for the authoritative list — one test
per invariant in `tests/test_core.py`.

## Deploy
Primary: MCP server (`adapters/mcp_server.py`). Secondary: FastAPI. Core is
stdlib-only. Tests: `PYTHONPATH=. pytest tests/ --override-ini=asyncio_mode=auto`.
