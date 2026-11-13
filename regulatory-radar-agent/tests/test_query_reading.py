"""Q1-Q4: a scan query that matches nothing no longer returns a silent empty result.

Q1 a query whose full phrase matches behaves exactly as before (no extra key).
Q2 a multi-word phrase that matches nothing falls back to regulations that
   contain at least one of its words, and says so in query_read_as.
Q3 if nothing matches at all, the result is still empty but says how many
   regulations apply without the query.
Q4 the fallback never widens jurisdiction or sector.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core import (  # noqa: E402
    Jurisdiction, RegulatoryRadarCore, Sector, _query_words)

LONG = "45V clean energy tax credit emissions disclosure"   # published since July 2026


@pytest.fixture
def agent():
    return RegulatoryRadarCore()


@pytest.mark.asyncio
async def test_q1_matching_phrase_is_unchanged(agent):
    got = await agent.scan_regulations(jurisdiction=Jurisdiction.GLOBAL, query="biodiversity")
    assert got["total_regulations"] > 0 and "query_read_as" not in got
    plain = await agent.scan_regulations(jurisdiction=Jurisdiction.US, sector=Sector.ENERGY)
    assert "query_read_as" not in plain


@pytest.mark.asyncio
async def test_q2_long_published_phrase_now_returns_regulations_and_says_how(agent):
    plain = await agent.scan_regulations(jurisdiction=Jurisdiction.US, sector=Sector.ENERGY)
    got = await agent.scan_regulations(jurisdiction=Jurisdiction.US, sector=Sector.ENERGY,
                                       query=LONG)
    assert got["total_regulations"] > 0
    read = got["query_read_as"]
    assert read["reading"] == "any_word" and read["query"] == LONG
    ids = {r["id"] for r in got["regulations"]}
    assert ids == set(read["words_matched"])
    for words in read["words_matched"].values():
        assert words and set(words) <= set(_query_words(LONG))
    assert ids <= {r["id"] for r in plain["regulations"]}            # Q4
    assert got["total_regulations"] == len(got["regulations"])


@pytest.mark.asyncio
async def test_q3_nothing_matches_says_what_applies_without_the_query(agent):
    plain = await agent.scan_regulations(jurisdiction=Jurisdiction.US)
    for query in ("zzzqqq", "zzzqqq xxxyyy"):
        got = await agent.scan_regulations(jurisdiction=Jurisdiction.US, query=query)
        assert got["total_regulations"] == 0 and got["regulations"] == []
        read = got["query_read_as"]
        assert read["reading"] == "no_match"
        assert read["without_query_total"] == plain["total_regulations"] > 0


@pytest.mark.asyncio
async def test_q2_single_word_never_falls_back_to_itself(agent):
    got = await agent.scan_regulations(jurisdiction=Jurisdiction.US, query="zzzqqq")
    assert got["query_read_as"]["reading"] == "no_match"


@pytest.mark.asyncio
async def test_q4_fallback_stays_inside_jurisdiction_and_sector(agent):
    for jurisdiction in (Jurisdiction.US, Jurisdiction.EU, Jurisdiction.GLOBAL):
        plain = await agent.scan_regulations(jurisdiction=jurisdiction, sector=Sector.ENERGY)
        got = await agent.scan_regulations(jurisdiction=jurisdiction, sector=Sector.ENERGY,
                                           query=LONG)
        assert {r["id"] for r in got["regulations"]} <= {r["id"] for r in plain["regulations"]}
        assert got["included_jurisdictions"] == plain["included_jurisdictions"]


def test_query_words_are_bounded_and_drop_filler():
    assert _query_words(LONG) == ["45v", "clean", "energy", "tax", "credit",
                                  "emissions", "disclosure"]
    assert _query_words("the rules for compliance") == []
    assert _query_words("a b cd") == []
    assert len(_query_words(" ".join(f"word{i}" for i in range(40)))) == 12
