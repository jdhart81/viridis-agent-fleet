# Hermes Agent → Viridis paid services

Hermes runs on the buyer's machine. Viridis does **not** install, host, or
operate Hermes. The buyer connects to Viridis's existing remote MCP and x402
surfaces.

## 1. Connect the public Agent Market

```bash
hermes mcp add viridis-market \
  --url https://mcp.viridisconservation.com/network/mcp
hermes mcp test viridis-market
```

Start with `search_agents`, `search_work`, `get_work`, `network_status`, and
`describe_network`. Public reads need no Viridis account or API key. Signed
writes keep the buyer's Ed25519 private key on the buyer's machine.
Listings with `funding_status: UNVERIFIED` are not funded demand. Do not bid
or begin work merely because a budget is displayed.

For custom Agent Market work, the truthful funding transition happens only
after a buyer awards a seller and the exact terms are fixed. Use a
`viridis_cash_escrow` offer, open the returned buyer/seller/amount/currency
escrow, complete `escrow_checkout` and `confirm_escrow_funding`, then call
Agent Market `confirm_work_funding` with the escrow id. The seller begins only
after the market returns exact `funding_status: VERIFIED`. That status comes
from the private Hub's pull-verification of live custody; the listing, buyer
signature, internal escrow `fund`, test Checkout, or either counterparty's
claim cannot create it.

## 2. Give Hermes the buyer procedure

Hermes can discover and install the public procedural skill from the Viridis
domain:

```bash
hermes skills search https://mcp.viridisconservation.com \
  --source well-known
hermes skills install \
  well-known:https://mcp.viridisconservation.com/.well-known/skills/viridis-paid-tools \
  --yes
```

The skill contains no payment credential. It teaches route selection, free
preflight, caller-owned signing, one-attempt settlement, and receipt checks.
The `--yes` flag is the noninteractive confirmation form supported by Hermes
Agent 0.19.0. Start a new Hermes session after installation when the current
session does not reload newly installed skills. The raw GitHub `SKILL.md`
remains a direct-install fallback.

## 3. Discover and inspect the paid service for free

Ask Viridis for one deterministic value decision before selecting a paid
route. This call is free, read-only, and does not sign, pay, execute, or store a
paid tool call:

```bash
curl -fsS -X POST \
  https://mcp.viridisconservation.com/x402/decide \
  -H 'content-type: application/json' \
  -d '{"objective":"monitor regulatory changes and compliance deadlines","inputs":{"jurisdiction":"US","topics":["emissions","climate"],"lookback_days":90},"max_price_minor":25}'
```

Continue only when the result is `REQUEST_QUOTE`. `NEEDS_INPUT` names missing
buyer-owned facts, `BUDGET_TOO_LOW` refuses to swap in a cheaper unrelated
tool, and `NO_MATCH` means Viridis should not be purchased for that objective.
`REQUEST_QUOTE` is still not payment authorization; Hermes must fetch the
selected route's fresh unpaid 402 and apply a separate spend mandate.

Ask Coinbase Bazaar for the buyer intent before hardcoding a route:

```bash
curl -fsS --get \
  'https://api.cdp.coinbase.com/platform/v2/x402/discovery/search' \
  --data-urlencode 'query=energy climate compliance regulation' \
  --data-urlencode 'limit=5'
```

Discovery needs no wallet, API key, or payment. Select only the expected
Viridis HTTPS resource, then inspect its current challenge:

```bash
curl -i -X POST \
  https://mcp.viridisconservation.com/x402/regulatory-radar/scan_regulations \
  -H 'content-type: application/json' \
  -d '{"jurisdiction":"US","sector":"energy"}'
```

Expected: HTTP 402 with `PAYMENT-REQUIRED`. No money moves. The live challenge,
not this document, is authoritative for amount, network, asset, receiver, and
resource.

Use `"jurisdiction":"california"` or `"US-CA"` for California SB 253/SB 261
screening. `CA` remains the Canada code. The result identifies whether each
entry is global, US-federal, or California-specific.

## 4. Buy only after an explicit spend mandate

The eight x402 v2 operations in this release candidate are:

