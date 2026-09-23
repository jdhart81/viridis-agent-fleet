# agent-verified-relay-agent

**Role in the A2A economy:** verified-relay. Viridis Verified — the
consequence wrapper: any third-party MCP server, relayed with tamper-evident
delivery receipts, metered fees, and dispute-ready evidence.

## Fleet contract
- `process(input: dict) -> dict` — async; dispatches on `input["action"]`; never raises (returns an error envelope).
- `health() -> dict` — async; `{status, agent, version, timestamp, checks}`.
- `describe() -> dict` — sync; `{name, version, capabilities, inputs, outputs, a2a_role}`.

## Actions
register_service, call_verified, get_receipt, verify_receipts, list_services, service_stats

Full input/output shapes: `describe()` and the action handlers in `src/core.py`.

## Invariants (V1–V10)
See the `src/core.py` module docstring for the authoritative list — one test
per invariant in `tests/test_core.py`.

## Security posture
The relay makes server-side HTTPS calls to caller-supplied URLs, so V1 is a
hard SSRF gate: https only, public FQDNs only (no IP literals, localhost,
.local/.internal), ports 443/8443, no userinfo. Container egress firewalling
is recommended defense-in-depth. The relay holds no keys and never signs or
mutates downstream payloads (V4) — it is an evidence layer, not a custodian.

## Deploy
Primary: MCP server (`adapters/mcp_server.py`); mounted at `/verified` on the
gateway with the freemium payment gate ($0.02/call past the free tier).
Core is stdlib-only. Tests: `PYTHONPATH=. pytest tests/ --override-ini=asyncio_mode=auto`.
