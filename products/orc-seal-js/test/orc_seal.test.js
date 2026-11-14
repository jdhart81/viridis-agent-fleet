// Invariant tests for the JS port. Letters match the Python suite:
// J* lossless JSON, R* receipt core, M* sealer, P* proxy.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { JNum, canonical, parse, pyFloatRepr, serialize } from "../lib/json.js";
import { seal, verify as verifyReceipt } from "../lib/orc.js";
import { Tracker, transformServerLine } from "../lib/proxy.js";
import { META_KEY, RegistryClient, Sealer, normalize, verify } from "../lib/sealer.js";
import { parseOptions } from "../lib/cli.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PKG = dirname(HERE);
const ROOT = join(PKG, "..", "..");
const BIN = join(PKG, "bin", "orc-seal.js");
const ISSUER = { id: "did:web:example.com", name: "Example" };

const REQ = '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"double","arguments":{"x":21,"secret":"hunter2"}}}';
const RESP = '{"jsonrpc":"2.0","id":7,"result":{"content":[{"type":"text","text":"42"}],"structuredContent":{"value":42,"ratio":0.1},"_meta":{"other":1}}}';

// ---- J: lossless JSON -------------------------------------------------------
test("J1 canonical sorts by code point and escapes like Python ensure_ascii", () => {
  const t = '{"b":1,"a":[true,null,"é☀😀\\u007f\\n\\"/"],"\\uffff":0,"😀":0,"2":0,"10":0}';
  assert.equal(canonical(parse(t)),
    '{"10":0,"2":0,"a":[true,null,"\\u00e9\\u2600\\ud83d\\ude00\\u007f\\n\\"/"],"b":1,"\\uffff":0,"\\ud83d\\ude00":0}');
});

test("J1 numbers: floats in Python repr, ints exact beyond 2^53", () => {
  assert.equal(canonical(parse("[1.0,0.10,1e2,1E-5,-0.0,12345678901234567890123,1e400,-1e400,NaN]")),
    "[1.0,0.1,100.0,1e-05,-0.0,12345678901234567890123,Infinity,-Infinity,NaN]");
});

test("J2 pyFloatRepr matches known Python reprs", () => {
  const cases = [[0.1, "0.1"], [1e16, "1e+16"], [1e15, "1000000000000000.0"], [0.0001, "0.0001"],
    [0.00001, "1e-05"], [1.5e-7, "1.5e-07"], [123.456, "123.456"], [-2.5, "-2.5"], [5e-324, "5e-324"],
    [1.7976931348623157e308, "1.7976931348623157e+308"], [2 ** 53, "9007199254740992.0"], [100, "100.0"]];
  for (const [x, want] of cases) assert.equal(pyFloatRepr(x), want, String(x));
});

test("J3 parse rejects what Python rejects", () => {
  for (const bad of ['{"a":1', '"\u0001"', "[1,]", "01", "1.", '{"a" 1}', "tru", "1 2", "9".repeat(4301)]) {
    assert.throws(() => parse(bad), undefined, bad);
  }
  assert.equal(canonical(parse("9".repeat(4300))), "9".repeat(4300));
});

test("J3 duplicate keys: last value wins in the first position", () => {
  const v = parse('{"a":1,"b":2,"a":3}');
  assert.equal(serialize(v), '{"a":3,"b":2}');
});

test("J4 serialize keeps spelling and key order", () => {
  const t = '{"z":1.50,"2":1e2,"a":[0.10,-0,"Café"]}';
  assert.equal(serialize(parse(t)), t);
});

test("J5 __proto__ is an ordinary key", () => {
  const v = parse('{"__proto__":{"polluted":true}}');
  assert.equal(({}).polluted, undefined);
  assert.equal(canonical(v), '{"__proto__":{"polluted":true}}');
});

