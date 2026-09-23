#!/usr/bin/env python3
"""Generate a buyer-readable Regulatory Change Evidence Pack."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "regulatory-radar-agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.core import RegulatoryRadarCore  # noqa: E402


def _escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(pack: dict) -> str:
    live = pack["live_source_monitoring"]
    profile = pack.get("company_profile") or {}
    receipt = pack["delivery_receipt"]
    lines = [
        "# Regulatory Change Evidence Pack",
        "",
        f"Generated: `{pack['generated_at']}`  ",
        f"Jurisdiction: `{pack['jurisdiction']}`  ",
        f"Company: `{profile.get('company_name', 'Illustrative screening profile')}`  ",
        f"Pack SHA-256: `{receipt['pack_sha256']}`",
        "",
        "## Executive signal",
        "",
        (
            f"Viridis retrieved {live['retrieved_source_count']} of "
            f"{live['selected_source_count']} selected official sources: "
            f"{live['changed_count']} changed, {live['baseline_count']} new "
            f"baselines, {live['unchanged_count']} unchanged, and "
            f"{live['failed_count']} failed retrievals."
        ),
        "",
        "A first baseline is not presented as a detected regulatory change. "
        "A later content-hash change produces a bounded before-and-after text diff.",
        "",
        "## Official-source evidence",
        "",
        "| Authority | Observation | Retrieved | SHA-256 | Source |",
        "|---|---|---|---|---|",
    ]
    for source in live["sources"]:
        lines.append(
            "| {authority} | {status} | {retrieved} | `{digest}` | [Official page]({url}) |".format(
                authority=_escape(source["authority"]),
                status=_escape(source["change_status"]),
                retrieved=_escape(source["retrieved_at"]),
                digest=source["sha256"],
                url=source["source_url"],
            )
        )
        if source.get("diff_excerpt"):
            lines.extend([
                "",
                f"### Detected text change: {source['title']}",
                "",
                "```diff",
                *source["diff_excerpt"],
                "```",
            ])

    lines.extend([
        "",
        "## Current authority signal",
        "",
        "| Official update | Published | Screening summary | Review focus |",
        "|---|---|---|---|",
    ])
    for source in live["sources"]:
        lines.append(
            f"| {_escape(source['title'])} | "
            f"{_escape(source.get('published_on') or 'rolling page')} | "
            f"{_escape(source['screening_summary'])} | "
            f"{_escape(source['review_focus'])} |"
        )

    calendar = pack["curated_deadline_calendar"]
    lines.extend([
        "",
        "## Curated deadline calendar",
        "",
        f"Alert level: **{calendar['alert_level']}**. "
        f"Items in the selected window: **{calendar['change_count']}**.",
        "",
        "| Regulation | Status | Key date | Source |",
        "|---|---|---|---|",
    ])
    for change in calendar.get("changes", [])[:10]:
        key_date = change.get("deadline") or change.get("effective_date") or "none"
        source_link = (
            f"[Authority]({change['source_url']})"
            if change.get("source_url") else "not recorded"
        )
        lines.append(
            f"| {_escape(change['regulation_name'])} | "
            f"{_escape(change['legal_status'])} | {_escape(key_date)} | "
            f"{source_link} |"
        )

    lines.extend(["", "## Recommended review actions", ""])
    actions = pack.get("recommended_actions") or [
        "No automated action was generated; retain the baseline for the next comparison."
    ]
    lines.extend(f"- {action}" for action in actions)
    lines.extend([
        "",
        "## Applicability and delivery boundary",
        "",
        pack["applicability_posture"]["notice"],
        "",
        "This artifact records source retrieval and screening output. It is not "
        "evidence of buyer delivery, buyer usefulness, renewal intent, or payment. "
        "Those fields remain unset until independently confirmed.",
        "",
    ])
    return "\n".join(lines)


async def generate(args: argparse.Namespace) -> dict:
    profile = {}
    if args.company_name:
        profile["company_name"] = args.company_name
    if args.sector:
        profile["sector"] = args.sector
    core = RegulatoryRadarCore(
        live_fetch_enabled=args.allow_live_fetch,
        snapshot_store_path=str(args.snapshot_store),
    )
    return await core.process({
        "action": "build_evidence_pack",
        "jurisdiction": args.jurisdiction,
        "topics": args.topic,
        "source_ids": args.source_id,
        "lookback_days": args.lookback_days,
        "company_profile": profile,
        "persist_snapshot": True,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jurisdiction", required=True)
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--company-name")
    parser.add_argument("--sector")
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--snapshot-store", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument(
        "--allow-live-fetch",
        action="store_true",
        help="Explicitly authorize retrieval of registry-owned official URLs.",
    )
    args = parser.parse_args()
    pack = asyncio.run(generate(args))
    if pack.get("status") != "success":
        print(json.dumps(pack, indent=2, sort_keys=True))
        return 1
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(pack), encoding="utf-8")
    print(json.dumps({
        "status": "success",
        "json_output": str(args.json_output),
        "markdown_output": str(args.markdown_output),
        "pack_sha256": pack["delivery_receipt"]["pack_sha256"],
        "live_source_status": pack["live_source_monitoring"]["status"],
        "retrieved_source_count": pack["live_source_monitoring"]["retrieved_source_count"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
