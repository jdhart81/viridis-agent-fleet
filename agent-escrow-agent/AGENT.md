# agent-escrow-agent

**Role in the A2A economy:** settlement. Trustless escrow between two agents —
funds are held until delivery is verified, then released to the payee or refunded
to the payer.

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises (returns an error envelope).
- `process_sync(input: dict) -> dict` — sync; envelope-identical to `await process(input)` (E9). For in-process composers needing a blocking settlement decision (gateway PaymentGate, PG13–PG16). Not covered by persistence wrappers on `process()` — sync callers own their own durability.
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
| action | inputs | effect |
|---|---|---|
| `open` | payer, payee, amount_minor, [currency, terms, deadline, fee_bps] | create escrow (state OPEN), freeze fee |
| `fund` | escrow_id, [payment_ref] | OPEN → FUNDED (idempotent) |
| `release` | escrow_id, [delivery_proof] | FUNDED/DISPUTED → RELEASED (exactly-once) |
| `refund` | escrow_id, [reason] | OPEN/FUNDED/DISPUTED → REFUNDED (exactly-once) |
| `dispute` | escrow_id, [reason] | FUNDED → DISPUTED |
| `status` | escrow_id | current record |
| `list` | [state] | all escrows, optionally filtered |
| `verify_audit` | escrow_id | validate the tamper-evident audit chain |

## Invariants (E1–E9)
Forward-only state machine; positive integer minor-unit amounts; fee frozen at
open (ceil bps); release requires FUNDED/DISPUTED; exactly-once settlement (no
double payout); tamper-evident audit hash chain; unknown escrow → error, never a
crash; sync dispatch surface semantically identical to async `process` (E9).
See `src/core.py` docstring for the authoritative list.

## Money-custody note
This core owns the **coordination + invariants**. Actual fund custody is delegated
to a payment-rail adapter (Stripe / x402 / on-chain), mirroring Energy AI's proven
micropayment idiom. No funds move without an approved rail — the state machine only
records intent and enforces safety.

## Deploy
Primary: MCP server (`adapters/mcp_server.py`). Secondary: FastAPI. Core is
stdlib-only. Tests: `PYTHONPATH=. pytest tests/ --override-ini=asyncio_mode=auto`.
