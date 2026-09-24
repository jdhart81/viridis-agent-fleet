# agent-offset-clearinghouse-agent

**Role in the A2A economy:** offsets. Verified conservation credits matched to agent compute emissions.

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises (returns an error envelope).
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
list_credit, buy_offset, net_position, verify_certificate, book, get_purchase

Full input/output shapes: `describe()` and the action handlers in `src/core.py`.

## Invariants (O1–O8)
See the `src/core.py` module docstring for the authoritative list — one test
per invariant in `tests/test_core.py`.

## Deploy
Primary: MCP server (`adapters/mcp_server.py`). Secondary: FastAPI. Core is
stdlib-only. Tests: `PYTHONPATH=. pytest tests/ --override-ini=asyncio_mode=auto`.
