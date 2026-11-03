"""B1 build identity and P1 pricing consistency (2026-11-03).

B1 describe() reports a build block from VIRIDIS_BUILD_SHA, never a guess.
P1 describe() free-call count matches the calculate_inventory tool text and README.
"""
import re
from pathlib import Path

from src.core import build, build_info

ROOT = Path(__file__).resolve().parents[1]


def test_B1_build_info(monkeypatch):
    monkeypatch.delenv("VIRIDIS_BUILD_SHA", raising=False)
    assert build().describe()["build"] == {
        "git_sha": None, "status": "not_set", "source": "env:VIRIDIS_BUILD_SHA"}
    monkeypatch.setenv("VIRIDIS_BUILD_SHA", "7c16107")
    assert build().describe()["build"]["git_sha"] == "7c16107"
    monkeypatch.setenv("VIRIDIS_BUILD_SHA", "not-a-sha")
    assert build_info()["status"] == "invalid" and build_info()["git_sha"] is None


def test_P1_free_calls_consistent():
    free = build().describe()["pricing"]["free_calls_per_day"]
    adapter = (ROOT / "adapters" / "mcp_server.py").read_text()
    readme = (ROOT / "README.md").read_text()
    tool_text = re.search(r"\$1\.00 per call after (\d+) free calls/day", adapter)
    assert tool_text and int(tool_text.group(1)) == free
    assert f"{free} free inventory calculations per UTC day" in readme
