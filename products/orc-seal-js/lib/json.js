// Lossless JSON for orc-seal. Zero dependencies.
//
// JavaScript's JSON.parse cannot tell 1.0 from 1, reorders integer-like keys
// and rounds integers above 2^53. The Python reference (orc_seal) sees all of
// those differences, and they change the digest. So this module parses JSON
// text into a tree that keeps what Python's json.loads keeps, and serializes
// it back exactly the way Python's json.dumps does.
//
// --- INVARIANTS ---
// J1  canonical(parse(text)) is byte-identical to Python's
//     json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"),
//     ensure_ascii=True) for every text both accept.
// J2  pyFloatRepr(x) === Python repr(float(x)) for every finite double.
// J3  parse() accepts what Python's json.loads(strict=True) accepts, including
//     NaN, Infinity and -Infinity, and rejects raw control characters in
//     strings. Duplicate keys: the last value wins, in the first key's position.
// J4  serialize(parse(text)) is semantically identical to text: numbers keep
//     their original spelling, object keys keep their original order.
// J5  No prototype pollution: object keys live in a Map, "__proto__" included.

export class JNum {
  /** @param {string} lex the number exactly as written in the source text */
  constructor(lex) {
    this.lex = lex;
    // Python's json.loads makes a float for any lexeme with '.', 'e' or 'E',
    // and for the NaN / Infinity literals. Everything else is an int.
    this.isFloat = /[.eE]/.test(lex) || lex === "NaN" || lex === "Infinity" || lex === "-Infinity";
  }

  /** The value Python would hold, as a JS number (floats) or BigInt (ints). */
  value() {
    if (!this.isFloat) return BigInt(this.lex);
    if (this.lex === "NaN") return NaN;
    if (this.lex === "Infinity") return Infinity;
    if (this.lex === "-Infinity") return -Infinity;
    return Number(this.lex);
  }
}

export class ParseError extends Error {}

const WS = new Set([0x20, 0x09, 0x0a, 0x0d]);
const MAX_INT_DIGITS = 4300; // CPython's default sys.int_info.default_max_str_digits

/** Parse JSON text into a tree of null | boolean | string | JNum | Array | Map. */
export function parse(text) {
  let i = 0;
  const n = text.length;

  const fail = (msg) => { throw new ParseError(`${msg} at offset ${i}`); };
  const ws = () => { while (i < n && WS.has(text.charCodeAt(i))) i++; };

  function value() {
    ws();
    if (i >= n) fail("unexpected end");
    const c = text[i];
    if (c === "{") return object();
    if (c === "[") return array();
    if (c === '"') return string();
    if (text.startsWith("true", i)) { i += 4; return true; }
    if (text.startsWith("false", i)) { i += 5; return false; }
    if (text.startsWith("null", i)) { i += 4; return null; }
    if (text.startsWith("NaN", i)) { i += 3; return new JNum("NaN"); }
    if (text.startsWith("Infinity", i)) { i += 8; return new JNum("Infinity"); }
    if (text.startsWith("-Infinity", i)) { i += 9; return new JNum("-Infinity"); }
    return number();
  }

  const NUM = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d+)?/y;
  function number() {
    NUM.lastIndex = i;
    const m = NUM.exec(text);
    if (!m) fail("bad value");
    const num = new JNum(m[0]);
    // Python 3.11+ refuses to parse ints longer than 4300 digits.
    if (!num.isFloat && m[0].replace("-", "").length > MAX_INT_DIGITS) fail("integer too long");
    i += m[0].length;
    return num;
  }

  function string() {
    i++; // opening quote
    let out = "";
    for (;;) {
      if (i >= n) fail("unterminated string");
      const code = text.charCodeAt(i);
      if (code === 0x22) { i++; return out; }
      if (code < 0x20) fail("control character in string");
      if (code === 0x5c) {
        const e = text[i + 1];
        i += 2;
        switch (e) {
          case '"': out += '"'; break;
          case "\\": out += "\\"; break;
          case "/": out += "/"; break;
          case "b": out += "\b"; break;
          case "f": out += "\f"; break;
          case "n": out += "\n"; break;
          case "r": out += "\r"; break;
          case "t": out += "\t"; break;
          case "u": {
            const h = text.slice(i, i + 4);
            if (!/^[0-9a-fA-F]{4}$/.test(h)) fail("bad \\u escape");
            out += String.fromCharCode(parseInt(h, 16));
            i += 4;
            break;
          }
          default: fail("bad escape");
        }
        continue;
      }
      out += text[i++];
    }
  }

  function array() {
    i++;
    const out = [];
    ws();
    if (text[i] === "]") { i++; return out; }
    for (;;) {
      out.push(value());
      ws();
      if (text[i] === ",") { i++; continue; }
      if (text[i] === "]") { i++; return out; }
      fail("expected , or ]");
    }
  }

  function object() {
    i++;
    const out = new Map();
    ws();
    if (text[i] === "}") { i++; return out; }
    for (;;) {
      ws();
      if (text[i] !== '"') fail("expected key");
      const k = string();
      ws();
      if (text[i] !== ":") fail("expected :");
      i++;
      out.set(k, value());
      ws();
      if (text[i] === ",") { i++; continue; }
      if (text[i] === "}") { i++; return out; }
      fail("expected , or }");
    }
  }

  const v = value();
  ws();
  if (i !== n) fail("extra data");
  return v;
}

