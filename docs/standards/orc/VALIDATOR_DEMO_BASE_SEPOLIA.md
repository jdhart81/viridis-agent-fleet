# ORC validator demo on Base Sepolia (testnet only)

This is the first public ERC-8004 validator run against Outcome Receipts. **Use testnet only.** Do not go to mainnet until there is outside demand (BEDROCK.md §4).

## What it proves
A requester asks: "did this agent really deliver this result?" A validator that holds no trust in the original agent **replays the computation** and answers on-chain with 100 (reproduced) or 0 (not reproduced), pointing to the receipt as evidence.

## Steps
1. **Receipt:** run `python3 products/signed-cliff-check/build_report.py products/signed-cliff-check/sample_solar_48e.json --out out/` and publish `out/*.orc.json` at an https URL (for example, a GitHub raw URL). That URL becomes `responseURI`.
2. **Request:** from a *requester* test wallet, call `validationRequest(validatorAddress, agentId, requestURI, requestHash)` on the Base Sepolia ValidationRegistry. `requestHash` = SHA-256 of the `requestURI` document. Note it down.
3. **Replay (dry run, no keys):**
   ```bash
   python3 products/orc-validator/validator.py out/<stem>.orc.json \
     --facts products/signed-cliff-check/sample_solar_48e.json \
     --request-hash 0x<requestHash> --response-uri https://…/<stem>.orc.json
   ```
   This prints `args = {requestHash, response: 100, responseURI, responseHash, tag: "orc/0.1"}`, unsigned.
4. **Respond:** from the *validator* test wallet (Justin's signer, never an agent's), send `validationResponse(args…)`.
5. **Record** the two transaction hashes in `CEO_CHARTER.md §8`. They are the demo link for the standards posts.

## Contract addresses
Take them from https://github.com/erc-8004/erc-8004-contracts (the testnet deployments list). As of 2026-09 the Validation Registry spec is still being revised, so confirm the ABI there before sending anything.

## Guardrails
- The validator code never holds keys (V3). The ERC-8004 bridge refuses any input that contains key material (B5).
- An unknown profile, or missing facts, always gets 0. A validator never vouches for work it cannot reproduce (V1, V4).
