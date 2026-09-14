# Buy a bounded efficiency or security planning result

The existing buyer client now supports Wu Wei and Maxwell. Each plan costs $1 USDC; a quote does not execute the service or move money. Examples below are synthetic illustrations, not customer evidence. Replace their values with your workload and evaluation data before purchase.

## Inspect without payment

```sh
python3 scripts/x402_demo_client.py --route wu-wei-router --input-file examples/efficiency/wu-wei-input.json --dry-run
python3 scripts/x402_demo_client.py --route maxwell-defense --input-file examples/efficiency/maxwell-input.json --dry-run
```

Maxwell defaults to mcp.viridis-security.com; Wu Wei uses the fleet at mcp.viridisconservation.com. Both require an input file. No wallet is needed for these quote-only commands.

## Buyer-authorized purchase

Use your existing buyer wallet setup described in scripts/x402_demo_client.py. Keep its credentials on buyer infrastructure. Remove --dry-run and supply --max-payment-usdc 1.00 only when you authorize that purchase. The client refuses a quote above the ceiling before paying; the SDK also enforces the bound on its payment path. Network fees, if applicable, are separate from the service quote.

The returned result contains the fleet delivery contract. Retain the payment receipt and result digest, validate the result, and use its feedback contract to report whether it helped. Feedback does not authorize a second purchase. Never publish the feedback token.

Wu Wei provides modeled routing recommendations, not independently verified savings or execution. Maxwell provides a policy rehearsal, not activated protection or measured energy savings. A $1 plan may find no savings; its fee still applies. Evaluate net benefit before repeating a purchase.
