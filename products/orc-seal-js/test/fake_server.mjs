// Minimal line-delimited JSON-RPC server for proxy tests (mirrors tests/fake_server.py).
import { createInterface } from "node:readline";

const rl = createInterface({ input: process.stdin });
rl.on("line", (line) => {
  let msg;
  try { msg = JSON.parse(line); } catch { process.stdout.write("not json from server\n"); return; }
  if (!("id" in msg)) return;
  let out;
  if (msg.method === "tools/call") {
    const name = msg.params.name;
    if (name === "fail") out = { jsonrpc: "2.0", id: msg.id, error: { code: -32000, message: "boom" } };
    else if (name === "iserror") out = { jsonrpc: "2.0", id: msg.id, result: { content: [{ type: "text", text: "bad" }], isError: true } };
    else {
      const x = (msg.params.arguments ?? {}).x ?? 0;
      // Hand-written so the float spelling (0.10, 1.0) reaches the proxy as-is.
      process.stdout.write(`{"jsonrpc":"2.0","id":${JSON.stringify(msg.id)},"result":{"content":[{"type":"text","text":"${x * 2}"}],"structuredContent":{"value":${x * 2},"ratio":0.10,"one":1.0,"note":"Café ☀"}}}\n`);
      return;
    }
  } else {
    out = { jsonrpc: "2.0", id: msg.id, result: { echo: msg.method } };
  }
  process.stdout.write(JSON.stringify(out) + "\n");
});