// ---- R: receipt core --------------------------------------------------------
test("R conformance vectors from docs/standards/orc/vectors.json", () => {
  const vectors = parse(readFileSync(join(ROOT, "docs/standards/orc/vectors.json"), "utf8")).get("vectors");
  assert.ok(vectors.length >= 3);
  for (const v of vectors) {
    assert.equal(verifyReceipt(v.get("receipt")).level, Number(v.get("expect_level").lex), v.get("name"));
  }
});

test("R2 R6 seal is pure and rejects floats", () => {
  const out = { a: "1.50", n: 3 };
  const r1 = seal(out, { issuer: ISSUER, subject: {}, salt: "ab".repeat(32) });
  const r2 = seal(out, { issuer: ISSUER, subject: {} });
  assert.deepEqual(out, { a: "1.50", n: 3 });
  assert.equal(r1.digest.value, r2.digest.value);
  assert.notEqual(r1.commitment.value, r2.commitment.value);
  assert.throws(() => seal({ x: 0.5 }, { issuer: ISSUER, subject: {} }), RangeError);
  assert.throws(() => seal(parse('{"x":1.0}'), { issuer: ISSUER, subject: {} }), RangeError);
});

test("R3 verify never throws", () => {
  for (const junk of [null, 5, "x", [], { orc: "0.1", digest: null }, { orc: "0.1", digest: [] }, parse('{"orc":"0.1","output":[]}')]) {
    assert.equal(verifyReceipt(junk).level, 0);
  }
});

test("R5 levels above INTACT need resolvers", () => {
  const r = seal({ a: 1 }, { issuer: ISSUER, subject: {} });
  assert.equal(verifyReceipt(r).label, "INTACT");
  assert.equal(verifyReceipt(r, { issuerResolver: () => true }).label, "ISSUED");
  assert.equal(verifyReceipt(r, { issuerResolver: () => false }).label, "INTACT");
});

// ---- M: sealer --------------------------------------------------------------
test("M1 M6 result preserved and only one _meta key added", async () => {
  const s = new Sealer(ISSUER, { agent: "demo" });
  const req = parse(REQ), resp = parse(RESP);
  const before = serialize(resp);
  const out = await s.sealToolsCall(req, resp);
  assert.equal(serialize(resp), before); // input not mutated
  const r = out.get("result");
  assert.deepEqual([...r.get("_meta").keys()], ["other", META_KEY]);
  for (const k of ["content", "structuredContent"]) assert.equal(serialize(r.get(k)), serialize(resp.get("result").get(k)));
});

test("M2 receipt verifies and tampering is caught", async () => {
  const s = new Sealer(ISSUER);
  const out = await s.sealToolsCall(parse(REQ), parse(RESP));
  const text = serialize(out.get("result").get("_meta").get(META_KEY));
  assert.equal(verify(parse(text)).label, "INTACT");
  assert.equal(verify(parse(text.replace('"value":42', '"value":43'))).level, 0);
  const r = parse(text);
  assert.ok(r.get("verify").get("page").endsWith("/verify?c=" + r.get("commitment").get("value")));
});

test("M3 arguments never reach the receipt or the registry", async () => {
  const sent = [];
  const fetchImpl = async (url, init) => {
    const body = JSON.parse(init.body);
    sent.push({ url, body, headers: init.headers });
    return new Response(JSON.stringify({ commitment: body.commitment, digest: body.digest,
      issuer_proof: { method: "registry", url: "https://reg.test/orc/v0/commitments/" + body.commitment } }));
  };
  const s = new Sealer(ISSUER, { registry: new RegistryClient("https://reg.test", "k", { fetchImpl }) });
  const out = await s.sealToolsCall(parse(REQ), parse(RESP));
  const r = out.get("result").get("_meta").get(META_KEY);
  assert.ok(!serialize(r).includes("hunter2"));
  assert.deepEqual(Object.keys(sent[0].body).sort(), ["commitment", "digest", "issued_at", "issuer", "profile", "salt", "subject"]);
  assert.deepEqual(sent[0].body.subject, { agent: "", tool: "double" });
  assert.equal(sent[0].headers.authorization, "Bearer k");
  assert.equal(sent[0].url, "https://reg.test/orc/v0/register");
});

