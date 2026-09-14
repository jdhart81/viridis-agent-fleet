# Measure completed Wu Wei workloads

Use `scripts/wu_wei_measure_savings.py` to compare completed runs locally without provider calls, payments, or production writes. This complements the paid planner; it is not deployed as a fleet endpoint.

Freeze the task manifest, evaluation rubric and cost scope before running either arm. Run identical inputs through the existing baseline and the chosen Wu Wei route, keeping all attempts, including failed attempts, retries and fallbacks. Evaluate both outputs against the same rubric. For this initial strict comparison, every task in both arms must pass; this prevents aggregate pass counts hiding different failures.

Fill in `docs/business/examples/wu-wei-measurement-template.json`. Null costs are intentionally unknown and produce INCOMPLETE_EVIDENCE. Each actual cost is in integer microdollars (1 USD = 1,000,000). Cost evidence references should point to retained provider usage/billing records or measured local operating costs. Route versions identify the executed model/configuration. Input hashes must cover the same canonical task input, excluding route-specific settings. Quality evidence should retain the output, rubric and assessment.

The overhead for each arm includes costs not already counted in attempts: planning/service fees, routing, verification, payment charges and integration costs allocated to this workload. Count each cost once. A zero overhead needs an explicit evidence reference explaining the scope. Cost scope must be identical in both arms. Include unsuccessful execution costs. Report the expense of running both benchmark arms separately from any ongoing operational savings.

Run from the workspace root:

```sh
python3 scripts/wu_wei_measure_savings.py docs/business/examples/wu-wei-measurement-template.json --output /tmp/wu-wei-measured-report.json
```

The tool rejects unmatched inputs, duplicate/missing task results and invalid costs. It withholds a qualified savings value when evidence is incomplete or a quality gate fails. Negative differences are retained. SHA-256 digests identify the submitted data and report, but do not certify that records are true. Evidence references are caller supplied and are not fetched or independently verified. The tool cannot detect omitted attempts if the caller leaves them out; reconcile the manifest and cost records against provider logs before relying on a result.

This is an observed comparison for the supplied task set, not a statistical guarantee, a verified invoice or a forecast. Energy remains unmeasured. Run a representative held-out benchmark and reconcile receipts before claiming customer savings or adopting percentage-of-savings billing.
