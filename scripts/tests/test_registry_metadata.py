"""RM1-RM6: every registry listing carries an icon, title, website and a
version the hosted gateway reports."""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import registry_metadata as rm  # noqa: E402


def _png_size(path: Path):
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", head[16:24])


def test_rm1_every_listing_is_complete():
    for entry in rm.entries():
        short = entry["short"]
        assert short in rm.SERVERS, short
        icon = rm.LOGOS / rm.logo_file(short)
        assert _png_size(icon) == (400, 400), icon
        if short in rm.HOLD:
            continue
        data = entry["data"]
        assert data["icons"][0]["src"].endswith("/" + icon.name)
        assert 0 < len(data["title"]) <= 100
        assert data["websiteUrl"].endswith(f"/docs/servers/{short}.md")
        assert (ROOT / "docs" / "servers" / f"{short}.md").exists()


def test_rm2_listing_version_is_the_hosted_release():
    for entry in rm.entries():
        if entry["short"] in rm.HOLD:
            continue
        data = entry["data"]
        release = data["_meta"][rm.META_KEY]["viridis"]["release"]
        if entry["short"] in rm.SELF_VERSIONED:                       # RM8
            assert data["version"] == release == rm.agent_release(entry)
            continue
        assert data["version"] == rm.hosted_version(release)
        assert rm._semver(data["version"]) > rm._semver(release)
        assert "+" not in data["version"]          # build metadata does not sort


def test_rm3_descriptions_fit_the_registry():
    for entry in rm.entries():
        if entry["short"] in rm.HOLD:
            continue
        text = entry["data"]["description"]
        assert len(text) <= 100 and text.rstrip().endswith((".", ")")), entry["short"]


def test_rm4_held_entries_have_reasons():
    assert all(reason.strip() for reason in rm.HOLD.values())


def test_rm6_apply_is_idempotent():
    assert rm.apply(write=False) == []
