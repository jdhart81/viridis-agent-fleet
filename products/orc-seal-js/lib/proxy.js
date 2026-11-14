// Stdio proxy: put orc-seal in front of ANY MCP server, in any language.
//
//     npx orc-seal --issuer did:web:example.com -- npx -y @acme/some-mcp-server
//
// --- INVARIANTS (same letters as the Python proxy) ---
// P1  Transparency: lines that are not JSON objects, requests, notifications,
//     and responses to anything other than tools/call are forwarded
//     byte-for-byte. Client-to-server traffic is always forwarded byte-for-byte.
// P2  Ordering: server-to-client lines are written in the order received, even
//     while a registry call for an earlier line is in flight.
// P3  The proxy never originates JSON-RPC messages of its own.
// P4  Exit: when the server exits, the proxy exits with the server's code
//     (128 + signal number if the server was killed by a signal).

import { spawn } from "node:child_process";
import { constants as osConstants } from "node:os";
import { canonical, get, isObject, parse, serialize } from "./json.js";

const decoder = new TextDecoder("utf-8", { fatal: true });

function parseLine(buf) {
  try {
    return parse(decoder.decode(buf));
  } catch {
    return undefined;
  }
}

/** Remembers tools/call requests by id until their response arrives. */
export class Tracker {
  constructor() { this.pending = new Map(); }

  noteClientLine(buf) {
    const msg = parseLine(buf);
    if (isObject(msg) && get(msg, "method") === "tools/call" && get(msg, "id") !== undefined) {
      this.pending.set(canonical(get(msg, "id")), msg);
    }
  }

  take(id) {
    const key = canonical(id);
    const req = this.pending.get(key);
    this.pending.delete(key);
    return req;
  }
}

/** Resolve to the bytes to write to the client for one server line. */
export async function transformServerLine(buf, tracker, sealer) {
  const msg = parseLine(buf);
  if (!isObject(msg) || get(msg, "id") === undefined || get(msg, "method") !== undefined) return buf; // P1
  const req = tracker.take(get(msg, "id"));
  if (req === undefined) return buf; // P1
  const out = await sealer.sealToolsCall(req, msg);
  if (out === msg) return buf;
  const crlf = buf.length >= 2 && buf[buf.length - 2] === 0x0d && buf[buf.length - 1] === 0x0a;
  return Buffer.from(serialize(out) + (crlf ? "\r\n" : "\n"), "utf8");
}

/** Split a byte stream into lines that keep their terminators. */
export function lineSplitter(onLine) {
  let pending = Buffer.alloc(0);
  return {
    push(chunk) {
      pending = pending.length ? Buffer.concat([pending, chunk]) : chunk;
      let nl;
      while ((nl = pending.indexOf(0x0a)) !== -1) {
        onLine(pending.subarray(0, nl + 1));
        pending = pending.subarray(nl + 1);
      }
    },
    end() {
      if (pending.length) onLine(pending); // a last line without a newline
      pending = Buffer.alloc(0);
    },
  };
}

function writeAll(stream, buf) {
  return new Promise((resolve) => {
    if (stream.write(buf)) resolve();
    else stream.once("drain", resolve);
  });
}

/**
 * Run `cmd` behind the sealer. Resolves to the exit code the proxy should use.
 * `io` lets tests supply their own streams.
 */
export function run(cmd, sealer, io = {}) {
  const stdin = io.stdin ?? process.stdin;
  const stdout = io.stdout ?? process.stdout;
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(cmd[0], cmd.slice(1), { stdio: ["pipe", "pipe", "inherit"], windowsHide: true });
    } catch (exc) {
      process.stderr.write(`orc-seal: cannot start server: ${exc.message}\n`);
      resolve(127);
      return;
    }
    const tracker = new Tracker();
    let chain = Promise.resolve();
    let exitCode = null;
    let stdoutDone = false;
    let spawnFailed = false;

    const finish = () => {
      if (spawnFailed || exitCode === null || !stdoutDone) return;
      chain.then(() => resolve(exitCode)); // P4, after every line is written (P2)
    };

    child.on("error", (exc) => {
      spawnFailed = true;
      process.stderr.write(`orc-seal: cannot start server: ${exc.message}\n`);
      resolve(127);
    });
    child.on("exit", (code, signal) => {
      exitCode = code ?? 128 + (osConstants.signals[signal] ?? 0);
      finish();
    });

    // client -> server: byte-for-byte, noting tools/call ids on the way (P1).
    const fromClient = lineSplitter((line) => {
      tracker.noteClientLine(line);
      if (child.stdin.writable) child.stdin.write(line);
    });
    child.stdin.on("error", () => {}); // EPIPE once the server has exited
    stdin.on("data", (c) => fromClient.push(c));
    stdin.on("end", () => { fromClient.end(); child.stdin.end(); });

    // server -> client: in order, sealing tools/call responses (P2).
    const fromServer = lineSplitter((line) => {
      chain = chain
        .then(() => transformServerLine(line, tracker, sealer))
        .catch(() => line)
        .then((out) => writeAll(stdout, out));
    });
    child.stdout.on("data", (c) => fromServer.push(c));
    child.stdout.on("end", () => { fromServer.end(); stdoutDone = true; finish(); });

    for (const sig of ["SIGTERM", "SIGHUP"]) {
      process.once(sig, () => { try { child.kill(sig); } catch { /* already gone */ } });
    }
  });
}
