# io.github.jdhart81/disclosure-compiler

[![mcptry](https://mcptry.com/badge/io.github.jdhart81/disclosure-compiler)](https://mcptry.com/servers/io.github.jdhart81/disclosure-compiler)

Deterministic cited compliance disclosure drafts with verified GHG lineage.

| | |
|---|---|
| Registry name | `io.github.jdhart81/disclosure-compiler` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/disclosure-compiler/mcp` |
| Version | 0.1.1 |
| Tools | 5 |
| Source | [`disclosure-compiler-agent/`](../../disclosure-compiler-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-disclosure-compiler": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/disclosure-compiler/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-disclosure-compiler https://mcp.viridisconservation.com/disclosure-compiler/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `compile_disclosure`

Compile a deterministic, cited disclosure draft from supplied company facts and an optional verified GHG-ledger result. Missing required datapoints remain explicit gaps; no prose or values are fabricated. Frameworks: …

*changes records; $2.00 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `company_facts` | object | no | Facts about the company, as an object. Only supplied facts are used; anything missing is listed as a gap. Keys read, by framework: ca-sb253: assurance_status, company_name, ghg_methodology, organizational_boundary, reporting_period; esrs-e1: climate_targets, company_name, ghg_intensity, reporting_period, transition_plan; ifrs-s2: climate_governance, climate_resilience, climate_strategy, climate_targets, company_name, reporting_period, risk_management_process; sec-climate: board_oversight, climate_targets, company_name, management_role, material_climate_risks, reporting_period, risk_management_process; tnfd: company_name, leap_process, nature_dependencies_and_impacts, nature_governance, nature_metrics, nature_risks_and_opportunities, nature_targets, priority_locations, reporting_period. |
| `framework` | string | no | Which disclosure to draft. One of: ca-sb253, esrs-e1, ifrs-s2, sec-climate, tnfd. |
| `ghg_result` | object | no | Optional. The `data` object of a ghg-ledger calculate_inventory result, passed unchanged; it fills the emission datapoints and is verified before use. |
| `options` | object | no | Must hold `applicability`: {framework: the same framework id, applies: true, reason: why it applies to this company}. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `list_frameworks`

List bundled framework IDs, coverage, source lineage, version, and the framework-pack digest.

*read-only; structured output*

No inputs.

### `get_framework`

Return one bundled framework's required datapoints, mappings, sources, and framework-pack lineage.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `framework` | string | yes | Framework id, for example esrs-e1 or ca-sb253; see list_frameworks. |

### `verify_result`

Recompute a disclosure draft audit hash, notary payload, structural invariants, and framework-pack currency. Pass the prior result as JSON.

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `result_json` | string | yes | The full compile_disclosure result, as a JSON string, unchanged. |

### `describe_agent`

Return deterministic capabilities, version, pack digest, pricing, composition, and the professional-review disclaimer.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "compile_disclosure",
  "arguments": {
    "company_facts": {
      "climate_targets": {
        "scope": "Scopes 1-3",
        "target": "50% by 2035"
      },
      "company_name": "Acme Climate Works",
      "ghg_intensity": {
        "unit": "tCO2e/USDm revenue",
        "value": "0.012"
      },
      "reporting_period": "2026",
      "transition_plan": {
        "status": "board-approved",
        "target_year": 2035
      }
    },
    "framework": "esrs-e1",
    "options": {
      "applicability": {
        "applies": true,
        "framework": "esrs-e1",
        "reason": "company is in CSRD scope"
      }
    }
  }
}
```

Response (shortened):

```json
{
  "status": "ok",
  "data": {
    "draft_status": "partial",
    "label": "disclosure draft for professional review",
    "framework": {
      "id": "esrs-e1",
      "name": "ESRS E1 — Climate change",
      "status": "mvp_structured_datapoints"
    },
    "applicability": {
      "framework": "esrs-e1",
      "applies": true,
      "reason": "company is in CSRD scope",
      "source": "caller",
      "forced": false,
      "force_reason": null
    },
    "inputs": {
      "framework": "esrs-e1",
      "company_facts": {
        "company_name": "Acme Climate Works",
        "reporting_period": "2026",
        "transition_plan": {
          "status": "board-approved",
          "target_year": 2035
        },
        "climate_targets": {
          "scope": "Scopes 1-3",
          "target": "50% by 2035"
        },
        "ghg_intensity": {
          "value": "0.012",
          "unit": "tCO2e/USDm revenue"
        }
      },
      "ghg_result": null,
      "options": {
        "applicability": {
          "framework": "esrs-e1",
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`disclosure-compiler-agent/`](../../disclosure-compiler-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
