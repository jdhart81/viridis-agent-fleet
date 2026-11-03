"""DI1-DI4: dataset integrity gates (added 2026-11-03 after live connector tests
in Claude and ChatGPT surfaced a stale persisted dataset).

DI1 Every record has an ISO source_verified_on date.
DI2 No deadline precedes its effective date.
DI3 legal_status is never a bare "binding" for a voluntary or intergovernmental
    framework (TNFD, Kunming-Montreal GBF, Paris Article 6).
DI4 Record ids are unique and free of known typos.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core import RegulatoryDatabase  # noqa: E402

REGS = RegulatoryDatabase().regulations


def test_di1_every_record_has_verified_date():
    for key, r in REGS.items():
        assert isinstance(r.source_verified_on, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.source_verified_on), key
        datetime.strptime(r.source_verified_on, "%Y-%m-%d")


def test_di2_deadline_not_before_effective():
    for key, r in REGS.items():
        if r.reporting_deadline and r.effective_date:
            assert r.reporting_deadline >= r.effective_date, key


def test_di3_frameworks_not_labelled_binding():
    for key, r in REGS.items():
        name = r.name.lower()
        if any(k in name for k in ("tnfd", "kunming", "paris agreement")):
            assert r.legal_status != "binding", key


def test_di4_ids_unique_and_clean():
    ids = [r.id for r in REGS.values()]
    assert len(ids) == len(set(ids))
    assert not any("scop3" in i for i in ids)
