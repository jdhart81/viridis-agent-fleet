# Genesis Receipts — the fleet's first self-transaction
> Executed 2026-07-11T14:54:28.985042+00:00 against `http://127.0.0.1:8402` over MCP streamable-http. Run `20260711T145426Z`. 11/11 invariants passed. Raw receipts: [GENESIS_RECEIPTS.json](GENESIS_RECEIPTS.json)

One measurement job, bought by one Viridis agent from another, settled entirely on the fleet's own rails:

- **Born** — genesis certificates for `viridis:smartscale` and `viridis:protogen` (provenance, content-addressed, verified)
- **Identified** — DIDs `did:viridis:51b4eb8815b9c385` / `did:viridis:60fcb56fa3c21546`
- **Authorized** — covenant `cov-000001`: out-of-scope act denied, purchase of 500 minor units allowed
- **Metered** — meter `mtr-000001`, 1 job, invoice 500 minor
- **Paid** — escrow `esc_000002` FUNDED -> RELEASED exactly once; delivery proof `sha256:d8fa9300c892f7c2d...`; audit chain valid
- **Carbon-accounted** — 0.200 gCO2e recorded (30 W x 60 s @ 400 g/kWh)
- **Offset** — retired against verified credit `dscore:zenodo.19317982/site7` -> net position <= 0
- **Trusted** — outcome recorded; seller score 0.6667

*No other fleet can publish this receipt. The rails it ran on are live at the same endpoint, free to call.*