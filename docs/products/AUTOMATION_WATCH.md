# Viridis Automation Watch

Prepared 2026-09-16. Launch offer: $299 per 30-day service period, one client
at a time until the first accepted delivery. This is a new standalone service;
it does not alter the $149 Watch continuation offered after the Reliability Sprint.

## Buyer and problem

Small businesses and agencies with one existing n8n, Make, Zapier or similar
workflow who need someone to notice failed runs and unexpected inactivity,
explain what happened, and identify the next action. Platform compatibility
must be confirmed from a sanitized sample before purchase.

## Included

- One existing workflow connecting up to two systems.
- Initial baseline: expected schedule, available execution evidence, escalation
  contact and agreed service start. Requirements/access must be ready first.
- One daily evidence check throughout the 30 days. Record missed checks as gaps.
- Failure, inactivity and evidence-availability detection, bounded by available
  logs. A successful execution does not prove a successful business outcome.
- Human exception review and Upwork issue notification by the next business day,
  Monday-Friday. This is not 24/7 incident response.
- Four weekly digests, a day-30 summary and prioritized action plan.
- One revision of the final report.

No production changes, automatic retries, guaranteed uptime, guaranteed recovery,
new workflows, unlimited repairs, or security/compliance certification. Any repair
needs a separately agreed scope. Duplicate/missing destination records are assessed
only when authorized source and destination evidence support reconciliation.

## Renewal and sales

Upwork Project Catalog sells the first fixed-scope 30-day period. Renewal is a
separate funded milestone or repurchase, not automatic monthly billing. Present
renewal with the day-23 report, with buyer-confirmed value and next-month scope.
Keep all Upwork-originated contracting, communication and payment on Upwork.
An alternative client-configured weekly contract exists, but is a different offer
and must not silently replace the $299/30-day terms.

Historical catalog draft: https://www.upwork.com/nx/project-dashboard/2100356601582166367
September 17 authenticated refresh: the only current catalog draft is a security
review offer; Approved 0 and Under Review 0. The historical project ID must not be
represented as a current Automation Watch checkout. Watch remains an offer draft.
No Connects required to create the catalog project. Upwork review/publication and
actual customer acquisition remain separate from preparing this offer.

Demand evidence: a public Upwork property-management automation posting requested
ongoing maintenance, error handling and deduplication:
https://www.upwork.com/freelance-jobs/apply/Automation-Engineer-for-Property-Management-Maintenance-Workflow_~022089093857264727895/
This is a demand signal, not proof someone will buy this particular package.
September 17 refresh: the public posting now says the job is no longer available.
Keep this reference as historical demand evidence only; do not apply to it.
Recurring weekly payment reference:
https://support.upwork.com/hc/en-us/articles/45819532067219-How-to-set-up-a-recurring-weekly-payment-for-your-freelancer

## Delivery readiness and operating procedure

September 17 local component: `DELIVERY_CHECK.md` documents the agent-callable
destination-evidence check and synthetic demo. It supplements execution checks
when a customer's authorized, complete source and destination exports can be
mapped to its one-create-per-event contract. This does not establish a live
connector, customer monitor, or expanded service commitment.

1. Qualify platform, expected activity, logs/API availability, authorization,
   data sensitivity, timezone and technical owner before accepting scope.
2. Agree service dates only after access and inputs are ready. Use buyer-owned,
   least-privilege access. Do not collect passwords in intake text.
3. Validate one real, minimized sample. Map it to the local monitor input schema.
   The generic report engine is not a deployed connector or customer case study.
4. Provision a customer-isolated collector and daily schedule only within the
   funded engagement. Test collection, stale-input detection, failed-run detection
   and a missed-check alert. Do not mark onboarding complete until these pass.
5. Save each daily report with coverage window and check time. Monitor the monitor:
   one missing report in 26 hours requires human attention. Credential/API errors
   produce UNKNOWN, never a healthy result.
6. Human reviews findings and sends concise Upwork updates within the stated window.
   Do not expose customer payloads to models unless specifically authorized.
7. Weekly digest: days checked/expected; unavailable days; observed execution
   counts and failures; evidence limits; incident status; prioritized actions.
8. Day 30: final report, buyer acceptance request, separately funded renewal if
   desired. Revoke access and agree retention/deletion at end of service.

## Economics and stopping rules

$299 is a launch hypothesis. Illustration only: at a 15% platform fee, $20
monthly infrastructure and one hour of human work valued at $50, contribution
would be $184.15 before tax/other overhead. At three human hours it is $84.15.
Check the actual fee on the contract; do not assume the earlier proposal fee.
Track onboarding and human minutes, incidents, accepted reports and renewals.
Do not scale until one independent customer pays, accepts useful delivery and
renews. Reprice or narrow if support consistently exceeds three hours per month.
Do not build additional general fleet infrastructure to compensate for no buyers.

## Cover asset

Built-in image generation; final file:
`deliverables/automation-watch/2026-09-16/upwork-cover-v2.png`.
Prompt: polished landscape marketplace cover, deep forest green, ivory text,
restrained lime, abstract connected workflow nodes, generous margins. Exact copy:
VIRIDIS / Automation Watch / Daily checks / Weekly reports. Version 2 centers
all copy within the middle 50 percent of width and height to accommodate the
Upwork crop. No third-party logos, contact details, customer claims, metrics or
fake dashboard. Version 1 retained locally; its edge-aligned text cropped badly.
