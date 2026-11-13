"""Call the sample server through orc-seal the way an MCP client would, then
save the receipt that came back with the result.

    python drive.py did:web:yourdomain.com

Writes receipt.json next to this file. Check it with `orc-seal verify receipt.json`.
Set ORC_SEAL_API_KEY first to get an ISSUED (registered) receipt instead of INTACT.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
META_KEY = "com.viridisconservation/orc"


def main(issuer: str) -> int:
    cmd = [sys.executable, "-m", "orc_seal", "--issuer", issuer, "--",
           sys.executable, str(HERE / "sample_server.py")]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def rpc(mid, method, params=None):
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method,
                                  "params": params or {}}) + "\n")
        p.stdin.flush()
        return json.loads(p.stdout.readline())

    rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "five-minute", "version": "0"}})
    out = rpc(2, "tools/call", {"name": "quote", "arguments": {"kwh": 1000}})
    p.stdin.close()
    p.wait(timeout=10)

    result = out["result"]
    receipt = result.get("_meta", {}).get(META_KEY)
    if receipt is None:
        print("no receipt on the result", file=sys.stderr)
        return 1
    (HERE / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print("result:", json.dumps(result["structuredContent"]))
    print("receipt saved to receipt.json;",
          "registered" if "issuer_proof" in receipt else "not registered (INTACT)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python drive.py <issuer id, e.g. did:web:yourdomain.com>")
    sys.exit(main(sys.argv[1]))
