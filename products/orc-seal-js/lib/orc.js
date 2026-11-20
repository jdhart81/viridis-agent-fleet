// Outcome Receipt (ORC) v0.1, JavaScript port of fleet_utils/orc.py.
// Spec: docs/standards/OUTCOME_RECEIPT_v0.1.md
//
// --- INVARIANTS (same letters as the Python reference) ---
// R1  canonical() is byte-identical to the Python reference (see json.js J1).
// R2  seal() never mutates its input; the same output and excludes always give
//     the same digest (the salt only changes the commitment).
// R3  verify() never throws; malformed input yields level 0 with reasons.
// R4  L1 requires BOTH digest recomputation and commitment recomputation.
// R5  Levels above L1 are granted only by an explicit resolver returning true.
// R6  Floats are rejected in `output` at seal time.
// X1  A receipt sealed by this module verifies under the Python reference and
//     vice versa (tested in products/orc-seal/tests/test_js_parity.py).

import { createHash, randomBytes } from "node:crypto";
import { JNum, canonical, get, isObject } from "./json.js";

export const ORC_VERSION = "0.1";
export const CANON_ID = "orc-canon/1";
export const COMMIT_SCHEME = "sha256(salt||digest)";
const LABELS = ["NONE", "INTACT", "ISSUED", "SETTLED", "VALIDATED"];

export function sha256Hex(s) {
  return createHash("sha256").update(s, "utf8").digest("hex");
}

function hasFloat(v) {
  if (typeof v === "number") return !Number.isInteger(v) || Object.is(v, -0);
  if (v instanceof JNum) return v.isFloat;
  if (Array.isArray(v)) return v.some(hasFloat);
  if (isObject(v)) return [...(v instanceof Map ? v.values() : Object.values(v))].some(hasFloat);
  return false;
}

const isHex64 = (s) => typeof s === "string" && /^[0-9a-f]{64}$/.test(s);

function withoutKeys(output, excludes) {
  const drop = new Set(excludes);
  if (output instanceof Map) return new Map([...output].filter(([k]) => !drop.has(k)));
  return Object.fromEntries(Object.entries(output).filter(([k]) => !drop.has(k)));
}

export function digestOf(output, excludes) {
  return sha256Hex(canonical(withoutKeys(output, excludes)));
}

// Python's datetime.now(timezone.utc).isoformat(): microseconds, +00:00.
export function utcNowIso(now = new Date()) {
  return now.toISOString().replace(/\.(\d{3})Z$/, ".$1000+00:00");
}

function clone(v) {
  if (Array.isArray(v)) return v.map(clone);
  if (v instanceof Map) return new Map([...v].map(([k, x]) => [k, clone(x)]));
  if (isObject(v)) return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, clone(x)]));
  return v; // primitives and JNum are immutable
}

/** Build an ORC receipt. Pure except for the random salt. */
export function seal(output, { issuer, subject, profile = "generic", excludes = [], bindings = {}, salt, issuedAt } = {}) {
  if (!isObject(output)) throw new TypeError("output must be a JSON object");
  if (hasFloat(output)) throw new RangeError("floats are not allowed in output; use integers or decimal strings"); // R6
  const out = clone(output); // R2
  const ex = [...excludes];
  const d = digestOf(out, ex);
  const s = salt ?? randomBytes(32).toString("hex");
  return {
    orc: ORC_VERSION, profile,
    issuer: clone(issuer), subject: clone(subject),
    output: out,
    digest: { alg: "sha256", canonicalization: CANON_ID, excludes: ex, value: d },
    commitment: { scheme: COMMIT_SCHEME, salt: s, value: sha256Hex(s + d) },
    bindings: clone(bindings),
    issued_at: issuedAt ?? utcNowIso(),
  };
}

// Python's str() of a JSON scalar, used where the reference does str(x).
function pyStr(v) {
  if (v === undefined || v === null) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (v instanceof JNum) return v.lex;
  return String(v);
}

/** Return {level, label, checks, reasons}. Never throws (R3). */
export function verify(receipt, { issuerResolver, paymentResolver, validationResolver } = {}) {
  const reasons = [];
  const checks = { digest_recomputes: false, commitment_binds: false, issuer_proven: null, payment_settled: null, validated: null };
  const done = (level) => ({ level, label: LABELS[level], checks, reasons });
  try {
    if (!isObject(receipt) || get(receipt, "orc") !== ORC_VERSION) {
      reasons.push("not an ORC v0.1 receipt"); return done(0);
    }
    // Python: receipt.get("digest", {}) -> a missing key acts as {}, a null one raises.
    const dg = get(receipt, "digest") === undefined ? new Map() : get(receipt, "digest");
    const cm = get(receipt, "commitment") === undefined ? new Map() : get(receipt, "commitment");
    const out = get(receipt, "output");
    if (!isObject(dg)) throw new TypeError("digest must be an object");
    if (get(dg, "canonicalization") !== CANON_ID || get(dg, "alg") !== "sha256") {
      reasons.push("unsupported digest algorithm or canonicalization"); return done(0);
    }
    if (!isObject(cm)) throw new TypeError("commitment must be an object");
    if (get(cm, "scheme") !== COMMIT_SCHEME || !isHex64(get(cm, "salt"))) {
      reasons.push("unsupported commitment scheme or bad salt"); return done(0);
    }
    if (!isObject(out)) { reasons.push("output must be an object"); return done(0); }
    const excl = get(dg, "excludes") === undefined ? [] : get(dg, "excludes");
    if (!Array.isArray(excl) || !excl.every((x) => typeof x === "string")) {
      reasons.push("digest.excludes must be a list of strings"); return done(0);
    }
    checks.digest_recomputes = digestOf(out, excl) === get(dg, "value");
    checks.commitment_binds = sha256Hex(get(cm, "salt") + pyStr(get(dg, "value"))) === get(cm, "value");
    if (!(checks.digest_recomputes && checks.commitment_binds)) { // R4
      if (!checks.digest_recomputes) reasons.push("output was altered: digest does not recompute");
      if (!checks.commitment_binds) reasons.push("commitment does not bind the digest");
      return done(0);
    }
    let level = 1;
    for (const [key, res, need] of [
      ["issuer_proven", issuerResolver, "issuer"],
      ["payment_settled", paymentResolver, "payment"],
      ["validated", validationResolver, "validation"],
    ]) { // R5
      if (!res) { reasons.push(`no ${need} resolver supplied; level capped at ${level}`); return done(level); }
      const ok = Boolean(res(receipt));
      checks[key] = ok;
      if (!ok) { reasons.push(`${need} check failed; level capped at ${level}`); return done(level); }
      level += 1;
    }
    return done(level);
  } catch (exc) { // R3
    reasons.push(`malformed receipt: ${exc?.constructor?.name ?? "Error"}`);
    return done(0);
  }
}
