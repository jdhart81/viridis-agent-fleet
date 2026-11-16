# io.github.jdhart81/agent-offset-clearinghouse

Verified conservation credits matched to agent compute emissions: cheapest-first matching, exactly-once retirement, content-addressed offset certificates. The first economy born carbon-accountable.

| | |
|---|---|
| Registry name | `io.github.jdhart81/agent-offset-clearinghouse` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/offsets/mcp` |
| Version | 0.6.0+h1115 |
| Tools | 19 |
| Source | [`agent-offset-clearinghouse-agent/`](../../agent-offset-clearinghouse-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-agent-offset-clearinghouse": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/offsets/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-agent-offset-clearinghouse https://mcp.viridisconservation.com/offsets/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `list_credit`

List a conservation credit on the book. verification_ref (a D-Score / land-verification attestation) is REQUIRED — unverified credits cannot enter the book. To trade on the Verra network, pass registry="verra" with the …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `issuer` | string | yes | Id of the party listing the credit. |
| `mass_g` | integer | yes | Grams of CO2e, a whole number. |
| `methodology` | string | no | Optional. The methodology code, for example VM0047. |
| `price_minor_per_kg` | integer | yes | Price per kilogram in minor units (cents). |
| `project_id` | string | yes | The restoration project's id. |
| `registry` | string | no | Optional. verra to trade on the Verra network. |
| `serial_number` | string | no | Verra serial number range, when registry is verra. |
| `vcs_project_id` | string | no | Verra VCS project id, when registry is verra. |
| `verification_ref` | string | yes | Required. The verification attestation or registry id. |
| `vintage` | string | no | Credit vintage year, when registry is verra. |

### `delist_credit`

Admin operation: remove a credit from the active fill path while retaining its listing and retirement history for audit. Idempotent for an already-delisted credit. Gateway state-change authentication is required.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `credit_id` | string | yes | The credit id returned by list_credit. |
| `reason` | string | yes | Why the credit is removed from the active book. |

### `verra_supply`

The tradeable Verra VCS book: verified credits carrying genuine Verra provenance (project id + serial + vintage), cross-referenceable on registry.verra.org. Read-only. Every retirement nets the project 85% and Viridis …

*changes records; may need a caller credential (see below); structured output*

No inputs.

### `verra_retirement_record`

Generate the Verra-portal-ready retirement record(s) for a retirement made against Verra supply — VCS project id, serial, vintage, methodology, quantity (tCO2e), beneficiary, and the registry.verra.org cross-reference. …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `purchase_id` | string | yes | Your id for the purchase; repeating it never retires twice. |
| `retirement_reason` | string | no | Optional. Text for the Verra retirement record. |

### `buy_offset`

Retire mass_g of verified credits for a buyer: cheapest-first matching, exactly-once (idempotent on purchase_id), returns a content-addressed offset certificate with per-fill costs. Payment settles via escrow. …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `buyer` | string | yes | Id of the party retiring credits. |
| `dry_run` | boolean | no | Optional. Preview the fills and cost without retiring. Default false. |
| `mass_g` | integer | yes | Grams of CO2e, a whole number. |
| `purchase_id` | string | yes | Your id for the purchase; repeating it never retires twice. |

### `buy_offset_budget`

Money-denominated offset purchase: retire the maximum cheapest-first verified mass whose exact cost fits inside budget_minor (never overspends). Built for callers whose restoration obligation is a currency amount — e.g. …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `budget_minor` | integer | yes | Most to spend, in minor units (cents); never exceeded. |
| `buyer` | string | yes | Id of the party retiring credits. |
| `dry_run` | boolean | no | Optional. Preview the fills and cost without retiring. Default false. |
| `purchase_id` | string | yes | Your id for the purchase; repeating it never retires twice. |

### `settlement_batch`

Read-only cash-settlement summary for a buyer: the list + exact sums (purchases, mass_g, cost_minor) of their retirements, optionally since an ISO-8601 timestamp — the statement a human settles in one transfer.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `buyer` | string | yes | Id of the party retiring credits. |
| `since` | string | no | Optional. ISO-8601 timestamp: only items at or after this time. |

### `net_position`

Buyer's carbon position: emitted (from agent-compute-ledger) minus retired. carbon_accountable == true when fully offset.

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `buyer` | string | yes | Id of the party retiring credits. |
| `emitted_g` | number | yes | Grams CO2e the buyer emitted, for example from the compute ledger. |

### `verify_certificate`

Verify an offset certificate: recompute its hash and check the ledger.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `certificate` | object | yes | The offset certificate object, unchanged. |

### `book`

The full credit book with per-credit and book-wide mass conservation totals.

*changes records; may need a caller credential (see below); structured output*

No inputs.

### `get_purchase`

Fetch a past purchase / offset certificate by id.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `purchase_id` | string | yes | Your id for the purchase; repeating it never retires twice. |

### `verify_retirement`

x402-C C4 check: confirm a retirement (offset_ref = purchase_id) actually retires at least required_g grams of verified conservation credit — the check that lets a carbon receipt's neutrality claim be honored. Returns …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `purchase_id` | string | yes | Your id for the purchase; repeating it never retires twice. |
| `required_g` | integer | no | Grams that must be covered by the retirement. Default 0. |

### `register_project`

Register a VERIFIED restoration project so retirements against its credits can be funded. verification_ref (D-Score / land-verification / registry id) is required — only verified conservation is funded. project_id is …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `beneficiary` | string | no | Optional. Who the project benefits. |
| `location` | string | no | Optional. Where the project is. |
| `methodology` | string | no | Optional. The methodology code, for example VM0047. |
| `name` | string | no | Optional. Project name. |
| `project_id` | string | yes | The restoration project's id. |
| `registry_ref` | string | no | Optional. The project's registry reference. |
| `verification_ref` | string | yes | Required. The verification attestation or registry id. |

### `project_funding`

Supply-side disbursement ledger: how much each restoration project has earned from retirements and is owed (gross_proceeds_minor + retired_g). Pass a project_id for one project, else all. Read-only — the CEO settles the …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `project_id` | string | no | Optional. One project's id; leave empty for all. |

### `list_projects`

List all registered restoration projects with their metadata.

*read-only; structured output*

No inputs.

### `disbursement_schedule`

Automated disbursement preview: for each verified restoration project, splits its newly-accrued proceeds into the Viridis Conservation withhold (default 15%, seeds the software/business) and the project payout (85%). …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `project_id` | string | no | Optional. One project's id; leave empty for all. |

### `certify_disbursement`

Freeze the current disbursement schedule into a certified, tamper-evident batch (content-addressed, hash-chained). Idempotent on batch_id; only newly-accrued proceeds for verified projects are certified (never disbursed …

*changes records; may need a caller credential (see below); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `batch_id` | string | yes | Your id for this batch; repeating it never certifies twice. |

### `verify_disbursement`

Recompute the disbursement certificate hash chain and confirm whole-book conservation of disbursed proceeds. Any party can audit disbursements.

*read-only; structured output*

No inputs.

### `describe_agent`

Describe this agent: name, version, purpose, every action it supports and the inputs each one takes. Read-only and free; call it first to learn how to use this server.

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
  "name": "agent-offset-clearinghouse-agent",
  "version": "0.6.0",
  "description": "Verified conservation credits matched to agent compute emissions: cheapest-first, exactly-once retirement, content-addressed offset certificates. The conservation flywheel of the agent economy.",
  "capabilities": [
    "list_credit",
    "delist_credit",
    "buy_offset",
    "buy_offset_budget",
    "net_position",
    "verify_certificate",
    "book",
    "get_purchase",
    "settlement_batch",
    "verify_retirement",
    "register_project",
    "project_funding",
    "list_projects",
    "disbursement_schedule",
    "certify_disbursement",
    "verify_disbursement",
    "verra_supply",
    "verra_retirement_record"
  ],
  "inputs": {
    "action": "str",
    "issuer": "str",
    "project_id": "str",
    "mass_g": "int > 0",
    "price_minor_per_kg": "int >= 0",
    "verification_ref": "str (required - verified supply only)",
    "buyer": "str",
    "purchase_id": "str",
    "budget_minor": "int > 0 (buy_offset_budget)",
    "dry_run": "bool (optional; O10 no mutation)",
    "since": "ISO-8601 str (optional, settlement_batch)",
    "emitted_g": "number >= 0",
    "certificate": "dict"
  },
  "outputs": {
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

This server is one of the fleet's shared rails, so on the hosted endpoint a tool that changes records needs a caller credential (`Authorization: Bearer <token>` with `X-Viridis-Agent-Id: <your agent id>`); without one it returns HTTP 401 and nothing changes. Read-only tools never need one. To get a credential, email <justin@viridisconservation.com>, or self-host from the source folder, where no credential applies.

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`agent-offset-clearinghouse-agent/`](../../agent-offset-clearinghouse-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
