# Viridis Regulatory Radar (MCP server)

Registry name: `io.github.jdhart81/regulatory-radar`
Remote endpoint (Streamable HTTP): `https://mcp.viridisconservation.com/regulatory-radar/mcp`
Source: this folder (`regulatory-radar-agent/`), Apache-2.0.

Regulatory Radar screens energy and climate regulations for a jurisdiction and
sector from a curated, source-linked dataset: which requirements apply, their
effective dates and deadlines, and which are urgent. It also assesses a
company's disclosure posture and watches upcoming key dates.

It is technology-assisted screening, not legal advice. Confirm applicability
and deadlines with the cited authority or qualified counsel.

## Tools

| Tool | Price | Inputs | Output |
|---|---|---|---|
| `describe_agent` | free, read-only | none | Capabilities, inputs and outputs |
| `scan_regulations` | $0.25 (10 free/day over MCP) | `jurisdiction` (required: e.g. `US`, `EU`, `california`, `CA` for Canada), `sector`, `query` | Applicable regulations with effective dates, deadlines, urgency flags, legal status and source URL |
| `assess_compliance` | $0.25 (10 free/day over MCP), read-only | `company_name`, `sector`, `jurisdiction` (required), `disclosures`, `annual_revenue_usd`, `prior_year_revenue_usd`, `entity_profile` | Compliance level and percentage, gaps, remediation priorities. Screening only, not legal advice. SB 253 counts only when revenue is over $1B in each of the two previous fiscal years and `entity_profile` establishes a US-formed business entity doing business in California with no exemption (17 CCR 96071-96072); missing inputs list it under `applicability_unconfirmed` and the level is `undetermined`, and a failing condition lists it under `out_of_scope` |
| `monitor_changes` | $0.25 (10 free/day over MCP) | `jurisdiction` (required), `since_days` (1–365), `topics` | Recently effective and upcoming dates/deadlines inside the window |
| `build_evidence_pack` | $0.25 (10 free/day over MCP) | `jurisdiction` (required), `topics`, `company_profile`, `source_ids`, `since_days`, `persist_snapshot` | Source-hashed change evidence pack fetched only from registry-owned regulator URLs |

## Example

`scan_regulations` request (MCP `tools/call` arguments):

```json
{
  "jurisdiction": "US",
  "sector": "energy"
}
```

Response from the live server (first of 7 regulations shown):

```json
{
  "jurisdiction": "us",
  "included_jurisdictions": [
    "california",
    "global",
    "us"
  ],
  "sector": "energy",
  "total_regulations": 7,
  "urgent_count": 2,
  "past_key_date_count": 5,
  "disclaimer": "Technology-assisted screening only; confirm applicability and deadlines with the cited authority or qualified counsel.",
  "status": "success",
  "regulations": [
    {
      "id": "tnfd-disclosure-2024",
      "name": "TNFD Disclosure Requirements 2024",
      "jurisdiction": "global",
      "effective_date": "2024-06-01T00:00:00",
      "deadline": "2025-12-31T00:00:00",
      "days_until_deadline": -308,
      "deadline_status": "past",
      "date_type": "reporting_deadline",
      "legal_status": "binding",
      "standards": [
        "TNFD"
      ],
      "requirements_count": 4,
      "source_url": "https://tnfd.global",
      "source_verified_on": null,
      "scope_note": null
    }
  ]
}
```

## Connect, pricing and ownership

No account or API key is needed. Client setup for Claude, ChatGPT, VS Code and
the Claude, OpenAI and xAI APIs, plus payment options and how the hosted
service relates to this repo: [docs/HOSTED_MCP.md](../docs/HOSTED_MCP.md).

Over the HTTP x402 route (`POST https://mcp.viridisconservation.com/x402/regulatory-radar/scan_regulations`)
each caller's first scan per UTC day is free while that offer is active; later
calls return HTTP 402 with the quote. A monthly Starter Seat ($19, 200 calls)
covers this server, GHG Ledger and Quantity Takeoff.

## Self-host

```sh
pip install -r requirements.txt
python3 adapters/mcp_server.py          # stdio
```
