# io.github.jdhart81/protogen

Viridis LLC revenue MCP CAD agent: provides a callable CAD design environment and manufacturing planning services to other agents

| | |
|---|---|
| Registry name | `io.github.jdhart81/protogen` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/protogen/mcp` |
| Version | 0.3.1 |
| Tools | 6 |
| Source | [`protogen-agent/`](../../protogen-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-protogen": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/protogen/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-protogen https://mcp.viridisconservation.com/protogen/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `create_cad_workspace`

Create a ProtoGen CAD workspace for another agent or workflow.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `constraints` | object | no | Optional. Design constraints, for example size limits or loads. |
| `design_goal` | string | yes | What the design must achieve, in plain words. |
| `owner_agent` | string | yes | Id of the agent or workflow that owns the workspace. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `project_name` | string | yes | Name for the CAD workspace. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `generate_cad_design`

Generate a parametric CAD design contract in a ProtoGen workspace.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `design_intent` | string | no | Optional. What the part is for. |
| `dimensions_mm` | object | yes | Overall dimensions in millimetres, for example {"length": 120, "width": 40}. |
| `features` | array | no | Optional. Features such as holes or fillets. |
| `material` | string | no | Optional. Material. Default aluminum. |
| `output_formats` | array | no | Optional. Formats to prepare: openscad, step_contract, manufacturing_brief. |
| `part_name` | string | yes | Name of the part. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `workspace_id` | string | yes | The workspace id returned by create_cad_workspace. |

### `export_cad_design`

Export a CAD design as OpenSCAD, STEP contract metadata, or manufacturing brief.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `design_id` | string | yes | The design id returned by generate_cad_design. |
| `export_format` | string | no | openscad (default), step_contract or manufacturing_brief. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |

### `manufacturing_plan_from_spec`

Generate a manufacturing plan, BOM, DFM notes, and cost estimate from a product spec.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `product_spec` | object | yes | The product specification, as an object. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `describe`

Return ProtoGen capabilities and current CAD environment status.

*read-only; structured output*

No inputs.

### `health`

Return ProtoGen health and workspace counts.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "describe",
  "arguments": {}
}
```

Response (shortened):

```json
{
  "name": "protogen-agent",
  "version": "0.3.1",
  "role": "Viridis revenue MCP CAD design environment and manufacturing planning assistant",
  "capabilities": [
    "cad_workspace_creation",
    "parametric_cad_generation",
    "cad_export_contracts",
    "spec_parsing",
    "bom_generation",
    "process_planning",
    "dfm_analysis",
    "cost_estimation"
  ]
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`protogen-agent/`](../../protogen-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
