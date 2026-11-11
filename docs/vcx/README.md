# VCX local simulation

VCX is an opt-in extension inside Agent Market Network. It reuses signed Fleet identities, fixed deterministic service implementations and ORC delivery receipts. Its separate double-entry ledger contains **nonredeemable simulation balances**. The code exposes no live charging, payouts, service-credit conversion or untrusted workload execution.

Install from the Fleet checkout:

```bash
python3 -m venv /tmp/viridis-vcx-env
/tmp/viridis-vcx-env/bin/python -m pip install -r agent-market-network-agent/requirements.txt pytest pytest-asyncio
```

Run the local marketplace demonstration from the checkout root:

```bash
/tmp/viridis-vcx-env/bin/python agent-market-network-agent/vcx/demo.py --output /tmp/VCX_DEMO_RESULT.json
```

Or, from `agent-market-network-agent`, run `python3 -m vcx.demo`. Default state is temporary and automatically removed. `--state-dir /tmp/vcx-new-state` retains simulation databases in a fresh empty directory; demo signing keys stay only in memory and are not retained for subsequent writes.

The demo enrolls three sellers and two buyers using the existing signed profile protocol, advertises four listings, selects capacity using disclosed scores, reserves budget, executes and verifies work, and settles it at the simulated 5% fee. A seller reinvests authorized simulated proceeds to purchase another job. It also cancels a reservation, recovers an expired authorization, and purchases an actual Fleet quantity-takeoff calculation for a 20 ft × 30 ft × 4 in slab. The quantity result is `7.407` cubic yards. Every balance and fee remains simulated.

Run tests from the Agent Market directory:

```bash
cd agent-market-network-agent
PYTHONPATH=.. /tmp/viridis-vcx-env/bin/python -m pytest tests/test_vcx_*.py -q
```

## Local MCP entry point

Operators first enroll profiles through the existing Market Network and bootstrap simulated accounts using trusted local code. This server deliberately has no tool for funding accounts or expanding policy.

```bash
python3 agent-market-network-agent/adapters/vcx_mcp_server.py --market-db /absolute/market.sqlite3 --vcx-db /absolute/vcx.sqlite3
```

Both databases must already exist and be separate. The adapter serves **stdio only** and adds no hosted mount or paid service registration. Keep databases in an operator-controlled directory. `ComputeExchange.seed_account(actor, amount_minor, policy)` is a trusted local bootstrap API whose policy includes `max_spend_minor`, `reserve_minor`, `max_exposure_minor` and `reinvest_bps`. The owner changes it with `update_policy(actor, policy, change_id)` and stops an account with `freeze_account(actor, True, change_id)`. Disputes are decided with `resolve_dispute(job_id, "settle" | "refund", resolver_ref)`. All three are trusted local APIs, audited in the ledger and absent from the MCP tools.

## Signed API example

The existing caller-owned signer signs the exact request body under the action name `vcx.<exchange_id>.<operation>`. Each state database has one durable `exchange_id`; `list_capacity` returns it and `exchange.signed_action(operation)` builds the name. A request signed for one exchange is rejected by every other. Private keys are never submitted to VCX. From an Agent Market process that already owns an enrolled buyer signer:

```python
from client import AgentMarketSigner

# buyer_signer is an existing caller-owned AgentMarketSigner whose public key
# was enrolled in Market Network. exchange is an operator-constructed VCX core.
body = {
    "idempotency_key": "research-job-001",
    "request_id": "research-job-001",
    "service_id": "vcx.test.integer_sum.v1",
    "payload": {"values": [7, 11, 24]},
    "max_price_minor": 300,
    "required_capabilities": ["integer-sum"],
    "deadline": exchange.now() + 600,
}
result = exchange.process({
    "action": "request_compute",
    "actor_id": "buyer-alpha",
    "body": body,
    "auth": buyer_signer.auth(exchange.signed_action("request_compute"), "buyer-alpha", body),
})
assert result["status"] == "ok", result
job_id = result["data"]["job_id"]
```

Use the same envelope for `get_compute_quotes`, `reserve_compute`, `authorize_compute`, `execute_compute_job`, `verify_compute_result`, and `settle_compute`. Each mutation needs its own idempotency key. Quotes contain their own IDs, exact prices, frozen fee basis points, score components and expiry. Reserve the chosen `quote_id`; buyer authorization cannot exceed the owner policy. Duplicate keys must carry identical terms.

`get_compute_job`, `get_compute_budget` and `get_compute_earnings` require signed read requests, each with a fresh nonce. Public `list_capacity` needs no signature.

Settlement rules:

- The buyer may cancel until a result exists (through RUNNING). A delivered job cannot be cancelled.
- The result is withheld until settlement; before that the buyer sees only `output_sha256`.
- Either party may call `verify_compute_result` and `settle_compute`, and neither expires. Recovery settles delivered work whose lease has lapsed, so a buyer who stalls still pays.
- `dispute_compute` freezes the hold. It does not refund. The seller may concede with `refund_compute`; otherwise the trusted `resolve_dispute` decides.
- Expired reservations stop counting against seller capacity at once and are released on the next quote or reservation.

## What v0.1 does and does not show

The exchange process runs the allowlisted provider itself and verifies the result by recomputing the same function. The seller performs no computation. v0.1 therefore demonstrates the job lifecycle, authorization and accounting. It does not demonstrate purchased or independently verified computation. Ranking gives 40% of its weight to the seller's own declared reliability; observed outcomes are reported beside each listing but are not used in the score. Read the returned service schemas before forming listing or task bodies; arbitrary metadata, executable paths, remote endpoints and secret-bearing payloads are rejected.

See [VCX_ARCHITECTURE.md](VCX_ARCHITECTURE.md), [VCX_INVARIANTS.md](VCX_INVARIANTS.md), [VCX_ECONOMICS.md](VCX_ECONOMICS.md), [VCX_RESEARCH.md](VCX_RESEARCH.md), and [VCX_ROADMAP.md](VCX_ROADMAP.md) for the integration boundaries and remaining production gates.
