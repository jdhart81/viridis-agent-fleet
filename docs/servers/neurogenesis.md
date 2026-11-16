# io.github.jdhart81/neurogenesis

Developmental agents plus Wu Wei routing: choose reuse, rules, local, tool, or cloud execution—and explicitly defer low-value work—under hard quality, reliability, locality, capability, cost, latency, and energy contracts with hash-bound decision and outcome receipts.

| | |
|---|---|
| Registry name | `io.github.jdhart81/neurogenesis` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/neurogenesis/mcp` |
| Version | 0.2.1 |
| Tools | 14 |
| Source | [`neurogenesis-agent/`](../../neurogenesis-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-neurogenesis": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/neurogenesis/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-neurogenesis https://mcp.viridisconservation.com/neurogenesis/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `create_agent`

Create a developmental agent from a digital genome: {agent_name, purpose, initial_nodes (unique, >=1), fitness_metrics (>=1), optional growth_rules / safety_axioms}. Returns agent_id + initial graph summary.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `genome` | object | yes | {agent_name, purpose, initial_nodes, fitness_metrics, growth_rules?, safety_axioms?}. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `submit_evaluation`

Evolve an agent with one task outcome: {task_id, task_type, success_score in [0,1], optional accuracy/user_satisfaction/ cost_efficiency/safety_score/notes/used_nodes/used_edges}. Success strengthens the used edges, …

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | The developmental agent's id, from create_agent. |
| `evaluation` | object | yes | {task_id, task_type, success_score 0..1, optional accuracy, used_nodes, used_edges}. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `get_agent`

Full current state: genome, cognitive graph (nodes/edges with weights and trust), and summary counts.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | The developmental agent's id, from create_agent. |

### `list_agents`

All developmental agents on this mount, with summary counts.

*read-only; structured output*

No inputs.

### `best_next_steps`

Routing recommendation: the strongest next cognitive steps from a given node, by learned edge weight and trust.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | The developmental agent's id, from create_agent. |
| `from_node` | string | yes | The node to route onward from. |
| `limit` | integer | no | Optional. How many next steps to return. Default 3. |

### `get_ledger`

The append-only developmental ledger: every growth, pruning, and evaluation event with reasons (NG3 — returned verbatim).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | The developmental agent's id, from create_agent. |
| `limit` | integer | no | Optional. The most ledger events to return. Default 100. |

### `export_state`

Portable state document for an agent (import_state recreates it anywhere — including a self-hosted verdigraph-neurogenesis).

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | The developmental agent's id, from create_agent. |

### `import_state`

Recreate an agent from an export_state document.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `state` | object | yes | A document from export_state, unchanged. |

### `delete_agent`

Remove a developmental agent from this mount.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | yes | The developmental agent's id, from create_agent. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `register_compute_profile`

Register a caller-owned Wu Wei execution profile: reuse/cache, deterministic rule, local model, tool/workflow, or cloud model. Profiles can declare quality, reliability, capabilities, token costs, latency, locality, …

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `profile` | object | yes | An execution profile: quality, reliability, capabilities, costs, latency, energy. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `route_task`

Choose the least-burden eligible route for a task. Hard constraints include quality, reliability, locality, capabilities, context, cost, latency, and energy. Optional baselines quantify predicted savings. Explicit …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `task` | object | yes | The task with its constraints: quality, cost, latency, energy and so on. |

### `record_route_outcome`

Attach one observed outcome to a Wu Wei decision. Actual cost, latency, and energy are optional and remain explicitly unknown when omitted. One append-only, hash-bound outcome is allowed per decision.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `actual_cost_usd` | number | no | Optional. What the task actually cost, in US dollars. |
| `actual_energy_wh` | number | no | Optional. Observed energy in watt-hours. |
| `actual_latency_ms` | number | no | Optional. Observed latency in milliseconds. |
| `decision_id` | string | yes | The decision id returned by route_task. |
| `notes` | string | no | Optional. Free-text notes on the outcome. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `success_score` | number | yes | How well the task went, 0 to 1. |

### `compute_efficiency_report`

Free read: decision/outcome receipts, route modes, compute avoided, predicted savings, predicted-vs-observed cost/latency/energy coverage, and Landauer-floor context. Estimates and observations stay distinct.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `limit` | integer | no | Optional. The most recent decisions to include. Default 50. |

### `describe_agent`

Return capabilities and input contract.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "describe_agent",
  "arguments": {}
}
```

Response (shortened):

```json
{
  "name": "neurogenesis-agent",
  "version": "0.2.0",
  "description": "Developmental agents from digital genomes: evaluation-driven growth/pruning over a cognitive graph with safety axioms and an append-only developmental ledger; Wu Wei v2 routes or defers work under hard quality, reliability, cost, latency, locality, and energy contracts.",
  "capabilities": [
    "create_agent",
    "list_agents",
    "get_agent",
    "submit_evaluation",
    "best_next_steps",
    "get_ledger",
    "export_state",
    "import_state",
    "delete_agent",
    "register_compute_profile",
    "route_task",
    "record_route_outcome",
    "compute_efficiency_report",
    "describe"
  ],
  "inputs": {
    "action": "str",
    "genome": "dict?",
    "agent_id": "str?",
    "evaluation": "dict?",
    "from_node": "str?",
    "state": "dict?",
    "profile": "dict?",
    "task": "dict?",
    "decision_id": "str?",
    "success_score": "float?",
    "limit": "int?"
  },
  "outputs": {
    "agent_id": "str",
    "nodes": "int",
    "edges": "int",
    "ledger_events": "int",
    "decision_sha256": "str?",
    "outcome_sha256": "str?"
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`neurogenesis-agent/`](../../neurogenesis-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
