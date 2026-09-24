# Viridis Delivery Check

September 17, 2026 — public free pilot deployed; no paid customer service activated.

Live page: https://mcp.viridisconservation.com/delivery-check

Live MCP: https://mcp.viridisconservation.com/delivery-check/mcp/

Release and rollback: `docs/deployment/DELIVERY_CHECK_RELEASE_2026-09-17.md`.

## The product decision

Make Viridis the component an operator uses to answer: “Did every expected item
actually arrive, with the right content, and without a duplicate?” Start with
one daily lead-to-CRM handoff owned by an automation agency. The recurring value
is a reviewed exception report that helps an operator find a lost or duplicated
business record. Daily work creates a reason for daily checks; it does not yet
establish willingness to pay for them.

The core is deterministic and uses no model calls. An agent can call it through
MCP or consume its JSON report. Inputs are locally hashed source records and
destination readbacks with explicit coverage. It reuses the existing workflow
reconciliation component and supplements Automation Watch's execution checks.

## What exists today

- Public stateless HTTP and MCP check, a working synthetic sample page, and local CLI/stdio equivalents.
- Public qualification path to the existing Reliability Sprint; proposed $299/30-day Watch requires agreed scope and funding.
- Local payload preparation, tenant checks, evidence freshness and eventual
  consistency grace window, bounded input size and per-event exception reports.
- Missing, duplicate, mismatched, shared-destination and uncertain-write detection.
- Machine-readable result plus readable report with content hash.
- Reproducible synthetic broken/corrected, partial-export and timeout demos.
- Local daily receipt runner with contract-bound scope, period summaries,
  missed-check detection and evidence-gap history that survives late recovery.

No hosted paid endpoint, live collector, customer schedule, alert delivery,
production fleet registration, payment mandate or accepted customer delivery
exists for this component. It does not assess free-text factual correctness.
It depends on honest, complete, correctly mapped collector evidence.

## How we will sell the first useful result

Reuse the **$299 / 30-day Automation Watch** offer draft. Authenticated September
17 review confirmed it is not a published Upwork catalog service. Limit the first engagement to
one existing workflow, two systems, at most 1000 source and 1000 destination
records per agreed daily window. Confirm one real minimized sample before
accepting the order. Custom integration beyond the included baseline needs the
existing **$995 Reliability Sprint** or another explicitly agreed scope.

The buyer gets one daily check, reviewed exceptions by the next business day,
four weekly digests and a final summary under Automation Watch's existing terms.
Repair, 24/7 response and automatic retries are excluded. Do not change the
separate $149 Watch continuation already offered to accepted Sprint customers.
Upwork-originated contracts and payments stay on Upwork. Catalog publication
and funding still require their own actual platform receipts.

Customer promise, after sample qualification: “We compare the records that
should arrive with the destination evidence and give you a daily exception
report, including when the evidence is insufficient to tell.”

## Daily-payment hypothesis

After three independent paying customers require the same collector/contract,
test a machine-only price of **$1 per completed daily report**, up to the current
1000-record limits, without human incident handling. This is an internal price
hypothesis, not published pricing or a current billing capability. Unavailable
collection should not trigger an unattended paid check; an evaluated report
containing delivery exceptions is useful work, not necessarily a failed service.
Refund and incomplete-report terms must be agreed before charging.

Use existing fleet payment rails only after a buyer requests hosted access.
Bind buyer mandate, workflow, window, policy and exact input to the request;
deduplicate retries; enforce a spending cap and record delivered/failed service
outcomes separately from whether the customer's workflow succeeded. Never call
ourselves to simulate demand. No speculative paid model or hosting budget.

100 independently paid reports a day at $1 would be $3,000 gross over 30 days;
that is arithmetic, not a forecast or profit. Hosting, collection, payment fees,
support, refunds and labor must be measured. The reason to pay us must become
validated collectors and dependable operation, because a standalone comparator
is easy to copy. Stop if native platform checks solve the buyer's problem more
cheaply or the buyer will not fund reliable collection.

## Flywheel and stopping rule

1. Show a real operator the clearly labeled synthetic failure demo.
2. Qualify one actual handoff and run a minimized sample with authorization.
3. Fund one bounded Watch period or repair scope through an existing verified rail.
4. Deliver daily evidence; record time, collection gaps, false positives and costs.
5. Obtain buyer confirmation of usefulness and a separately funded renewal.
6. Reuse only the collector/contract repeatedly requested by independent buyers.

Do not spend more than one additional working day on generic functionality before
obtaining a qualified sample. Seek five qualified conversations; if none will
share an authorized sample and discuss a funded check, revisit this offer rather
than add agents or features. This is a manual next-action plan, not a new schedule.

## Evidence reviewed today

- [n8n user discussion](https://community.n8n.io/t/setting-up-error-workflow-upon-ai-agent-tool-failure/252743)
  describes agent/tool failures not reaching expected error handling. Problem
  evidence; no purchase commitment.
- [n8n monitoring template](https://n8n.io/workflows/13290-monitor-scheduled-workflow-health-in-n8n-with-automatic-trigger-checks/)
  addresses schedules that stop triggering. An existing alternative, and a
  reminder that Viridis must add destination evidence rather than just uptime.
- [CRM automation buyer request](https://www.upwork.com/freelance-jobs/apply/CRM-Workflow-Automation-Specialist-HubSpot-n8n-Make-API-Integrations_~022100127476303446941/)
  explicitly asks about duplicate prevention, failure handling and conflicting
  CRM records. Public page showed $30–$60/hour and 50+ proposals. The requested
  broad expert role exceeds this component; prior HubSpot expertise is not
  established by our synthetic demo. Demand evidence, not an application target
  without further qualification.
- [Next Play buyer request](https://www.upwork.com/freelance-jobs/apply/Automation-Systems-Integration-Specialist-n8n-Airtable-APIs-CRM-Content_~022094565192345756227/)
  describes existing workflows, per-record validation, exceptions and ongoing
  maintenance. A possible narrow reliability subproject; full role is broader.
  Later authenticated review disqualified it: $5–$9/hour, 23 Connects, zero
  available Connects, and personal platform-experience requirements. Do not apply.
- The property-management posting previously cited by Automation Watch now says
  [job no longer available](https://www.upwork.com/freelance-jobs/apply/Automation-Engineer-for-Property-Management-Maintenance-Workflow_~022089093857264727895/).
  Retain it as historical evidence, not a live lead.

Current commercial baseline remains 0.28 USDC in external settlements, zero
verified paid deliveries, zero repeats and zero MRR. This build changes readiness,
not that commercial baseline.
