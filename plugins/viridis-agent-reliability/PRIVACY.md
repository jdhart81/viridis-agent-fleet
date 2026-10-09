# Current technical data disclosures

Public policy: https://viridisconservation.com/privacy (soft-launch notice v0.3,
effective 2026-08-12). Operator: Viridis North LLC. Contact:
justin@viridisconservation.com. Refer to the policy for current request procedures;
no new deletion or retention promise is made here.

This skill reads no local credentials and requests no secret user_config input.
The submitted package contains no environment-backed authentication examples.
User-supplied diagnostic material remains in the host conversation. A user-requested
bounded public discovery request may go to the supplied third-party origin and
reveal the requested URL and request metadata. The diagnostic excludes private
inputs and credentials. Hosted identity authorization uses Supabase; the
existing gateway payment verification uses Stripe, not a card-entry tool in this
plugin. Tool calls share their supplied arguments with the named Viridis MCP
endpoint. The skill reviews supplied declarations and public discovery evidence; it
does not automatically invoke the attached priced tools.

An explicitly authorized paid assessment returns its original signed result,
including subject identifiers, detailed derived findings, digests and signature.
Order storage retains caller/order/session identifiers, the exact intake hash,
payment/tax evidence, fulfillment state and result. Scanner receipts retain
identifiers, hashes, derived findings and signed evidence, not raw scan intake.
Derived findings may repeat submitted identifiers. These boundaries do not promise
absence of inputs from host histories, operational logs, processors or backups.
The separate public receipt view is an unsigned filtered summary; public receipt
read tools are not attached to this plugin. Never submit secrets or sensitive
third-party records. Installation creates no paid entitlement; individual OAuth
consent alone does not authorize an assessment without its exact paid order.

## Active private-pilot OAuth flow

The approved private hosted pilot uses the existing Supabase identity provider.
The adapter receives provider identity/token responses and stores OAuth tokens and
transactions in private encrypted storage. Its separate metadata ledger stores
issuer/subject/caller/client bindings, grant-family issue/expiry times and revocation
state. The current pilot binds only the approved owner identity; additional customer
or reviewer bindings require separate approval. No identity credentials are accepted
as conversation or skill input. Gateway payment credentials and signer files remain
outside the adapter under the reviewed broker isolation boundary.

The approved OAuth policy caps grant families at 24 hours and runs cleanup hourly
with a one-hour post-expiry safety window. This is not a guaranteed session lifetime,
secure-erasure promise or backup-deletion promise. Commercial order, receipt,
derived evidence and replay retention are separate; no service-wide commercial
purge period is implemented. Host histories, processors, operational logs and
backups have their own handling, which must be confirmed for a public attestation.
Receipt expiry does not delete stored evidence. There is no self-service deletion
tool in this plugin; requests use the operator's privacy contact and public policy.

## Providers and release decisions

Existing service hosting uses DigitalOcean with Caddy transport; identity uses
Supabase; payment verification uses Stripe. Applicable published provider notices:

- https://www.digitalocean.com/legal/privacy-policy
- https://supabase.com/privacy (customer-data processing also has a DPA)
- https://stripe.com/privacy

Host platform notices include https://www.anthropic.com/legal/privacy and
https://openai.com/policies/privacy-policy/; the user's specific plan/terms also
apply. These links do not assert a particular provider retention or deletion rule.
No model/GPU workload is introduced by these documentation changes.

Before public policy attestation or broader release, the owner must confirm
record-class retention, deletion/backup procedures, relevant processor arrangements
and locations, intended audience, and the policy wording for the separate existing
payment flow. Do not infer those decisions from OAuth cleanup or software tests.
