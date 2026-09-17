# Repository funnel measurement

Use `python3 scripts/repo_funnel_snapshot.py --output-dir /tmp/viridis-repo-funnel`
to capture the existing public health aggregates. It makes one read-only health
request, signs no payment, and exports no wallet addresses or buyer input.
A failed fetch leaves previous snapshots unchanged.

## What is measured

| Stage | Existing evidence | Limitation |
|---|---|---|
| GitHub referral | Landing requests classified as GitHub by HTTP referrer | Not unique people; referrer suppression loses attribution |
| Service selection | Not currently exposed | Report unavailable; do not substitute catalog views |
| First purchase | External payer cohort with buyer-declared `github` source | Buyer-declared source is not a tracked visitor identity |
| Successful delivery | Fleet-wide external paid-result delivery counters | GitHub-specific delivery is not exposed |
| Useful result | Fleet-wide buyer feedback marked useful | Keep separate from transport delivery |
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

## Remaining instrumentation boundary

End-to-end attribution is incomplete. A production change would need durable,
finite source-by-route aggregates for selection/quote, settled delivery, and
buyer feedback, with replay protection and internal activity excluded. Preserve
source through the buyer journey without storing raw referrers or inventing
identities. Review this against the current private production gateway: the
public reference gateway is not a deployable replacement for it.

Until that change is reviewed and deployed, the report deliberately marks
source-specific selection, delivery, and usefulness unavailable. Existing
payer retention and referral counts are usable now.
