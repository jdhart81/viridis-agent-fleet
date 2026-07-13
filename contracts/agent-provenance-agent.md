# agent-provenance-agent

**Role in the A2A economy:** provenance. Genesis certificates, lineage, and cascading recalls for the agent economy.

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises (returns an error envelope).
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
register_genesis, get_certificate, verify_certificate, lineage, recall, list,
register_artifact, get_artifact, verify_artifact, list_artifacts

Full input/output shapes: `describe()` and the action handlers in `src/core.py`.

## Invariants (V1–V8, A1–A7)
See the `src/core.py` module docstring for the authoritative list — one test
per invariant in `tests/test_core.py`. Artifacts use a separate content-addressed
DAG; exact replays are idempotent and conflicting duplicate IDs fail closed.

## Deploy
Primary: MCP server (`adapters/mcp_server.py`). Secondary: FastAPI. Core is
stdlib-only. Tests: `PYTHONPATH=. pytest tests/ --override-ini=asyncio_mode=auto`.
