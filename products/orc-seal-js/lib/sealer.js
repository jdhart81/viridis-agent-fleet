// orc-seal sealer, JavaScript port of products/orc-seal/orc_seal/sealer.py.
//
// Attaches an Outcome Receipt (ORC v0.1) to every successful MCP tools/call
// result, under result._meta["com.viridisconservation/orc"].
//
// --- INVARIANTS (same letters as the Python package) ---
// M1  Result preservation: sealing only adds one key under `_meta`.
// M2  Every receipt produced here verifies at L1, here and in Python.
// M3  Privacy: tool arguments never appear in a receipt (only args_sha256);
//     the registry client sends only commitment, digest, salt, profile,
//     subject, issuer and issued_at.
// M4  Fail-open: a registry, network or sealing failure never fails the call;
//     issuer_proof is attached only after a 2xx reply that echoes the seal.
// M5  normalize() matches Python's: floats -> shortest repr strings,
//     NaN/Infinity -> "NaN"/"Infinity"/"-Infinity", bytes -> {bytes_sha256}.
//     normalize(normalize(x)) equals normalize(x).
// M6  Only successful results are sealed (no JSON-RPC errors, no isError).
// M7  Results whose canonical output exceeds MAX_OUTPUT_BYTES pass through
//     with _meta[...] = {"skipped": "too_large"}.

import { createHash } from "node:crypto";
import { JNum, canonical, get, isObject, pyFloatRepr } from "./json.js";
import * as orc from "./orc.js";

export const META_KEY = "com.viridisconservation/orc";
export const MAX_OUTPUT_BYTES = 262_144;
export const DEFAULT_REGISTRY = "https://mcp.viridisconservation.com";
export const VERSION = "0.1.0";

function normFloat(x) {
  if (Number.isNaN(x)) return "NaN";
  if (x === Infinity) return "Infinity";
  if (x === -Infinity) return "-Infinity";
  return pyFloatRepr(x);
}

/** M5. Accepts parsed trees (JNum, Map) and ordinary JS values. */
export function normalize(v) {
  if (v === null || v === undefined || typeof v === "boolean" || typeof v === "string" || typeof v === "bigint") {
    return v === undefined ? null : v;
  }
  if (v instanceof JNum) return v.isFloat ? normFloat(v.value()) : v;
  if (typeof v === "number") return Number.isInteger(v) && !Object.is(v, -0) ? v : normFloat(v);
  if (v instanceof Uint8Array) return new Map([["bytes_sha256", createHash("sha256").update(v).digest("hex")]]);
  if (Array.isArray(v)) return v.map(normalize);
  if (v instanceof Map) return new Map([...v].map(([k, x]) => [String(k), normalize(x)]));
  if (isObject(v)) return new Map(Object.entries(v).map(([k, x]) => [k, normalize(x)]));
  return String(v);
}

export function argsDigest(args) {
  return orc.sha256Hex(canonical(normalize(args ?? new Map())));
}

// Python truthiness for a parsed JSON value.
function truthy(v) {
  if (v === null || v === undefined || v === false || v === "") return false;
  if (v instanceof JNum) { const x = v.value(); return typeof x === "bigint" ? x !== 0n : x !== 0; } // NaN is truthy
  if (typeof v === "number") return v !== 0;
  if (Array.isArray(v)) return v.length > 0;
  if (v instanceof Map) return v.size > 0;
  if (isObject(v)) return Object.keys(v).length > 0;
  return true;
}

function pyStr(v) {
  if (v === undefined || v === null) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (v instanceof JNum) return v.lex;
  return String(v);
}

/** POST {base}/orc/v0/register. Sends no output and no arguments (M3). */
export class RegistryClient {
  constructor(baseUrl = DEFAULT_REGISTRY, apiKey = "", { timeoutMs = 3000, fetchImpl } = {}) {
    this.base = baseUrl.replace(/\/+$/, "");
    this.apiKey = apiKey;
    this.timeoutMs = timeoutMs;
    this.fetch = fetchImpl ?? globalThis.fetch;
    this.lastError = null;
  }

  static payload(r) {
    return {
      commitment: r.commitment.value, salt: r.commitment.salt, digest: r.digest.value,
      profile: r.profile, issuer: r.issuer,
      subject: { agent: String(r.subject.agent ?? ""), tool: String(r.subject.tool ?? "") },
      issued_at: r.issued_at,
    };
  }

