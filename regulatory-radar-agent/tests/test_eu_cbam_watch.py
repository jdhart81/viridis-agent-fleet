"""Radar Watch covers the European Commission's CBAM news page.

The public watch missed the 18 November 2026 announcement that CBAM extends to
Iceland and Norway, because no watched source covered CBAM. These tests pin the
new source and show the watch reports that announcement.

CB1  the registry holds eu-cbam-news, served over https from an official
     europa.eu host, in the eu jurisdiction, under the cbam topic
CB2  an eu watch filtered to cbam watches that source and nothing else
CB3  through the real fetch and normalizer, the first sweep is a baseline and
     the page gaining the Iceland and Norway item is reported as exactly one
     change for eu-cbam-news, with the new headline in the diff excerpt
CB4  a change to the page's header, menu or footer alone is not a change
CB5  a redirect away from the registered hosts fails closed
CB6  every source registered before this one is unchanged and keeps its place
"""
import email.message
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]

from src.core import RegulatoryRadarCore  # noqa: E402
from src import live_sources  # noqa: E402
from src.live_sources import (  # noqa: E402
    OFFICIAL_SOURCES, SourceFetchError, change_log_path, fetch_official_source,
    load_change_log, select_sources)

FIXTURES = ROOT / "tests" / "fixtures"
BEFORE = (FIXTURES / "eu_cbam_news_2026-11-17.html").read_text(encoding="utf-8")
AFTER = (FIXTURES / "eu_cbam_news_2026-11-18.html").read_text(encoding="utf-8")
CBAM = "eu-cbam-news"
CBAM_URL = ("https://taxation-customs.ec.europa.eu/"
            "carbon-border-adjustment-mechanism/cbam-communication-and-news_en")

# The registry as it stood before the CBAM source was added, in order.
EARLIER_SOURCES = [
    "sec-climate-disclosure-2026",
    "eu-csrd-delegated-acts",
    "eu-esrs-revision-2026",
    "carb-corporate-climate-program",
    "carb-climate-disclosure-rulemaking",
    "carb-climate-disclosure-resources",
]


class FakeResponse:
    def __init__(self, url, body, final_url=None):
        self._url = final_url or url
        self._body = body.encode("utf-8")
        self.status = 200
        self.headers = email.message.Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"

    def geturl(self):
        return self._url

    def read(self, limit=-1):
        return self._body if limit < 0 else self._body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Web:
    """Stands in for urlopen: serves the CBAM page from a fixture and a
    plain official notice for every other source."""

    def __init__(self):
        self.pages = {source.url: (
            "<html><body><main>Official notice. The reporting program "
            "applies to covered entities and the authority has published "
            f"guidance for the first reporting year. {source.source_id}"
            "</main></body></html>") for source in OFFICIAL_SOURCES}
        self.pages[CBAM_URL] = BEFORE
        self.redirect = {}

    def __call__(self, request, timeout=None):
        url = request.full_url
        return FakeResponse(url, self.pages[url], self.redirect.get(url))


@pytest.fixture()
def web(monkeypatch):
    fake = Web()
    monkeypatch.setattr(live_sources, "urlopen", fake)
    return fake


@pytest.fixture()
def radar(tmp_path, web):
    store = tmp_path / "radar" / "snapshots.json"
    core = RegulatoryRadarCore(live_fetch_enabled=True,
                               snapshot_store_path=str(store))
    return core, web, store


def cbam_source():
    return next(source for source in OFFICIAL_SOURCES if source.source_id == CBAM)


def age_last_sweep(store, hours):
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


async def poll(core, **request):
    return await core.process({"action": "watch_changes", **request})


def test_cb1_registry_holds_the_official_cbam_news_page():
    source = cbam_source()
    parsed = urlparse(source.url)
    assert source.url == CBAM_URL
    assert parsed.scheme == "https"
    assert parsed.hostname == "taxation-customs.ec.europa.eu"
    assert parsed.hostname.endswith(".europa.eu")
    assert source.authority == "European Commission"
    assert source.jurisdiction == "eu"
    assert "cbam" in source.topics and "customs" in source.topics


def test_cb2_cbam_topic_selects_only_the_cbam_page():
    assert [s.source_id for s in select_sources("eu", ["cbam"])] == [CBAM]
    assert CBAM in {s.source_id for s in select_sources("global")}
    assert CBAM not in {s.source_id for s in select_sources("us")}
    assert CBAM not in {s.source_id for s in select_sources("california")}


@pytest.mark.asyncio
async def test_cb3_iceland_norway_extension_is_reported_once(radar):
    core, web, store = radar
    first = await poll(core, jurisdiction="eu", topics=["cbam"])
    assert first["status"] == "success" and first["changes"] == []
    assert [w["source_id"] for w in first["sources_watched"]] == [CBAM]
    assert first["sources_not_retrieved_in_last_sweep"] == []

    web.pages[CBAM_URL] = AFTER
    age_last_sweep(store, 30)
    second = await poll(core, jurisdiction="eu", topics=["cbam"],
                        since=first["cursor"])
    assert second["change_count"] == 1
    change = second["changes"][0]
    assert change["source_id"] == CBAM
    assert change["source_url"] == CBAM_URL
    added = " ".join(line for line in change["diff_excerpt"]
                     if line.startswith("+") and not line.startswith("+++"))
    assert "Extension of CBAM to Iceland and Norway" in added
    assert change["previous_sha256"] != change["sha256"]

    # the same change is not logged twice, and the next poll is empty
    age_last_sweep(store, 30)
    third = await poll(core, jurisdiction="eu", topics=["cbam"],
                       since=second["cursor"])
    assert third["changes"] == []
    logged = [r for r in load_change_log(store)
              if r["type"] == "change" and r["source_id"] == CBAM]
    assert len(logged) == 1


@pytest.mark.asyncio
async def test_cb3_a_plain_eu_watch_also_reports_it(radar):
    core, web, store = radar
    first = await poll(core, jurisdiction="eu")
    assert CBAM in {w["source_id"] for w in first["sources_watched"]}
    web.pages[CBAM_URL] = AFTER
    age_last_sweep(store, 30)
    second = await poll(core, jurisdiction="eu", since=first["cursor"])
    assert [c["source_id"] for c in second["changes"]] == [CBAM]


@pytest.mark.asyncio
async def test_cb4_page_chrome_alone_is_not_a_change(radar):
    core, web, store = radar
    first = await poll(core, jurisdiction="eu", topics=["cbam"])
    web.pages[CBAM_URL] = (BEFORE
        .replace("Home Taxation Customs", "Home Taxation Customs Newsroom")
        .replace("Follow us on social media.", "Follow us on Bluesky.")
        .replace('"menu": "Carbon', '"menu": "CBAM Carbon'))
    assert web.pages[CBAM_URL] != BEFORE
    age_last_sweep(store, 30)
    second = await poll(core, jurisdiction="eu", topics=["cbam"],
                        since=first["cursor"])
    assert second["changes"] == []


def test_cb5_redirect_off_the_registered_hosts_fails_closed(web):
    web.redirect[CBAM_URL] = "https://example.com/cbam-news"
    with pytest.raises(SourceFetchError):
        fetch_official_source(cbam_source())


def test_cb6_earlier_sources_are_unchanged_and_in_place():
    ids = [source.source_id for source in OFFICIAL_SOURCES]
    assert ids[:len(EARLIER_SOURCES)] == EARLIER_SOURCES
    assert ids[len(EARLIER_SOURCES):] == [CBAM]