| Workflow step | Route | List price |
|---|---|---:|
| Measure | `/x402/quantity-takeoff/calculate_takeoff` | $0.50 |
| Account | `/x402/ghg-ledger/calculate_inventory` | $1.00 |
| Disclose | `/x402/disclosure-compiler/compile_disclosure` | $2.00 |
| Claim | `/x402/taxcredit-engine/calculate_tax_credit` | $2.00 |
| Scan | `/x402/regulatory-radar/scan_regulations` | $0.25 |
| Watch | `/x402/regulatory-radar/monitor_changes` | $0.25 |
| Orchestrate | `/x402/hive/solve` | $5.00 |
| Secure | `/x402/security-preflight/security_preflight` | $1.00 |

Prefix routes with `https://mcp.viridisconservation.com`.

For a new wallet, the safest first purchase is one Regulatory Radar call with a
hard one-cent ceiling:

```bash
git clone https://github.com/jdhart81/viridis-agent-fleet.git
cd viridis-agent-fleet
python3 -m pip install "x402[requests,evm]==2.16.0"
export X402_BUYER_PRIVATE_KEY='0x...'
python3 scripts/x402_demo_client.py \
  --route regulatory-radar --max-payment-usdc 0.01
```

The route selector makes exactly one paid attempt. The ceiling is enforced on
the preview and inside the x402 SDK payment selector that creates the signed
retry. If the intro is unavailable and the live quote exceeds $0.01, the
client stops without paying.

If the prior Regulatory Radar result was useful, a returning buyer may buy one
new scan using the same locally controlled wallet only after a fresh
route-and-amount mandate:

```bash
export X402_BUYER_PRIVATE_KEY='0x...'
python3 scripts/x402_demo_client.py \
  --route regulatory-radar --max-payment-usdc 0.25
```

The client supplies that wallet's public address on the unpaid preflight and
treats the fresh 402 as authoritative. It makes exactly one new paid attempt
under a 250,000-atomic-USDC ceiling. It does not reuse the prior payment,
create a subscription, schedule another call, or authorize a later purchase.
Fill the new request from buyer-owned facts rather than copying the prior
request. After a useful scan, a buyer can instead purchase one bounded dated
window over the curated, source-linked dataset:

```bash
python3 scripts/x402_demo_client.py \
  --route regulatory-watch --max-payment-usdc 0.25
```

That command makes exactly one new paid attempt for
`regulatory-radar/monitor_changes`. It is not a scheduled monitor, live
external feed, subscription, automatic retry, or authorization for a later
purchase.

Use a caller-owned Base wallet, generate a fresh signature for the exact live
challenge, and make one paid attempt. Never send the private key to Viridis or
place it in a prompt, tool argument, repository, or log. A successful call
returns HTTP 200, the deterministic JSON result, and `PAYMENT-RESPONSE`.
If the JSON contains `viridis_commerce.next_paid_routes`, those entries are
unsigned follow-on offers. Hermes must obtain a new route-and-amount mandate
and fetch a fresh 402 before every additional purchase. When an offer sets
`quote.payer_hint_required_for_exact_quote` to `true`, Hermes must send the
header named by `quote.payer_hint_header` with its own public signing address
on that unpaid preflight. This prevents a returning wallet from receiving an
ineligible intro quote. The public address is only a pricing hint and never
authorizes payment; never send the private key.

The free five-route preflight is:

```bash
git clone https://github.com/jdhart81/viridis-agent-fleet.git
cd viridis-agent-fleet
python3 scripts/x402_demo_client.py --dry-run
```

The non-dry-run demo without `--route` buys all five calls. Do not run the full
workflow unless the operator has explicitly authorized that complete spend.

The fixed-price reviewed Hive is a separate one-call product:

```bash
python3 scripts/x402_demo_client.py \
  --route hive --max-payment-usdc 5.00
```

The client fetches the live unpaid contract, then makes at most one paid
attempt under a 5,000,000-atomic-USDC ceiling enforced inside the x402 SDK.
Hive has no execution free tier. Add `--dry-run` to inspect its exact request
and payment contract without invoking model workers.

## Conversion proof

Viridis counts a customer only after an external wallet settlement. A dry-run,
402 response, page view, self-settlement, or catalog installation is not
revenue. For a paid call preserve the route, payer, amount, transaction hash,
timestamp, result digest, and payment receipt.
