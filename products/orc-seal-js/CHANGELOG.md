# Changelog

All notable changes to the Node `orc-seal` package. Versions follow [semver](https://semver.org); the receipt format follows the ORC spec version, which is separate.

## 0.1.0 (unreleased)

First npm release. The Node port of the Python `orc-seal` 0.1.0.

- `npx -y orc-seal --issuer <did> -- <server command>` wraps any stdio MCP server and seals each successful `tools/call` result with an ORC v0.1 receipt.
- `orc-seal verify <receipt.json>` and `orc-seal badge` from the same binary.
- Library: `Sealer`, `verify`, `parse` and the canonical encoder, with lossless JSON numbers.
- L2 ISSUED receipts when `ORC_SEAL_API_KEY` is set; registry failures fail open after 3 s.
- Byte-identical canonical form and digests with the Python package, checked on every push.
- No runtime dependencies. Node 18.17 or newer.
