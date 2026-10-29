// Helper for products/orc-seal/tests/test_js_parity.py.
// Reads one JSON job from stdin, answers with JSON on stdout.
//   {"op": "canonical", "texts": [...]}           -> [canonical(parse(t)) or null]
//   {"op": "repr", "hex": [...]}                   -> [pyFloatRepr(double from 16 hex digits)]
//   {"op": "seal", "pairs": [[req, resp], ...]}    -> [sealed response line or null]
//   {"op": "verify", "receipts": [text, ...]}      -> [{level, label}]
import { readFileSync } from "node:fs";
import { canonical, parse, pyFloatRepr, serialize } from "../lib/json.js";
import { Sealer, verify } from "../lib/sealer.js";

const job = JSON.parse(readFileSync(0, "utf8"));
const out = [];

if (job.op === "canonical") {
  for (const t of job.texts) {
    try { out.push(canonical(parse(t))); } catch { out.push(null); }
  }
} else if (job.op === "repr") {
  const view = new DataView(new ArrayBuffer(8));
  for (const h of job.hex) {
    view.setBigUint64(0, BigInt("0x" + h));
    out.push(pyFloatRepr(view.getFloat64(0)));
  }
} else if (job.op === "seal") {
  const s = new Sealer({ id: "did:web:example.com", name: "Example" }, { agent: "demo" });
  for (const [req, resp] of job.pairs) {
    const sealed = await s.sealToolsCall(parse(req), parse(resp));
    out.push(serialize(sealed));
  }
} else if (job.op === "verify") {
  for (const t of job.receipts) {
    const v = verify(parse(t));
    out.push({ level: v.level, label: v.label });
  }
} else {
  throw new Error("unknown op " + job.op);
}
process.stdout.write(JSON.stringify(out));