  /** Resolve to issuer_proof on success, else null. Never rejects (M4). */
  async register(receipt) {
    this.lastError = null;
    // A ref'd timer (AbortSignal.timeout is unref'd) so a hung registry can
    // never outlive its timeout or let the process idle out mid-call.
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(new DOMException("registry timeout", "TimeoutError")), this.timeoutMs);
    try {
      const resp = await this.fetch(this.base + "/orc/v0/register", {
        method: "POST",
        headers: { "content-type": "application/json", authorization: "Bearer " + this.apiKey, "user-agent": "orc-seal-js/" + VERSION },
        body: JSON.stringify(RegistryClient.payload(receipt)),
        signal: ac.signal,
      });
      const text = await resp.text();
      if (!(resp.status >= 200 && resp.status < 300)) { this.lastError = `http ${resp.status}`; return null; }
      const data = JSON.parse(text || "{}");
      if (data?.commitment !== receipt.commitment.value || data?.digest !== receipt.digest.value) {
        this.lastError = "registry echo mismatch"; return null;
      }
      const proof = data.issuer_proof ?? {};
      if (proof.method !== "registry" || !String(proof.url ?? "").startsWith("http")) {
        this.lastError = "registry returned no proof url"; return null;
      }
      return { method: "registry", url: proof.url };
    } catch (exc) {
      this.lastError = exc?.name ?? "Error"; // network, timeout, JSON: fail open
      return null;
    } finally {
      clearTimeout(timer);
    }
  }
}

export class Sealer {
  constructor(issuer, { agent = "", registry = null, profile = "generic", verifyBase } = {}) {
    if (!issuer || typeof issuer !== "object" || !issuer.id) {
      throw new TypeError("issuer must be an object with an 'id' (e.g. did:web:example.com)");
    }
    this.issuer = { id: String(issuer.id), name: String(issuer.name ?? issuer.id) };
    this.agent = agent;
    this.registry = registry;
    this.profile = profile;
    this.verifyBase = (verifyBase ?? (registry ? registry.base : DEFAULT_REGISTRY)).replace(/\/+$/, "");
  }

  /** Resolve to a receipt, or null if the result is too large (M7). */
  async seal(tool, args, result, bindings) {
    const output = { tool: pyStr(tool), args_sha256: argsDigest(args), result: normalize(result) };
    if (canonical(output).length > MAX_OUTPUT_BYTES) return null;
    const receipt = orc.seal(output, {
      issuer: this.issuer, subject: { agent: this.agent, tool: pyStr(tool) },
      profile: this.profile, bindings: bindings ?? {},
    });
    receipt.verify = { page: `${this.verifyBase}/verify?c=${receipt.commitment.value}` };
    if (this.registry) {
      const proof = await this.registry.register(receipt);
      if (proof) receipt.issuer_proof = proof;
    }
    return receipt;
  }

  /**
   * JSON-RPC (MCP wire) mode. `request` and `response` are parsed trees.
   * Resolves to `response` itself when nothing is sealed (M1, M6), otherwise
   * to a copy whose result._meta carries the receipt.
   */
  async sealToolsCall(request, response) {
    try {
      if (get(request, "method") !== "tools/call" || get(response, "result") === undefined) return response;
      const result = get(response, "result");
      if (!(result instanceof Map) || truthy(result.get("isError"))) return response;
      const rawParams = get(request, "params");
      const params = truthy(rawParams) ? rawParams : new Map();
      if (!isObject(params)) return response;
      const rawMeta = result.get("_meta");
      if (truthy(rawMeta) && !(rawMeta instanceof Map)) return response; // Python: dict(non-mapping) raises
      const sealedPart = new Map([...result].filter(([k]) => k !== "_meta"));
      const name = get(params, "name") === undefined ? "" : get(params, "name");
      const receipt = await this.seal(name, get(params, "arguments"), sealedPart);
      const meta = new Map(truthy(rawMeta) ? rawMeta : []);
      meta.set(META_KEY, receipt ?? { skipped: "too_large" });
      const newResult = new Map(result);
      newResult.set("_meta", meta);
      const out = new Map(response);
      out.set("result", newResult);
      return out;
    } catch {
      return response; // M4
    }
  }
}

/**
 * L1 always; L2 when `registryRecord` (fetched from issuer_proof.url) echoes
 * this receipt's commitment and digest.
 */
export function verify(receipt, { registryRecord } = {}) {
  const proof = get(receipt, "issuer_proof");
  const hasProof = isObject(proof) && registryRecord !== undefined;
  const issuerOk = (r) => {
    if (get(proof, "method") !== "registry" || !isObject(registryRecord)) return false;
    return get(registryRecord, "commitment") === get(get(r, "commitment"), "value")
      && get(registryRecord, "digest") === get(get(r, "digest"), "value");
  };
  return orc.verify(receipt, { issuerResolver: hasProof ? issuerOk : undefined });
}
