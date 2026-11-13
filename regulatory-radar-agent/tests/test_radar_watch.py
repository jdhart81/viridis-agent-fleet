"""Radar Watch: a durable log of official-source text changes, polled by cursor.

RW1  one record per (source, previous text, new text); a first observation or
     a normalizer reset is a baseline, never a change
RW2  the log is append-only and a record's seq is its line number; a poll with
     since=c returns exactly the selected changes with seq > c
RW3  a poll does not fetch while the last sweep is fresh; when it sweeps it
     sweeps every registered source
RW4  without a store the watch fails closed
RW5  the answer names what was watched and what could not be retrieved
RW6  the log holds hashes and a bounded excerpt, never the page text
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]

from src.core import RegulatoryRadarCore  # noqa: E402
from src import live_sources  # noqa: E402
from src.live_sources import (  # noqa: E402
    OFFICIAL_SOURCES, SourceFetchError, change_log_path, load_change_log,
    normalize_text)

ALL = sorted(source.source_id for source in OFFICIAL_SOURCES)
CARB = "carb-climate-disclosure-rulemaking"
SEC = "sec-climate-disclosure-2026"
BASE = ("Official notice. The reporting program applies to covered entities "
        "and the board has published guidance for the first reporting year. ")


class Pages:
    """A fetcher over an editable set of page texts; counts every fetch."""

    def __init__(self):
        self.text = {source_id: BASE + source_id for source_id in ALL}
        self.fail = set()
        self.fetches = []

    def __call__(self, source):
        self.fetches.append(source.source_id)
        if source.source_id in self.fail:
            raise SourceFetchError(f"{source.source_id}: unreachable")
        normalized = normalize_text(
            f"<html><body>{self.text[source.source_id]}</body></html>")
        return {
            "source_id": source.source_id, "title": source.title,
            "authority": source.authority, "jurisdiction": source.jurisdiction,
            "topics": list(source.topics), "source_url": source.url,
            "final_url": source.url,
            "retrieved_at": datetime.utcnow().isoformat() + "Z",
            "http_status": 200, "content_type": "text/html",
            "content_bytes": len(normalized),
            "normalizer_version": live_sources.NORMALIZER_VERSION,
            "published_on": source.published_on,
            "screening_summary": source.screening_summary,
            "review_focus": source.review_focus,
            "normalized_text": normalized,
            "sha256": live_sources.sha256(normalized.encode()).hexdigest(),
        }


@pytest.fixture()
def radar(tmp_path):
    pages = Pages()
    store = tmp_path / "radar" / "snapshots.json"
    core = RegulatoryRadarCore(live_fetcher=pages, live_fetch_enabled=True,
                               snapshot_store_path=str(store))
    return core, pages, store


async def poll(core, **request):
    return await core.process({"action": "watch_changes", **request})


def age_last_sweep(store, hours):
    """Rewrite the last sweep record's time, as if it ran `hours` ago."""
    path = change_log_path(store)
    lines = path.read_text().splitlines()
    for index in range(len(lines) - 1, -1, -1):
        record = json.loads(lines[index])
        if record["type"] == "sweep":
            record["at"] = (datetime.utcnow() - timedelta(hours=hours)
                            ).isoformat() + "Z"
            lines[index] = json.dumps(record, sort_keys=True)
            break
    path.write_text("\n".join(lines) + "\n")


@pytest.mark.asyncio
async def test_rw1_first_poll_is_a_baseline_with_no_changes(radar):
    core, pages, store = radar
    got = await poll(core, jurisdiction="california")
    assert got["status"] == "success" and got["changes"] == []
    assert got["swept_for_this_call"] is True
    assert sorted(pages.fetches) == ALL                      # RW3: every source
    log = load_change_log(store)
    assert [record["type"] for record in log] == ["sweep"]
    assert got["cursor"] == 1


@pytest.mark.asyncio
async def test_rw2_change_is_logged_once_and_served_by_cursor(radar):
    core, pages, store = radar
    first = await poll(core, jurisdiction="california")
    pages.text[CARB] = BASE + "The reporting deadline moved to August 10, 2026."
    age_last_sweep(store, 30)
    second = await poll(core, jurisdiction="california", since=first["cursor"])
    assert second["change_count"] == 1
    change = second["changes"][0]
    assert change["source_id"] == CARB and change["seq"] > first["cursor"]
    assert change["previous_sha256"] != change["sha256"]
    assert change["diff_excerpt"] and change["detected_at"]
    # polling again from the new cursor returns nothing; from 0 returns it again
    assert (await poll(core, jurisdiction="california",
                       since=second["cursor"]))["changes"] == []
    assert len((await poll(core, jurisdiction="california"))["changes"]) == 1
    # an unchanged re-sweep does not log the same change twice
    age_last_sweep(store, 30)
    third = await poll(core, jurisdiction="california", since=0)
    assert [c["event_id"] for c in third["changes"]] == [change["event_id"]]
    seqs = [record["seq"] for record in load_change_log(store)]
    assert seqs == list(range(1, len(seqs) + 1))