/** Python repr() of a float (J2). */
export function pyFloatRepr(x) {
  if (Number.isNaN(x)) return "NaN";
  if (x === Infinity) return "inf";
  if (x === -Infinity) return "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const sign = x < 0 ? "-" : "";
  // toExponential() with no argument gives the shortest round-trip digits.
  const [mant, expStr] = Math.abs(x).toExponential().split("e");
  const digits = mant.replace(".", "");
  const exp = Number(expStr);
  const decpt = exp + 1; // value = 0.<digits> * 10^decpt
  let body;
  if (decpt > -4 && decpt <= 16) {
    if (decpt <= 0) body = "0." + "0".repeat(-decpt) + digits;
    else if (decpt >= digits.length) body = digits + "0".repeat(decpt - digits.length) + ".0";
    else body = digits.slice(0, decpt) + "." + digits.slice(decpt);
  } else {
    const m = digits.length > 1 ? digits[0] + "." + digits.slice(1) : digits;
    body = m + "e" + (exp < 0 ? "-" : "+") + String(Math.abs(exp)).padStart(2, "0");
  }
  return sign + body;
}

/** Python json.dumps of a float: repr, but NaN/Infinity spelled as JSON-ish literals. */
function pyJsonFloat(x) {
  if (Number.isNaN(x)) return "NaN";
  if (x === Infinity) return "Infinity";
  if (x === -Infinity) return "-Infinity";
  return pyFloatRepr(x);
}

function asciiString(s) {
  let out = '"';
  for (let k = 0; k < s.length; k++) {
    const c = s.charCodeAt(k);
    if (c === 0x22) out += '\\"';
    else if (c === 0x5c) out += "\\\\";
    else if (c === 0x0a) out += "\\n";
    else if (c === 0x0d) out += "\\r";
    else if (c === 0x09) out += "\\t";
    else if (c === 0x08) out += "\\b";
    else if (c === 0x0c) out += "\\f";
    else if (c < 0x20 || c > 0x7e) out += "\\u" + c.toString(16).padStart(4, "0");
    else out += s[k];
  }
  return out + '"';
}

/** Compare two strings by Unicode code point, as Python's sorted() does. */
export function codePointCompare(a, b) {
  const ia = a[Symbol.iterator]();
  const ib = b[Symbol.iterator]();
  for (;;) {
    const x = ia.next();
    const y = ib.next();
    if (x.done || y.done) return x.done === y.done ? 0 : x.done ? -1 : 1;
    const cx = x.value.codePointAt(0);
    const cy = y.value.codePointAt(0);
    if (cx !== cy) return cx < cy ? -1 : 1;
  }
}

function entries(obj) {
  return obj instanceof Map ? [...obj.entries()] : Object.entries(obj);
}

export function isObject(v) {
  return v instanceof Map || (v !== null && typeof v === "object" && !Array.isArray(v) && !(v instanceof JNum));
}

/** orc-canon/1: Python json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True) (J1). */
export function canonical(v) {
  if (v === null || v === undefined) return "null";
  if (v === true) return "true";
  if (v === false) return "false";
  if (typeof v === "string") return asciiString(v);
  if (typeof v === "bigint") return v.toString();
  if (typeof v === "number") return Number.isInteger(v) && !Object.is(v, -0) ? String(v) : pyJsonFloat(v);
  if (v instanceof JNum) {
    const x = v.value();
    return typeof x === "bigint" ? x.toString() : pyJsonFloat(x);
  }
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
  if (isObject(v)) {
    const es = entries(v).sort((a, b) => codePointCompare(a[0], b[0]));
    return "{" + es.map(([k, x]) => asciiString(k) + ":" + canonical(x)).join(",") + "}";
  }
  throw new TypeError(`not JSON-serializable: ${typeof v}`);
}

/** Compact JSON that keeps key order and number spelling (J4). Non-ASCII stays raw. */
export function serialize(v) {
  if (v === null || v === undefined) return "null";
  if (v === true) return "true";
  if (v === false) return "false";
  if (typeof v === "string") return JSON.stringify(v);
  if (typeof v === "bigint") return v.toString();
  if (typeof v === "number") return Number.isInteger(v) && !Object.is(v, -0) ? String(v) : pyJsonFloat(v);
  if (v instanceof JNum) return v.lex;
  if (Array.isArray(v)) return "[" + v.map(serialize).join(",") + "]";
  if (isObject(v)) return "{" + entries(v).map(([k, x]) => JSON.stringify(k) + ":" + serialize(x)).join(",") + "}";
  throw new TypeError(`not JSON-serializable: ${typeof v}`);
}

/** Read a key from a Map or a plain object. */
export function get(obj, key) {
  if (obj instanceof Map) return obj.get(key);
  if (obj !== null && typeof obj === "object" && Object.prototype.hasOwnProperty.call(obj, key)) return obj[key];
  return undefined;
}
