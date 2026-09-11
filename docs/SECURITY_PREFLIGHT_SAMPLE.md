# See what a Security Preflight check catches

**For MCP developers reviewing a manifest or policy change before release.**
This synthetic example shows two metadata problems and the checks after correcting them. It runs locally without a wallet, network request, signing key or paid call.

| Supplied metadata | Before | After |
|---|---|---|
| `delete_records` input schema | Accepts undeclared fields | `additionalProperties: false` |
| Approval policy | No approval requirement for `delete_records` | Tool listed in `approval_required_tools` |
| Static findings | One high-severity finding and one warning | No findings or warnings in these six checks |

The proposed integration decision is to close the schema and declare approval before release. You still need to implement and test both controls in the running application. Changing a declaration does not enforce it.

## Reproduce it free

From the repository root, with Python 3.10 or newer:

```sh
python3 scripts/preflight_sample_report.py
```

Read the [complete synthetic inputs and output](../examples/security-preflight-sample-report.json).
The report identifies the scanner version and source hash. It is an **unsigned local example**, not a hosted assessment receipt, customer result, independent audit or security certification. It does not execute `delete_records` or access the example endpoint.

## When to use the hosted assessment

Use the hosted service when you want these supplied-input checks executed by Viridis with a signed assessment receipt and a stored baseline for subsequent change checks. The list price is **$1 USDC per assessment**; an eligible introductory quote may be **$0.01**. Your fresh quote and explicit spending ceiling govern.

[Start with a free quote, then authorize one capped purchase](SECURITY_PREFLIGHT_BUYER_QUICKSTART.md).
You supply one agent's manifest, schemas, policy and samples. The service does not fetch the deployed endpoint or test runtime security. The public reference check can be inspected locally; the paid value is hosted execution, receipt issuance and the maintained change-check workflow.

After a paid result, record the specific decision the findings helped you make. Use the private feedback mechanism described in the buyer guide; never post your complete paid-result file, credentials or feedback token in a public issue.

## Repeat only for a real need

The free change check reuses an unchanged assessment. A relevant change may justify a fresh assessment, with a new quote and purchase authorization. There is no automatic subscription or promised human review in this offer.
