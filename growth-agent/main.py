#!/usr/bin/env python3
"""Small scheduler for the isolated growth-agent container."""
import json
import os
import time

from growth_agent import GrowthError, build_default


def run_cycle(agent, *, dry_run: bool) -> dict:
    """Turn expected live-read failures into a fail-closed cycle result.

    Posting failures are already captured by ``GrowthAgent.run_once`` after
    the durable attempt record is written. This boundary is for expected
    operational failures such as a transient gateway/catalog error: report
    them without killing the long-running scheduler. Unexpected programming
    errors still raise and let the container fail visibly.
    """
    try:
        return agent.run_once(dry_run=dry_run)
    except GrowthError as exc:
        return {
            "status": "cycle_failed",
            "error_type": type(exc).__name__,
            "message": str(exc)[:300],
            "send_attempted": False,
        }


def main() -> None:
    agent = build_default()
    interval = max(int(os.environ.get("GROWTH_AGENT_INTERVAL_SECONDS", "86400")),
                   3600)
    run_once = str(os.environ.get("GROWTH_AGENT_RUN_ONCE", "0")).lower() in {
        "1", "true", "yes", "on"}
    dry_run = str(os.environ.get("GROWTH_AGENT_DRY_RUN", "0")).lower() in {
                   "1", "true", "yes", "on"}
    while True:
        result = run_cycle(agent, dry_run=dry_run)
        # Structured operational status only; credentials never enter result.
        print(json.dumps(result, sort_keys=True), flush=True)
        if run_once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
