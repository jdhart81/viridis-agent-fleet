#!/usr/bin/env python3
"""Small scheduler for the isolated growth-agent container."""
import json
import os
import time

from growth_agent import build_default


def main() -> None:
    agent = build_default()
    interval = max(int(os.environ.get("GROWTH_AGENT_INTERVAL_SECONDS", "86400")),
                   3600)
    run_once = str(os.environ.get("GROWTH_AGENT_RUN_ONCE", "0")).lower() in {
        "1", "true", "yes", "on"}
    dry_run = str(os.environ.get("GROWTH_AGENT_DRY_RUN", "0")).lower() in {
        "1", "true", "yes", "on"}
    while True:
        result = agent.run_once(dry_run=dry_run)
        # Structured operational status only; credentials never enter result.
        print(json.dumps(result, sort_keys=True), flush=True)
        if run_once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
