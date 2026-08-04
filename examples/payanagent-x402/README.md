# PayanAgent x402 buyer examples

Two small, fail-closed examples for PayanAgent's escrow-backed example requests:

- `mcp-buy-example.mjs` calls `payanagent_discover` through the official
  `@payanagent/mcp` server, selects a live offer below a hard price ceiling,
  completes one purchase, and verifies the public receipt.
- `payan_x402_buy.py` performs the same x402 Exact / ERC-3009 Base-USDC flow
  from Python and prints the response body, `X-Receipt-Id`, and `X-Tx-Hash`.

Neither file contains a key. Use a dedicated Base wallet with only the USDC you
intend to spend. Both examples fail closed unless the advertised asset is
canonical Base USDC and the advertised amount is at or below your explicit
price ceiling.

## Node + MCP example

Requirements: Node.js 20 or newer and a funded Base wallet.

```bash
npm install
export PAYANAGENT_WALLET_PRIVATE_KEY=0xYOUR_DEDICATED_KEY
export PAYANAGENT_QUERY='weather'
export PAYANAGENT_OFFER_ID=kh7301wth5bhxt72g829batxtn89grvw
export PAYANAGENT_INPUT_JSON='{"location":"London"}'
export PAYANAGENT_MAX_USD=0.001
export PAYANAGENT_EXECUTE=I_ACCEPT_ONE_X402_PAYMENT
npm run mcp-buy
```

Optional controls:

- `PAYANAGENT_OFFER_ID`: require and buy this offer only if it appears in the
  live discovery result and remains under the price cap.
- `PAYANAGENT_EXCLUDE_SELLER_ID`: exclude a seller. It defaults to the Viridis
  Agent Fleet seller so the example cannot manufacture a self-purchase.

To exercise live MCP discovery and selection without loading a wallet or
signing anything:

```bash
export PAYANAGENT_DRY_RUN=1
export PAYANAGENT_QUERY='weather'
export PAYANAGENT_MAX_USD=0.01
npm run mcp-buy
```

The script launches the official `@payanagent/mcp@0.4.1` stdio server, calls
`payanagent_discover`, calls `payanagent_buy`, then requires non-empty receipt
and transaction identifiers and resolves the receipt through
`GET /api/v1/receipts/:id`.

## Python example

Requirements: Python 3.10 or newer.

```bash
python -m pip install 'x402[requests,evm]==2.18.0'
export PAYANAGENT_WALLET_PRIVATE_KEY=0xYOUR_DEDICATED_KEY
python payan_x402_buy.py kh7301wth5bhxt72g829batxtn89grvw \
  --input-json '{"location":"London"}' \
  --max-usd 0.001 \
  --execute
```

Before signing, the script makes the unpaid request once, decodes the
`PAYMENT-REQUIRED` challenge, and verifies all of these bindings:

- x402 version 2;
- `exact` scheme;
- Base mainnet (`eip155:8453`);
- canonical Base USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`);
- a valid recipient address; and
- an amount no greater than `--max-usd`.

It then uses the official x402 Python SDK to sign and retry the POST. A
successful HTTP response without both Payan receipt headers is treated as a
failure, and the receipt must resolve through the public API.

## Tests

The tests are offline and never load a wallet:

```bash
npm test
python -m unittest -v test_payan_x402_buy.py
```

## Evidence boundary

Source code and passing tests prove only artifact readiness. A real receipt
proves the example purchase. The request itself earns nothing until the buyer
accepts the bid, the provider fulfills the exact accepted request, the buyer
approves it, and PayanAgent releases escrow with a separately verifiable
receipt.

## Primary references

- PayanAgent source and buy flow:
  <https://github.com/derNif/payanagent/blob/master/README.md>
- PayanAgent MCP tool implementation:
  <https://github.com/derNif/payanagent/blob/master/packages/mcp/src/tools.ts>
- x402 Foundation Python client example:
  <https://github.com/x402-foundation/x402/blob/34cb6bd04c88f4333f56b9c778d3d35df997379c/examples/python/clients/requests/main.py>