test("M4 registry success gives ISSUED; every failure fails open to INTACT", async () => {
  const echo = async (_u, init) => {
    const b = JSON.parse(init.body);
    return new Response(JSON.stringify({ commitment: b.commitment, digest: b.digest, issuer_proof: { method: "registry", url: "https://x/c" } }));
  };
  const ok = new Sealer(ISSUER, { registry: new RegistryClient("https://reg.test", "k", { fetchImpl: echo }) });
  const r = await ok.seal("t", {}, { v: 2 });
  const rec = { commitment: r.commitment.value, digest: r.digest.value };
  assert.equal(verify(r, { registryRecord: rec }).label, "ISSUED");
  assert.equal(verify(r, { registryRecord: { ...rec, digest: "0".repeat(64) } }).label, "INTACT");

  const failures = [
    async () => { throw new TypeError("fetch failed"); },
    async () => new Response("{}", { status: 500 }),
    async () => new Response("not json"),
    async () => new Response(JSON.stringify({ commitment: "0".repeat(64), digest: "0".repeat(64), issuer_proof: { method: "registry", url: "https://x" } })),
    () => new Promise(() => {}), // never answers: the timeout must fire
  ];
  for (const fetchImpl of failures) {
    const reg = new RegistryClient("https://reg.test", "k", { fetchImpl: (u, init) => Promise.race([fetchImpl(u, init), new Promise((_, rej) => init.signal.addEventListener("abort", () => rej(init.signal.reason)))]), timeoutMs: 50 });
    const out = await new Sealer(ISSUER, { registry: reg }).sealToolsCall(parse(REQ), parse(RESP));
    const rr = out.get("result").get("_meta").get(META_KEY);
    assert.equal(rr.issuer_proof, undefined);
    assert.equal(verify(rr).label, "INTACT");
    assert.ok(reg.lastError);
  }
});

test("M5 normalize is deterministic and idempotent", () => {
  const n = normalize(parse('{"1":[0.1,NaN,Infinity,-Infinity,3],"k":[true,null,1.0]}'));
  assert.equal(canonical(n), '{"1":["0.1","NaN","Infinity","-Infinity",3],"k":[true,null,"1.0"]}');
  assert.equal(canonical(normalize(n)), canonical(n));
  assert.equal(canonical(normalize(new Uint8Array([97, 98]))), '{"bytes_sha256":"fb8e20fc2e4c3f248c60c39bd652f3c1347298bb977b8b4d5903b85055620603"}');
});

test("M6 errors, isError and other methods pass through untouched", async () => {
  const s = new Sealer(ISSUER);
  const err = parse('{"jsonrpc":"2.0","id":7,"error":{"code":-1,"message":"x"}}');
  assert.equal(await s.sealToolsCall(parse(REQ), err), err);
  const ie = parse('{"jsonrpc":"2.0","id":7,"result":{"content":[],"isError":true}}');
  assert.equal(await s.sealToolsCall(parse(REQ), ie), ie);
  const other = parse('{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}');
  assert.equal(await s.sealToolsCall(parse('{"method":"tools/list","id":1}'), other), other);
});

test("M7 oversized results pass through unsealed", async () => {
  const s = new Sealer(ISSUER);
  const big = parse(JSON.stringify({ jsonrpc: "2.0", id: 7, result: { content: [{ type: "text", text: "a".repeat(300000) }] } }));
  const out = await s.sealToolsCall(parse(REQ), big);
  assert.equal(serialize(out.get("result").get("_meta").get(META_KEY)), '{"skipped":"too_large"}');
});

test("issuer id is required", () => {
  assert.throws(() => new Sealer({ name: "no id" }), TypeError);
});

// ---- P: proxy ---------------------------------------------------------------
test("P1 non-tool lines are forwarded byte-for-byte", async () => {
  const s = new Sealer(ISSUER), t = new Tracker();
  for (const line of ["garbage\n", '{"jsonrpc":"2.0","method":"notifications/x"}\n', '{"jsonrpc":"2.0","id":9,"result":{"a":1.50}}\n', "[1,2]\n", "\xff\n"]) {
    const buf = Buffer.from(line, "latin1");
    assert.equal(await transformServerLine(buf, t, s), buf);
  }
});

