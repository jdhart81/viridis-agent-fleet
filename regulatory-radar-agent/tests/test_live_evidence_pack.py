import json
from hashlib import sha256

import pytest

from src.core import RegulatoryRadarCore
from src.live_sources import (
    NORMALIZER_VERSION,
    OFFICIAL_SOURCES,
    normalize_text,
    select_sources,
)


def _fake_fetcher(text_by_source):
    def fetch(source):
        text = text_by_source[source.source_id]
        normalized = normalize_text(text, "text/html")
        return {
            "source_id": source.source_id,
            "title": source.title,
            "authority": source.authority,
            "jurisdiction": source.jurisdiction,
            "topics": list(source.topics),
            "source_url": source.url,
            "final_url": source.url,
            "retrieved_at": "2026-08-14T12:00:00Z",
            "http_status": 200,
            "content_type": "text/html",
            "content_bytes": len(text.encode()),
            "normalizer_version": NORMALIZER_VERSION,
            "published_on": source.published_on,
            "screening_summary": source.screening_summary,
            "review_focus": source.review_focus,
            "normalized_text": normalized,
            "sha256": sha256(normalized.encode()).hexdigest(),
        }
    return fetch


def test_source_selection_never_accepts_arbitrary_urls():
    selected = select_sources("eu", ["esrs"])
    assert {source.source_id for source in selected} == {
        "eu-csrd-delegated-acts", "eu-esrs-revision-2026",
    }
    with pytest.raises(ValueError):
        select_sources("eu", source_ids=["https://example.com/private"])
    assert all(source.url.startswith("https://") for source in OFFICIAL_SOURCES)


def test_carb_registry_uses_current_official_urls():
    urls = {
        item.source_id: item.url for item in OFFICIAL_SOURCES
        if item.source_id.startswith("carb-")
    }
    assert urls == {
        "carb-corporate-climate-program": (
            "https://ww2.arb.ca.gov/our-work/programs/"
            "california-corporate-greenhouse-gas-reporting-and-climate-"
            "related-financial-risk"
        ),
        "carb-climate-disclosure-rulemaking": (
            "https://ww2.arb.ca.gov/rulemaking/2025/"
            "california-corporate-greenhouse-gas-reporting-and-climate-"
            "related-financial-risk"
        ),
        "carb-climate-disclosure-resources": (
            "https://ww2.arb.ca.gov/our-work/programs/"
            "corporate-ghg-reporting/resources"
        ),
    }
    assert all(url.startswith("https://ww2.arb.ca.gov/") for url in urls.values())


@pytest.mark.asyncio
async def test_first_pack_is_baseline_and_journaled(tmp_path):
    source_id = "eu-esrs-revision-2026"
    fetcher = _fake_fetcher({
        source_id: "<html><body>Official standard adopted July 3, 2026. "
        "Reporting requirements were simplified for covered entities.</body></html>",
    })
    store = tmp_path / "snapshots.json"
    core = RegulatoryRadarCore(
        live_fetcher=fetcher,
        live_fetch_enabled=True,
        snapshot_store_path=str(store),
    )

    result = await core.process({
        "action": "build_evidence_pack",
        "jurisdiction": "EU",
        "topics": ["esrs"],
        "source_ids": [source_id],
        "company_profile": {
            "company_name": "Design Partner Example",
            "sector": "manufacturing",
        },
    })

    assert result["status"] == "success"
    monitor = result["live_source_monitoring"]
    assert monitor["baseline_count"] == 1
    assert monitor["changed_count"] == 0
    assert monitor["sources"][0]["change_status"] == "baseline_created"
    assert monitor["sources"][0]["diff_excerpt"] == []
    assert monitor["persistence"]["status"] == "persisted"
    assert store.exists()
    journal = store.with_suffix(".json.journal.jsonl")
    assert journal.exists()
    assert result["delivery_receipt"]["delivered"] is False
    assert result["delivery_receipt"]["buyer_acknowledged_useful"] is None


@pytest.mark.asyncio
async def test_second_pack_reports_exact_diff(tmp_path):
    source_id = "sec-climate-disclosure-2026"
    store = tmp_path / "snapshots.json"
    first = RegulatoryRadarCore(
        live_fetcher=_fake_fetcher({
            source_id: "<p>Proposal remains open. Comment deadline August 1.</p>",
        }),
        live_fetch_enabled=True,
        snapshot_store_path=str(store),
    )
    initial = await first.process({
        "action": "build_evidence_pack",
        "jurisdiction": "US",
        "source_ids": [source_id],
    })
    assert initial["live_source_monitoring"]["baseline_count"] == 1

    second = RegulatoryRadarCore(
        live_fetcher=_fake_fetcher({
            source_id: "<p>Final rescission adopted. Effective September 1.</p>",
        }),
        live_fetch_enabled=True,
        snapshot_store_path=str(store),
    )
    changed = await second.process({
        "action": "build_evidence_pack",
        "jurisdiction": "US",
        "source_ids": [source_id],
    })

    monitor = changed["live_source_monitoring"]
    assert monitor["changed_count"] == 1
    diff = "\n".join(monitor["sources"][0]["diff_excerpt"])
    assert "-Proposal remains open" in diff
    assert "+Final rescission adopted" in diff
    assert changed["recommended_actions"][0].startswith(
        "Review the detected text change"
    )
    stored = json.loads(store.read_text())
    assert stored["sources"][source_id]["normalized_text"].startswith(
        "Final rescission adopted"
    )


@pytest.mark.asyncio
async def test_live_pack_fails_closed_when_not_authorized():
    core = RegulatoryRadarCore(live_fetch_enabled=False)
    result = await core.process({
        "action": "build_evidence_pack",
        "jurisdiction": "EU",
    })
    assert result["status"] == "error"
    assert result["error_type"] == "PermissionError"
    assert result["live_source_status"] == "disabled"
