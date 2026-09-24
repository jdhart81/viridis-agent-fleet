# agent-metering-agent

**Role in the A2A economy:** metering. Usage metering + SLA accounting for agent services — the meter behind x402 micropayments.

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises (returns an error envelope).
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
create_meter, record_usage, usage_summary, sla_report, close_period, verify_chain, list_meters

Full input/output shapes: `describe()` and the action handlers in `src/core.py`.

## Invariants (M1–M8)
See the `src/core.py` module docstring for the authoritative list — one test
per invariant in `tests/test_core.py`.

## Deploy
Primary: MCP server (`adapters/mcp_server.py`). Secondary: FastAPI. Core is
stdlib-only. Tests: `PYTHONPATH=. pytest tests/ --override-ini=asyncio_mode=auto`.
