"""CLI.

  orc-seal --issuer did:web:example.com [--name "Example"] [--agent my-server]
           [--registry https://mcp.viridisconservation.com] -- <server command...>
  orc-seal verify receipt.json

Registration (L2 ISSUED) is enabled when ORC_SEAL_API_KEY is set.
Without a key, receipts are self-sealed (L1 INTACT) and nothing leaves the machine.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

from .proxy import run
from .sealer import DEFAULT_REGISTRY, RegistryClient, Sealer, verify


def _lookup(url: str):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["verify"]:
        if len(argv) != 2:
            print("usage: orc-seal verify receipt.json", file=sys.stderr)
            return 2
        with open(argv[1]) as f:
            receipt = json.load(f)
        out = verify(receipt, registry_lookup=_lookup)
        print(json.dumps({"level": out["level"], "label": out["label"],
                          "reasons": out["reasons"]}, indent=2))
        return 0 if out["level"] >= 1 else 1
    if "--" not in argv:
        print(__doc__, file=sys.stderr)
        return 2
    i = argv.index("--")
    opts, cmd = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(prog="orc-seal")
    p.add_argument("--issuer", required=True, help="issuer id, e.g. did:web:example.com")
    p.add_argument("--name", default="")
    p.add_argument("--agent", default="")
    p.add_argument("--registry", default=os.environ.get("ORC_SEAL_REGISTRY", DEFAULT_REGISTRY))
    a = p.parse_args(opts)
    if not cmd:
        p.error("missing server command after --")
    key = os.environ.get("ORC_SEAL_API_KEY", "")
    registry = RegistryClient(a.registry, key) if key else None
    sealer = Sealer({"id": a.issuer, "name": a.name or a.issuer}, agent=a.agent or cmd[0],
                    registry=registry, verify_base=a.registry)
    return run(cmd, sealer)


if __name__ == "__main__":
    sys.exit(main())
