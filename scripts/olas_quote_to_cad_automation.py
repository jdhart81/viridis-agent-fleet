#!/usr/bin/env python3
"""Codex automation entrypoint for the Viridis Quote-to-CAD Olas Mech."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLAS_SERVICE_PARENT = ROOT / "_rnd-exploration"
OLAS_SERVICE_DIR = OLAS_SERVICE_PARENT / "olas_quote_to_cad_mech"


SAMPLE_REQUEST = {
    "tool": "viridis_quote_to_cad",
    "tier": "basic",
    "project_name": "Contractor shelf bracket",
    "part_name": "shelf_bracket",
    "description": "Make a simple quote-ready CAD intake for an aluminum shelf bracket.",
    "material": "aluminum",
    "dimensions_mm": {"length": 140, "width": 48, "height": 8},
    "features": [{"type": "through_hole", "x_mm": 35, "y_mm": 0, "diameter_mm": 6}],
    "estimated_volume": 50,
}


def load_service():
    sys.path.insert(0, str(OLAS_SERVICE_PARENT))
    from olas_quote_to_cad_mech.src import QuoteToCadMechService

    return QuoteToCadMechService(root=ROOT)


def cmd_smoke(_: argparse.Namespace) -> int:
    service = load_service()
    health = service.health()
    direct_quote = service.quote(SAMPLE_REQUEST)
    result = service.execute_marketplace(SAMPLE_REQUEST)
    marketplace_quote = result["quote"]
    checks = [
        health["status"] == "ok",
        direct_quote["status"] == "accepted",
        direct_quote["cost_guard"] == "pass",
        marketplace_quote["status"] == "accepted",
        marketplace_quote["cost_guard"] == "pass",
        marketplace_quote["tier"] == "olas_marketplace",
        marketplace_quote["price_amount"] == 5.0,
        marketplace_quote["price_currency"] == "xDAI",
        result["marketplace_terms"]["required_delivery_rate_wei"] == 5_000_000_000_000_000_000,
        result["status"] == "completed",
        "openscad" in result["cad_design"]["outputs"],
        result["settlement"]["completion"]["success"] is True,
    ]
    print(
        json.dumps(
            {
                "health": health,
                "direct_quote": direct_quote,
                "marketplace_quote": marketplace_quote,
                "marketplace_terms": result["marketplace_terms"],
                "job_id": result["job_id"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    if not all(checks):
        print("Olas Quote-to-CAD smoke failed", file=sys.stderr)
        return 1
    print("Olas Quote-to-CAD smoke passed")
    return 0


def cmd_sample(_: argparse.Namespace) -> int:
    service = load_service()
    print(
        json.dumps(
            service.execute_marketplace(SAMPLE_REQUEST),
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(OLAS_SERVICE_PARENT))
    if args.adapter in ("auto", "fastapi"):
        try:
            import fastapi  # noqa: F401
            import uvicorn
        except ImportError:
            if args.adapter == "fastapi":
                print("fastapi/uvicorn is not installed. Use --adapter stdlib or install requirements.", file=sys.stderr)
                return 1
        else:
            uvicorn.run(
                "olas_quote_to_cad_mech.adapters.fastapi_server:app",
                host=args.host,
                port=args.port,
                reload=False,
            )
            return 0

    from olas_quote_to_cad_mech.adapters.http_server import run_http_server

    run_http_server(host=args.host, port=args.port)
    return 0


def cmd_sync_olas_tool(args: argparse.Namespace) -> int:
    target_root = Path(args.operate_mech).expanduser()
    target = target_root / "packages" / "viridis" / "customs" / "viridis_quote_to_cad"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OLAS_SERVICE_DIR / "olas_tool" / "viridis_quote_to_cad.py", target / "viridis_quote_to_cad.py")
    shutil.copy2(OLAS_SERVICE_DIR / "olas_tool" / "component.yaml", target / "component.yaml")
    init_file = target / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Viridis Quote-to-CAD Olas tool."""\n', encoding="utf-8")
    print(json.dumps({"status": "synced", "target": str(target), "required_env": {"VIRIDIS_FLEET_ROOT": str(ROOT)}}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("smoke", help="Run local deploy-readiness smoke check")
    smoke.set_defaults(func=cmd_smoke)

    sample = sub.add_parser("sample", help="Run and print a sample paid-job packet")
    sample.set_defaults(func=cmd_sample)

    serve = sub.add_parser("serve", help="Run the local off-chain HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8020)
    serve.add_argument("--adapter", choices=["auto", "stdlib", "fastapi"], default="auto")
    serve.set_defaults(func=cmd_serve)

    sync = sub.add_parser("sync-olas-tool", help="Copy the tool into an Olas ~/.operate-mech workspace")
    sync.add_argument("--operate-mech", default="~/.operate-mech")
    sync.set_defaults(func=cmd_sync_olas_tool)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