@pytest.mark.asyncio
async def test_rw2_selection_filters_changes_but_the_cursor_covers_the_log(radar):
    core, pages, store = radar
    await poll(core, jurisdiction="eu")
    pages.text[SEC] = BASE + "The Commission withdrew the proposal entirely."
    pages.text[CARB] = BASE + "A new reporting template was posted for filers."
    age_last_sweep(store, 30)
    eu = await poll(core, jurisdiction="eu")
    us = await poll(core, jurisdiction="us")
    assert eu["changes"] == []
    assert {c["source_id"] for c in us["changes"]} == {SEC, CARB}
    assert eu["cursor"] == us["cursor"] == load_change_log(store)[-1]["seq"]


@pytest.mark.asyncio
async def test_rw3_fresh_sweep_is_reused_and_stale_sweep_is_refreshed(radar):
    core, pages, store = radar
    await poll(core, jurisdiction="us")
    pages.fetches.clear()
    again = await poll(core, jurisdiction="us")
    assert pages.fetches == [] and again["swept_for_this_call"] is False
    age_last_sweep(store, 5)
    assert (await poll(core, jurisdiction="us", max_age_hours=6)
            )["swept_for_this_call"] is False
    assert (await poll(core, jurisdiction="us", max_age_hours=4)
            )["swept_for_this_call"] is True
    assert sorted(pages.fetches) == ALL


@pytest.mark.asyncio
async def test_rw4_no_store_or_no_live_retrieval_fails_closed():
    for kwargs in ({"live_fetch_enabled": True, "snapshot_store_path": ""},
                   {"live_fetch_enabled": False, "snapshot_store_path": "/tmp/x.json"}):
        core = RegulatoryRadarCore(live_fetcher=Pages(), **kwargs)
        core.snapshot_store_path = (Path(kwargs["snapshot_store_path"])
                                    if kwargs["snapshot_store_path"] else None)
        got = await poll(core, jurisdiction="us")
        assert got["status"] == "error" and got["watch_status"] == "unavailable"
        assert "changes" not in got


@pytest.mark.asyncio
async def test_rw5_answer_names_sources_and_reports_what_was_not_retrieved(radar):
    core, pages, store = radar
    pages.fail.add(CARB)
    got = await poll(core, jurisdiction="california")
    assert got["watch_status"] == "partial"
    assert got["sources_not_retrieved_in_last_sweep"] == [CARB]
    by_id = {source["source_id"]: source for source in got["sources_watched"]}
    assert by_id[CARB]["retrieved_in_last_sweep"] is False
    assert by_id[CARB]["source_url"].startswith("https://ww2.arb.ca.gov/")
    assert all(source["authority"] for source in got["sources_watched"])
    assert got["next_poll"]["arguments"]["since"] == got["cursor"]
    assert "not a legal" in got["coverage_note"]
    assert got["deadline_calendar"]["jurisdiction"] == "california"
    # an unreachable source is not a change when it comes back unchanged
    pages.fail.clear()
    age_last_sweep(store, 30)
    back = await poll(core, jurisdiction="california")
    assert back["changes"] == [] and back["watch_status"] == "complete"


@pytest.mark.asyncio
async def test_rw6_log_holds_hashes_and_a_bounded_excerpt_not_the_text(radar):
    core, pages, store = radar
    await poll(core, jurisdiction="us")
    pages.text[SEC] = BASE + " ".join(f"word{i}" for i in range(400))
    age_last_sweep(store, 30)
    await poll(core, jurisdiction="us")
    raw = change_log_path(store).read_text()
    assert "word399" not in raw and "normalized_text" not in raw
    change = [r for r in load_change_log(store) if r["type"] == "change"][0]
    words = sum(len(line.split()) for line in change["diff_excerpt"]
                if not line.startswith(("---", "+++", "@@", "...")))
    assert words <= 25


@pytest.mark.asyncio
async def test_evidence_pack_change_is_logged_for_watchers(radar):
    core, pages, store = radar
    await poll(core, jurisdiction="us")
    pages.text[SEC] = BASE + "Comment period extended to September."
    pack = await core.process({"action": "build_evidence_pack",
                               "jurisdiction": "us", "source_ids": [SEC]})
    assert pack["live_source_monitoring"]["changed_count"] == 1
    got = await poll(core, jurisdiction="us")           # sweep still fresh: no fetch
    assert got["swept_for_this_call"] is False
    assert [c["source_id"] for c in got["changes"]] == [SEC]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"since": -1}, {"since": "3"}, {"since": True},
                                 {"max_age_hours": 0}, {"max_age_hours": 500},
                                 {"jurisdiction": "Mars"}, {}])
async def test_bad_polls_get_a_teaching_error(radar, bad):
    core, _pages, _store = radar
    got = await poll(core, **({"jurisdiction": "us", **bad} if bad else {}))
    assert got["status"] == "error" and got["error_type"] == "ValidationError"
    assert "first_call_help" in got


@pytest.mark.asyncio
async def test_no_matching_source_is_an_error_not_an_empty_watch(radar):
    core, _pages, _store = radar
    got = await poll(core, jurisdiction="jp")
    assert got["status"] == "error" and "nothing would be watched" in got["message"]
