#!/usr/bin/env node
// orc-seal CLI (same flags as the Python package).
//
//   orc-seal --issuer did:web:example.com [--name "Example"] [--agent my-server]
//            [--registry https://mcp.viridisconservation.com] -- <server command...>
//   orc-seal verify receipt.json
//   orc-seal badge
//
// Registration (L2 ISSUED) is enabled when ORC_SEAL_API_KEY is set. Without a
// key, receipts are self-sealed (L1 INTACT) and nothing leaves the machine.

import { main } from "../lib/cli.js";

main(process.argv.slice(2)).then((code) => {
  // Exit only after everything already written to stdout has been flushed (P4).
  process.stdout.write("", () => process.exit(code));
});
