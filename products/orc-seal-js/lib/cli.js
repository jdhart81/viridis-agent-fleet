import { readFileSync } from "node:fs";
import { get, isObject, parse } from "./json.js";
import { run } from "./proxy.js";
import { DEFAULT_REGISTRY, RegistryClient, Sealer, VERSION, verify } from "./sealer.js";

const SPEC = "https://github.com/jdhart81/viridis-agent-fleet/blob/main/docs/standards/OUTCOME_RECEIPT_v0.1.md";

const USAGE = `usage: orc-seal --issuer ISSUER [--name NAME] [--agent AGENT] [--registry URL] -- <server command...>
       orc-seal verify receipt.json
       orc-seal badge

Put orc-seal in front of any stdio MCP server. Every successful tools/call
result gets an Outcome Receipt (ORC v0.1) under result._meta.

options:
  --issuer ISSUER   issuer id, e.g. did:web:example.com (required)
  --name NAME       issuer display name (default: the issuer id)
  --agent AGENT     agent name in each receipt (default: the server command)
  --registry URL    registry base URL (default: $ORC_SEAL_REGISTRY or ${DEFAULT_REGISTRY})
  -h, --help        show this help
  --version         print the version

Set ORC_SEAL_API_KEY to register each seal (L2 ISSUED). Without it nothing
leaves your machine.
`;

const BADGE = `[![ORC sealed](https://img.shields.io/badge/ORC-sealed-2e7d32)](${SPEC})`;

/** Parse proxy options the way Python's argparse does for this CLI. */
export function parseOptions(opts) {
  const out = { name: "", agent: "", registry: process.env.ORC_SEAL_REGISTRY || DEFAULT_REGISTRY };
  const flags = { "--issuer": "issuer", "--name": "name", "--agent": "agent", "--registry": "registry" };
  for (let k = 0; k < opts.length; k++) {
    const a = opts[k];
    const eq = a.indexOf("=");
    const flag = eq > 0 ? a.slice(0, eq) : a;
    if (!(flag in flags)) throw new UsageError(`unrecognized argument: ${a}`);
    let value;
    if (eq > 0) value = a.slice(eq + 1);
    else {
      value = opts[++k];
      if (value === undefined) throw new UsageError(`argument ${flag}: expected one argument`);
    }
    out[flags[flag]] = value;
  }
  if (!out.issuer) throw new UsageError("the following arguments are required: --issuer");
  return out;
}

class UsageError extends Error {}

async function fetchRecord(url) {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
    return parse(await r.text());
  } catch {
    return null;
  }
}

async function verifyFile(path) {
  let receipt;
  try {
    receipt = parse(readFileSync(path, "utf8"));
  } catch (exc) {
    process.stderr.write(`orc-seal: cannot read ${path}: ${exc.message}\n`);
    return 2;
  }
  const proof = isObject(receipt) ? get(receipt, "issuer_proof") : undefined;
  const url = isObject(proof) ? get(proof, "url") : undefined;
  const record = typeof url === "string" && url.startsWith("http") ? await fetchRecord(url) : undefined;
  const out = verify(receipt, { registryRecord: record });
  process.stdout.write(JSON.stringify({ level: out.level, label: out.label, reasons: out.reasons }, null, 2) + "\n");
  return out.level >= 1 ? 0 : 1;
}

export async function main(argv) {
  try {
    if (argv[0] === "verify") {
      if (argv.length !== 2) { process.stderr.write("usage: orc-seal verify receipt.json\n"); return 2; }
      return await verifyFile(argv[1]);
    }
    if (argv[0] === "badge") { process.stdout.write(BADGE + "\n"); return 0; }
    const sep = argv.indexOf("--");
    const opts = sep === -1 ? argv : argv.slice(0, sep);
    if (opts.includes("-h") || opts.includes("--help")) { process.stdout.write(USAGE); return 0; }
    if (opts.includes("--version")) { process.stdout.write(VERSION + "\n"); return 0; }
    const a = parseOptions(opts);
    const cmd = sep === -1 ? [] : argv.slice(sep + 1);
    if (!cmd.length) throw new UsageError("missing server command after --");
    const key = process.env.ORC_SEAL_API_KEY || "";
    const registry = key ? new RegistryClient(a.registry, key) : null;
    const sealer = new Sealer({ id: a.issuer, name: a.name || a.issuer }, { agent: a.agent || cmd[0], registry, verifyBase: a.registry });
    return await run(cmd, sealer);
  } catch (exc) {
    if (exc instanceof UsageError) {
      process.stderr.write(USAGE.split("\n\n")[0] + `\norc-seal: error: ${exc.message}\n`);
      return 2;
    }
    throw exc;
  }
}
