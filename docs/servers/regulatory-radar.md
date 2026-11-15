# io.github.jdhart81/regulatory-radar

Live authoritative-source regulatory change evidence, compliance screening, and deadline monitoring

| | |
|---|---|
| Registry name | `io.github.jdhart81/regulatory-radar` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/regulatory-radar/mcp` |
| Version | 0.2.0 |
| Tools | 6 |
| Source | [`regulatory-radar-agent/`](../../regulatory-radar-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-regulatory-radar": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/regulatory-radar/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-regulatory-radar https://mcp.viridisconservation.com/regulatory-radar/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `scan_regulations`

Scan a jurisdiction (e.g. EU, US, california, or CA for Canada), optionally filtered by sector and/or a free-text query over regulation names, descriptions and requirements. Returns regulations with urgency flags and …

*read-only; $0.25 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `jurisdiction` | string | no | Where the company operates. One of: eu, uk, us, california, ca, au, jp, sg, global (ca is Canada; use california for the US state). A US state or EU member state is read as us or eu. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `query` | string | no | Optional words to look for in rule names, descriptions and requirements, for example: scope 3. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `sector` | string | no | Optional industry filter. One of: agriculture, consumer_goods, energy, financial_services, fisheries, forestry, manufacturing, technology. |

### `assess_compliance`

Screen a company's posture against applicable regulations. Returns compliance level, percentage, gaps, and remediation priorities. Gated obligations count only when their applicability is established from inputs. …

*read-only; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `annual_revenue_usd` | number | no | Optional. Latest annual revenue in US dollars, for scope tests. |
| `company_name` | string | yes | The company's name. |
| `disclosures` | array | no | Optional. Disclosures the company already makes, for example ["CSRD"]. |
| `entity_profile` | object | no | Optional. Facts for applicability tests, for example employees or listing. |
| `jurisdiction` | string | yes | Where the company operates, for example california, us, eu or uk. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `prior_year_revenue_usd` | number | no | Optional. Prior year's revenue in US dollars. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `sector` | string | yes | Industry, for example energy or manufacturing. |

### `monitor_changes`

Watch curated regulatory effective dates and deadlines in a bounded window. `since_days` controls both recently effective dates behind today and effective/deadline dates ahead of today. This is a source-linked watch …

*read-only; $0.25 per call after the free daily calls (x402 catalog); structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `jurisdiction` | string | no | Where the company operates, for example california, us, eu or uk. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `since_days` | integer | no | Optional. Window in days, before and after today. Default 90. |
| `topics` | array | no | Optional. Topics to keep, for example ["ghg", "scope 3"]. |

### `watch_changes`

Poll for text changes on official regulator pages since your last poll. Radar Watch keeps a durable log of every detected change to the registry-owned official sources (SEC, European Commission, EFRAG, CARB). Pass the …

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `jurisdiction` | string | no | Where the company operates, for example california, us, eu or uk. |
| `max_age_hours` | integer | no | Optional. Refresh the sources if the last sweep is older. 1 to 168, default 24. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |
| `since` | integer | no | The cursor from your previous answer. 0 for everything. |
| `topics` | array | no | Optional. Topics to keep, for example ["ghg", "scope 3"]. |

### `build_evidence_pack`

Build a live, source-hashed regulatory change evidence pack. Fetches only the product's registry-owned regulator URLs, reports source retrieval timestamps and SHA-256 hashes, distinguishes a first baseline from a …

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `company_profile` | object | no | Optional. Company facts to tailor the pack. |
| `jurisdiction` | string | yes | Where the company operates, for example california, us, eu or uk. |
| `persist_snapshot` | boolean | no | Optional. Store this retrieval for change detection. Default true. |
| `since_days` | integer | no | Optional. Window in days, before and after today. Default 90. |
| `source_ids` | array | no | Optional. Only these official sources. |
| `topics` | array | no | Optional. Topics to keep, for example ["ghg", "scope 3"]. |

### `describe_agent`

Fleet-standard self-description: capabilities, inputs, outputs.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "scan_regulations",
  "arguments": {
    "jurisdiction": "california",
    "sector": "energy"
  }
}
```

Response (shortened):

```json
{
  "jurisdiction": "california",
  "included_jurisdictions": [
    "california",
    "global",
    "us"
  ],
  "sector": "energy",
  "total_regulations": 7,
  "urgent_count": 0,
  "past_key_date_count": 2,
  "regulations": [
    {
      "id": "ca-sb261-2026",
      "name": "California SB 261 — Climate risk reports; enforcement enjoined",
      "jurisdiction": "california",
      "effective_date": "2023-10-07T00:00:00",
      "deadline": "2026-01-01T00:00:00",
      "days_until_deadline": -319,
      "deadline_status": "past",
      "date_type": "first_reporting_deadline",
      "legal_status": "statutory_requirement_enforcement_enjoined",
      "standards": [
        "California SB 261",
        "TCFD"
      ],
      "requirements_count": 4,
      "source_url": "https://ww2.arb.ca.gov/public-comments/climate-related-financial-risk-reports-sb-261-docket",
      "source_verified_on": "2026-07-25",
      "scope_note": "The statutory date has passed, but CARB says a Ninth Circuit injunction prevents enforcement for failure to post and submit by that date. CARB's public docket accepts voluntary reports. Verify current litigation and entity-specific coverage before relying on this entry."
    },
    {
      "id": "ca-sb253-2026",
      "name": "California SB 253 — First Mandatory Scope 1+2 Filing",
      "jurisdiction": "california",
      "effective_date": "2026-10-12T00:00:00",
      "deadline": "2026-11-10T00:00:00",
      "days_until_deadline": -6,
      "deadline_status": "past",
      "date_type": "first_reporting_deadline",
  …
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`regulatory-radar-agent/`](../../regulatory-radar-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
