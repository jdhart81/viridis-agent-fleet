# Official A2A Python SDK quickstart

Viridis exposes six paid skills through A2A 1.0 HTTP+JSON: five deterministic
carbon/compliance tools plus the reviewed Agent Hive Orchestrator. The public
Agent Card requires the canonical A2A x402 extension:

- Agent Card:
  `https://mcp.viridisconservation.com/.well-known/agent-card.json`
- interface: `https://mcp.viridisconservation.com/a2a`
- extension:
  `https://github.com/google-a2a/a2a-x402/v0.1`

## Discover without writing or paying

The default probe uses the released official A2A Python SDK to parse the live
Agent Card. It performs one GET, creates no task, and needs no wallet:

```bash
git clone https://github.com/jdhart81/viridis-agent-fleet.git
cd viridis-agent-fleet
uv run --no-project --with "a2a-sdk==1.1.2" \
  python scripts/a2a_quote_client.py
```

`pip install "a2a-sdk==1.1.2"` also works if you prefer an activated virtual
environment.

The command fails closed unless the card advertises:

- an `HTTP+JSON` interface;
- protocol version `1.0`;
- all six required Viridis commerce skills (future additions are allowed); and
- the required canonical x402 extension.

## Request one unpaid A2A quote

This explicit mode sends one structured A2A message for Regulatory Radar and
creates one durable `TASK_STATE_INPUT_REQUIRED` task:

```bash
uv run --no-project --with "a2a-sdk==1.1.2" \
  python scripts/a2a_quote_client.py --request-quote
```

The script prints the task ID and the x402 version, scheme, network, Base USDC
asset, atomic amount, receiver, and resource URL. It does not import or read a
private key, create a signature, submit a payment payload, or make a paid
retry.

The initial message is structured data, not prompt text:

```json
{
  "skillId": "regulatory-radar.scan_regulations",
  "input": {
    "jurisdiction": "US",
    "sector": "energy",
    "query": "45V clean energy tax credit emissions disclosure"
  }
}
```

For a California-specific quote, set `jurisdiction` to `california` or
`US-CA`. `CA` means Canada. Viridis canonicalizes the California alias before
creating the unpaid task.

The official SDK activates the payment extension with the standard
`A2A-Extensions` service parameter. Viridis also accepts the extension's
legacy `X-A2A-Extensions` form and echoes both forms in the response.

## Paying remains a separate buyer decision

The quote is not revenue and does not execute the skill. A buyer that accepts
the terms must use its own signing boundary to create an x402 payment payload,
then send a second A2A message containing the original `taskId`,
`x402.payment.status: payment-submitted`, and
`x402.payment.payload`.

Viridis verifies and settles the caller-supplied payload before executing the
deterministic skill. The seller never receives the buyer's private key. For
the existing ceiling-protected HTTP buyer path, see
[`scripts/x402_demo_client.py`](../../scripts/x402_demo_client.py).

Every payment is an independent buyer authorization. There is no automatic
follow-on purchase.

The Hive skill is `hive.solve`, fixed at $5.00, and excluded from one-cent
introductory pricing because its three-worker provider and solver-settlement
costs are real. Its advertised fixed profile requires `budget_minor=500`,
`depth=0`, `fee_bps=0`, no more than four subtasks, and redundancy no greater
than three. Viridis rechecks these bounds and provider readiness before
settlement.

## Compatibility receipt

On 2026-07-25, `a2a-sdk==1.1.2` completed an isolated in-memory interoperability
run against the production Viridis A2A seller code:

- Agent Card parsed successfully;
- five skills discovered (the compatibility receipt predates the sixth Hive
  commerce route);
- `HTTP+JSON` interface selected;
- canonical x402 extension activated;
- structured message accepted;
- one `TASK_STATE_INPUT_REQUIRED` quote returned;
- zero tool executions;
- zero signatures, settlements, or production writes.

The public Agent Card itself was also parsed by the same SDK through a live,
read-only GET. These are interoperability results, not a purchase or revenue.
