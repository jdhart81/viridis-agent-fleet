#!/usr/bin/env python3
"""Launch the five-offer claimant only after Payan deploys verificationBody."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SKILL_URL = "https://payanagent.com/SKILL.md"
CLAIMANT = Path("/root/viridis-fleet/claim_payanagent_catalog_offers_20260804.py")
CLAIM_AUTH = "claim-payanagent-legacy-catalog-viridis-fleet"
DEPLOYMENT_MARKERS = (
    "verificationBody",
    "only during the unpaid ownership probe",
)


def fetch_text(url: str, timeout: int = 30) -> tuple[int, str]:
    request = Request(
        url,
        headers={
            "Accept": "text/markdown,text/plain",
            "Cache-Control": "no-cache",
            "User-Agent": "Viridis-Payan-Catalog-Claim-Watch/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, ""


def deployment_ready(skill_text: str) -> bool:
    return all(marker in skill_text for marker in DEPLOYMENT_MARKERS)


def main() -> int:
    status, skill = fetch_text(SKILL_URL)
    if status != 200:
        print(json.dumps({"status": "waiting", "reason": f"skill_http_{status}"}))
        return 0
    if not deployment_ready(skill):
        print(
            json.dumps(
                {
                    "status": "waiting",
                    "reason": "verificationBody_not_deployed",
                    "writes_performed": 0,
                },
                sort_keys=True,
            )
        )
        return 0
    if not CLAIMANT.is_file():
        raise SystemExit("refusing: reviewed catalog claimant is missing")
    os.execv("/usr/bin/python3", ["python3", str(CLAIMANT), CLAIM_AUTH])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
