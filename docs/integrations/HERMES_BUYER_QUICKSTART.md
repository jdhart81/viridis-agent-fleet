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

## 2. Give Hermes the buyer procedure

Hermes can install the public procedural skill directly:

```bash
hermes skills install \
  https://raw.githubusercontent.com/jdhart81/viridis-agent-fleet/main/integrations/viridis-paid-tools/SKILL.md \
  --name viridis-paid-tools
```

The skill contains no payment credential. It teaches route selection, free
preflight, caller-owned signing, one-attempt settlement, and receipt checks.

## 3. Inspect the paid service for free

```bash
curl -i -X POST \
  https://mcp.viridisconservation.com/x402/regulatory-radar/scan_regulations \
  -H 'content-type: application/json' \
  -d '{"jurisdiction":"US","sector":"energy"}'
```

Expected: HTTP 402 with `PAYMENT-REQUIRED`. No money moves. The live challenge,
not this document, is authoritative for amount, network, asset, receiver, and
resource.

## 4. Buy only after an explicit spend mandate

The five live x402 v2 routes are:

| Workflow step | Route | List price |
|---|---|---:|
| Measure | `/x402/quantity-takeoff/calculate_takeoff` | $0.50 |
| Account | `/x402/ghg-ledger/calculate_inventory` | $1.00 |
| Disclose | `/x402/disclosure-compiler/compile_disclosure` | $2.00 |
| Claim | `/x402/taxcredit-engine/calculate_tax_credit` | $2.00 |
| Scan | `/x402/regulatory-radar/scan_regulations` | $0.25 |

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

Use a caller-owned Base wallet, generate a fresh signature for the exact live
challenge, and make one paid attempt. Never send the private key to Viridis or
place it in a prompt, tool argument, repository, or log. A successful call
returns HTTP 200, the deterministic JSON result, and `PAYMENT-RESPONSE`.

The free five-route preflight is:

```bash
git clone https://github.com/jdhart81/viridis-agent-fleet.git
cd viridis-agent-fleet
python3 scripts/x402_demo_client.py --dry-run
```

The non-dry-run demo without `--route` buys all five calls. Do not run the full
workflow unless the operator has explicitly authorized that complete spend.

## Conversion proof

Viridis counts a customer only after an external wallet settlement. A dry-run,
402 response, page view, self-settlement, or catalog installation is not
revenue. For a paid call preserve the route, payer, amount, transaction hash,
timestamp, result digest, and payment receipt.
