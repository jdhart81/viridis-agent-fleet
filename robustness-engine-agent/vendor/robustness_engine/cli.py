"""Command-line entry point for deterministic robustness evaluations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .canonical import canonical_json
from .engine import evaluate_case


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate a robustness decision case")
    parser.add_argument("case", type=Path, help="Decision-case JSON file")
    parser.add_argument("outcomes", type=Path, help="Outcome-bundle JSON file")
    parser.add_argument("--output", type=Path, help="Optional output file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON instead of canonical JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    record = evaluate_case(_load_json(args.case), _load_json(args.outcomes))
    if args.pretty:
        rendered = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    else:
        rendered = canonical_json(record) + "\n"

    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    if record["status"] in {"DECISION", "DECISION_READY"}:
        return 0
    if record["status"] == "HOLD":
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
