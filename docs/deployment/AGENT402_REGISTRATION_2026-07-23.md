# Agent402 Registration Receipt — 2026-07-23

Viridis Regulatory Radar is registered and publicly visible on the Agent402
marketplace.

## Live identity

- Status: `active`
- Agent ID: `6c4edb82-5358-4383-8fb8-4dce012d9445`
- ERC-8004 token: `#59701`
- Registration transaction:
  `0x58fd0061cee961b725f449003382d867fa9ddbcb8a64a948b5fccbc76f754a0b`
- Identity and settlement network: Base mainnet (`eip155:8453`)
- Verified operator and settlement wallet:
  `0xfEf2e570b645EB720Ee6c589d27450810982f329`
- Facilitator: Coinbase CDP
- Marketplace listing:
  <https://marketplace.agent402.app/marketplace?agent=6c4edb82-5358-4383-8fb8-4dce012d9445>

## Live service

- Service: Regulatory Applicability Scan
- Price: `$0.25 USDC` per exact call
- Endpoint:
  <https://mcp.viridisconservation.com/x402/regulatory-radar/scan_regulations_agent402>
- Registration-time validator: `13 / 14` checks passed
- The previously missing optional `resource.iconUrl` is now live at:
  <https://mcp.viridisconservation.com/brand/viridis-mark.svg>

The endpoint returned the required x402 payment challenge during registration.
The marketplace displayed the service publicly with token `#59701`, Base,
Coinbase CDP, and the `$0.25` price after the on-chain registration confirmed.

## Icon deployment

- Full Mac fleet gate: `1,343 passed`, `0 failed`, `33 / 33` suites clean.
- Isolated candidate: health `ok`, SVG HTTP `200`, unpaid challenge HTTP `402`.
- Live candidate image:
  `sha256:7367ee25748eac6e1b3ec71bac297321e64964be691011704d3ecdd5136ad809`
- Rollback image:
  `sha256:bad2d608525980fa455efef41f4d50620f65944335afedc4f63841b5603472b4`
- Rollback tag: `viridis-stable:prev-2026-07-23-agent402-icon`
- Post-cutover health: `ok`; persistence available.
- Agent402 alias remained `250000` atomic USDC and the public intro route
  remained `10000` atomic USDC.

Agent402's service-to-ERC-8004 metadata sync remains pending. Its metadata
rebuild did not reach a wallet request after more than one minute, so the
attempt was canceled without signing another transaction.

No paid self-request was made. This preserves the publisher-terms boundary
against artificial payment or activity inflation.
