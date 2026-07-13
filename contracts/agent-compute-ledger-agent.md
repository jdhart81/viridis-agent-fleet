# agent-compute-ledger-agent

**Role in the A2A economy:** accounting. Compute-is-carbon energy/carbon ledger with Landauer-limit validation.

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises (returns an error envelope).
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
record_work, footprint, attest, verify_attestation, verify_chain, list_entries,
record_inventory, get_inventory, list_inventories, verify_inventory_chain

Full input/output shapes: `describe()` and the action handlers in `src/core.py`.

## Invariants (L1–L8, I1–I6)
See the `src/core.py` module docstring for the authoritative list — one test
per invariant in `tests/test_core.py`. Inventory records use a separate
append-only chain, exact integer grams, explicit content/factor lineage, and
payload-consistent idempotency; a conflicting duplicate ID fails closed.

## Deploy
Primary: MCP server (`adapters/mcp_server.py`). Secondary: FastAPI. Core is
stdlib-only. Tests: `PYTHONPATH=. pytest tests/ --override-ini=asyncio_mode=auto`.
