# Viridis B2B Subscriptions — public contract

Endpoint: `https://mcp.viridisconservation.com/subscriptions/mcp`

Version: `0.1.0`

This infrastructure surface attributes calls to human-buyer accounts and
resolves versioned monthly-seat entitlements before the existing per-call
freemium gate. Anonymous callers remain on the per-call path.

## Public tools

`list_plans`, `get_plan`, `create_account`, `create_checkout_link`,
`record_subscription`, `subscription_status`, `customer_portal_link`,
`usage_summary`, `mrr_summary`, and `describe_agent`.

## Contract invariants

- Account and subscription state is durable; raw account keys are never stored.
- Entitlement lookup fails safe to the existing paid per-call path.
- One entitled call takes exactly one path: included quota or exact overage.
- Only an active, live-mode subscription inside its verified period entitles.
- Activation is idempotent for each Stripe subscription and billing period.
- Checkout and portal actions return Stripe-hosted links; they never charge a
  card, handle a Stripe secret, or move money autonomously.
- Included use, overage, and monthly rollover conserve exactly and are auditable.
- Every decision cites the version and SHA-256 of the bundled plan catalog.

Bearer credentials are supplied only through `Authorization: Bearer`; they are
not MCP tool arguments. Status and usage responses mask the credential. The
public Glama bridge does not embed a shared account key.

## Launch state

The five starting plans and 1,000-call quota are published as draft defaults.
Subscription Checkout remains disabled until Viridis approves final monthly
prices and quota and supplies recurring Stripe Price IDs. This fail-closed state
does not affect anonymous per-call callers or the fleet's free rails.
