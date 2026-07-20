# Viridis x402 free dry-run — captured output

Captured against production on 2026-07-20 with:

```bash
python3 scripts/x402_demo_client.py --dry-run
```

No wallet key was loaded and no payment was signed or settled. Production
returned HTTP 402 for all five steps:

```text
[measure]  quantity-takeoff/calculate_takeoff      10000 atomic USDC ($0.01)
[account]  ghg-ledger/calculate_inventory          10000 atomic USDC ($0.01)
[disclose] disclosure-compiler/compile_disclosure  10000 atomic USDC ($0.01)
[claim]    taxcredit-engine/calculate_tax_credit   10000 atomic USDC ($0.01)
[scan]     regulatory-radar/scan_regulations       10000 atomic USDC ($0.01)

network: eip155:8453
asset:   0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
payTo:   0xfEf2e570b645EB720Ee6c589d27450810982f329
workflow: measure -> account -> disclose -> claim -> scan
dry_run: true
list_total_usdc: 5.75
same_wallet_expected_total_usdc: 5.26
```

The five independent unpaid preflights each advertise the new-wallet intro
because a dry run never consumes it. A real wallet receives the $0.01 intro on
its first successful settlement only; the remaining four calls use list price,
for a $5.26 same-wallet workflow total in this order.