function runProxy(args, stdinText, { keepOpenMs } = {}) {
  return new Promise((resolve) => {
    const p = spawn(process.execPath, [BIN, ...args], { stdio: ["pipe", "pipe", "pipe"] });
    let out = "", err = "";
    p.stdout.on("data", (c) => { out += c; });
    p.stderr.on("data", (c) => { err += c; });
    const started = Date.now();
    let timer;
    p.on("exit", (code) => {
      const ms = Date.now() - started;
      clearTimeout(timer);
      p.stdin.destroy();
      p.on("close", () => resolve({ code, out, err, ms }));
    });
    p.stdin.on("error", () => {});
    p.stdin.write(stdinText);
    if (keepOpenMs === undefined) p.stdin.end();
    else timer = setTimeout(() => p.stdin.end(), keepOpenMs);
  });
}

test("P end-to-end: sealed in order, floats keep their spelling", async () => {
  const msgs = [
    { jsonrpc: "2.0", id: 1, method: "initialize", params: {} },
    { jsonrpc: "2.0", method: "notifications/initialized" },
    { jsonrpc: "2.0", id: "a", method: "tools/call", params: { name: "double", arguments: { x: 4 } } },
    { jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "fail" } },
    { jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "iserror" } },
  ];
  const { code, out, err } = await runProxy(["--issuer", "did:web:example.com", "--", process.execPath, join(HERE, "fake_server.mjs")],
    msgs.map((m) => JSON.stringify(m) + "\n").join(""));
  assert.equal(code, 0, err);
  const lines = out.trim().split("\n");
  assert.deepEqual(lines.map((l) => JSON.parse(l).id), [1, "a", 3, 4]); // P2
  assert.ok(lines[1].includes('"ratio":0.10,"one":1.0'), lines[1]); // J4 on the wire
  const sealed = parse(lines[1]).get("result");
  const receipt = sealed.get("_meta").get(META_KEY);
  assert.equal(verify(receipt).label, "INTACT");
  assert.equal(receipt.get("subject").get("agent"), process.execPath);
  assert.equal(canonical(receipt.get("output").get("result").get("structuredContent")),
    '{"note":"Caf\\u00e9 \\u2600","one":"1.0","ratio":"0.1","value":8}');
  assert.ok(!lines[3].includes("_meta"));
});

test("P4 server exits early: proxy exits with its code even with stdin open", async () => {
  const { code, ms } = await runProxy(["--issuer", "x", "--", process.execPath, "-e", "setTimeout(() => process.exit(5), 100)"],
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n', { keepOpenMs: 10000 });
  assert.equal(code, 5);
  assert.ok(ms < 5000, `proxy took ${ms} ms to exit`);
});

test("P4 server that cannot start gives 127", async () => {
  const { code, err } = await runProxy(["--issuer", "x", "--", "/nonexistent/orc-seal-test-server"], "");
  assert.equal(code, 127);
  assert.match(err, /cannot start server/);
});

// ---- CLI --------------------------------------------------------------------
test("CLI options, help, badge and usage errors", async () => {
  assert.deepEqual(parseOptions(["--issuer=did:web:a", "--name", "A"]).issuer, "did:web:a");
  assert.throws(() => parseOptions(["--name", "A"]), /--issuer/);
  assert.throws(() => parseOptions(["--bogus"]), /unrecognized/);
  const help = await runProxy(["--help"], "");
  assert.equal(help.code, 0);
  assert.match(help.out, /usage: orc-seal/);
  const badge = await runProxy(["badge"], "");
  assert.match(badge.out, /img\.shields\.io\/badge\/ORC-sealed/);
  const missing = await runProxy(["--issuer", "x"], "");
  assert.equal(missing.code, 2);
  assert.match(missing.err, /missing server command/);
});
