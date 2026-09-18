# Repository funnel measurement

Use `python3 scripts/repo_funnel_snapshot.py --output-dir /tmp/viridis-repo-funnel`
to capture the existing public health aggregates. It makes one read-only health
request, signs no payment, and exports no wallet addresses or buyer input.
A failed fetch leaves previous snapshots unchanged.

## What is measured

| Stage | Existing evidence | Limitation |
|---|---|---|
| GitHub referral | Landing requests classified as GitHub by HTTP referrer | Not unique people; referrer suppression loses attribution |
| Service choice | Valid unpaid HTTP quote requests, when the versioned counter is deployed | Includes retries; not unique buyers and not MCP/A2A-wide coverage |
| First purchase | External payer cohort with buyer-declared `github` source | Buyer-declared source is not a tracked visitor identity |
| Successful delivery | Versioned delivery counts grouped by the payment's declared source | Unavailable on older gateways; not buyer acceptance |
| Useful result | Versioned useful-feedback counts grouped by payment source | Requires delivered result and recorded buyer feedback |
| Repeat purchase | GitHub payer cohorts at 7, 14, and 30 days | Only mature eligible cohorts have a rate |

Do not divide buyers by page views: the records have different attribution,
time coverage, and denominators. Unknown historical payer sources remain
unknown. A reported zero GitHub cohort does not prove no GitHub visitor bought.

## Preserve genuine buyer attribution

If GitHub is how you actually found the service, include `--source github` in
both the unpaid quote and any separately authorized paid invocation of
`scripts/viridis_preflight_buy.py`. The client forwards the existing finite
`X-Viridis-Acquisition-Source` header. This is optional and buyer-declared.
Use `--source internal` for operator rehearsals; omit the flag if unknown.
Never tag our own verification requests as acquired customers.

For example, a GitHub-discovered buyer can inspect an unpaid quote:

```sh
python3 scripts/viridis_preflight_buy.py \
  --inputs examples/security-preflight-inputs.json --source github
```

Follow the [buyer walkthrough](SECURITY_PREFLIGHT_BUYER_QUICKSTART.md) for payment,
result verification, feedback, and a later buyer-authorized repeat. MCP clients
that do not propagate the acquisition header remain unattributed.

## Versioned production contracts

The report accepts `viridis-quote-source-counts-v1` at `repo_funnel` and
`viridis-source-outcomes-v1` within HTTP settlement telemetry. An older gateway
continues to report those stages as unavailable. Incomplete quote persistence
also reports unavailable rather than a lower apparent count.

Quote requests are counted only after a known route and valid input reach an
unpaid quote response. Retries count again. Declared internal quotes are excluded;
raw referrers, wallet addresses, and input payloads are not saved in that counter.
Delivery and usefulness are aggregated from existing durable payment records;
self-payments and records explicitly marked internal are excluded.

Outcome attribution uses each payment's declared source. Retention cohorts use
the payer's first purchase source. These are different groupings, and neither is
a visitor-to-payer identity join. No conversion rate is calculated.

Deployment of these contracts is a separate operation from merging this report.
Rehearse the exact production image with copied state and verified backups first.
