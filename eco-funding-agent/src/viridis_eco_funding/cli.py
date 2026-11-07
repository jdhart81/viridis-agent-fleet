"""Command line: ``vef value|receipt|verify|simulate|describe``. Output is canonical JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .canonical import canonical_dumps, loads_decimal
from .explain import describe_method, explain_valuation
from .inputs import SiteInputError
from .pool import PoolSpecError, simulate_pool
from .receipt import make_receipt, verify_receipt
from .valuation import value_site


def _load(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return loads_decimal(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vef", description="viridis-eco-funding (read-only)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("value", "value a site (vef-site/0.1 JSON)"),
                            ("explain", "explain a site valuation step by step"),
                            ("receipt", "value a site and print a sealed receipt"),
                            ("verify", "re-run and verify a receipt")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("path", help="JSON file, or - for stdin")
    sim = sub.add_parser("simulate", help="simulate a pool (vef-pool/0.1 JSON)")
    sim.add_argument("pool")
    sim.add_argument("observations", nargs="?")
    sub.add_parser("describe", help="describe the method")
    args = parser.parse_args(argv)

    try:
        if args.command == "value":
            out: Any = value_site(_load(args.path))
        elif args.command == "explain":
            out = explain_valuation(_load(args.path))
        elif args.command == "receipt":
            out = make_receipt(_load(args.path))
        elif args.command == "verify":
            out = verify_receipt(_load(args.path))
        elif args.command == "simulate":
            observations = _load(args.observations) if args.observations else None
            out = simulate_pool(_load(args.pool), observations)
        else:
            out = describe_method()
    except (SiteInputError, PoolSpecError, ValueError, ArithmeticError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(canonical_dumps(out))
    if args.command == "verify" and not out["valid"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
