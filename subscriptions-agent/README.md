# Viridis Subscriptions

Revenue infrastructure for monthly human-buyer seats over the existing Viridis
per-call payment gate. The core attributes calls to bearer-authenticated
accounts, pull-verifies current Stripe lifecycle, resolves bundles from a
content-addressed catalog, and conserves included/overage usage exactly.

It never handles a Stripe secret or charges a card. Checkout and portal actions
only return validated Stripe-hosted links for a human to complete. An
unverified, ambiguous, canceled, expired, past-due, or persistence-failed
entitlement falls through to the existing per-call freemium path.

## Current catalog boundary

The baked default remains catalog `0.2.0`: five coverage-ready plans with
`stripe_price_id: null`, `approval_status: draft`, and checkout disabled. It
is the fail-closed fallback if the explicit catalog override is absent or
unreadable.

Production currently selects the owner-approved `0.3.0` override. Its five
active monthly Stripe Prices and 1,000-call quotas make all five plans
checkout-ready while the restricted Stripe link provider is attached.
Catalog `0.3.1` is a local truth-copy candidate that preserves every
commercial term and corrects stale explanatory text in `0.3.0`; it is not
live until separately promoted.

When any approval, coverage, Price, provider, or catalog gate is unset,
`create_checkout_link` returns the explicit `configuration_required` error
type. It does not create an account, Checkout Session, or money-moving side
effect.

## StateStore contract

Account hashes, subscriptions, verified billing-period snapshots, activation
keys, decisions, usage counters, and audit events are ordinary picklable core
attributes. The fleet `StateStore` restores and write-through persists them.
Provider objects, locks, key factories, and the short-lived rollback journal
live under `AgentConfig`, which StateStore excludes.

Payment-gate entitlement calls use this strict transaction:

```python
decision = subscriptions.reserve_entitlement(
    account_id, agent_id, request_id, per_call_price_minor
)
token = decision.get("reservation_token")
if token:
    if state_store.save("subscriptions", subscriptions):
        subscriptions.commit_reservation(token)
    else:
        subscriptions.rollback_reservation(token)
        # fall through to the ordinary per-call freemium path
```

The reserve holds the subscription transaction lock until commit/rollback, so
no concurrent quota mutation can overtake the durable snapshot. An overage
decision sets `bypass_anonymous_freemium: true` and
`requires_direct_overage_charge: true`; it must be charged at the exact current
per-call rate rather than receiving another anonymous free allowance.

Every potentially entitled call is pull-verified through the injected provider
before quota is waived. A new quota period is created only from a newly
verified Stripe `[current_period_start,current_period_end)` tuple. Local time
never guesses or rolls a paid period forward.

## Provider boundary

`AgentConfig.stripe_provider` is a restricted adapter, not a Stripe client in
this package. It supplies three methods:

- `create_subscription_checkout(...) -> {"url": "https://checkout.stripe.com/..."}`
- `verify_subscription(reference) -> normalized verified subscription dict`
- `create_customer_portal(...) -> {"url": "https://billing.stripe.com/..."}`

Verification must return `verified=true`, `mode=subscription`, exactly one
item of quantity one, monthly interval/count, currency/unit amount, unique
Price ID, catalog version/SHA, account binding, live/test mode, lifecycle, and
the exact period. The core checks every field before activation.

## MCP

```bash
python3 adapters/mcp_server.py
python3 adapters/mcp_server.py --serve
```

Catalog reads and aggregate MRR are open. Status, usage, and billing portal are
bearer-owned. A full account key is returned only once, on account creation or
first verified activation; later output is masked.

## Test

```bash
python3 -m unittest discover -s tests -v
```
