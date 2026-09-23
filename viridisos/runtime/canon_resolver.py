"""Canon DOI resolver — the root of trust (invariant A-1).

Resolves a theorem DOI to its canon status. A module may only certify if its backing
DOI resolves to a gate-passed canon entry. Reads the live research-pipeline index when
available; falls back to an injectable fixture so the flow is testable offline. The
interface is stable so the fallback swaps to the live index/ledger without code change.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Live index produced by the research pipeline (RESEARCH_PIPELINE_v2/build_canon_index.py).
# Deploys ship a self-contained canon snapshot under viridisos/_canon/ so the agent
# certifies its published theorems even when the research pipeline tree is absent.
def _default_canon_index() -> Path:
    """First existing of: explicit override, live research pipeline, bundled snapshot.

    Priority preserves live-pipeline behavior when the pipeline is checked out beside
    the fleet root (Justin's dev env); falls back to the canon snapshot bundled with
    the agent for self-contained deploys. Invariant A-1 is unchanged: a DOI still only
    certifies if it resolves to a gate-passed record in whichever index is loaded.
    """
    env = os.environ.get("VIRIDISOS_CANON_INDEX")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    candidates = (
        here.parents[2] / "RESEARCH_PIPELINE_v2" / "canon_fingerprint_index.json",
        here.parents[1] / "_canon" / "canon_fingerprint_index.json",
    )
    for c in candidates:
        if c.exists():
            return c
    # Nothing on disk — return the live-pipeline path so behavior/messages are unchanged.
    return candidates[0]


_DEFAULT_INDEX = _default_canon_index()


@dataclass(frozen=True)
class CanonEntry:
    doi: str
    verified: bool          # gate-passed canon entry
    lean_module: str = ""
    name: str = ""


class CanonResolver:
    """Resolve DOIs against the canon. Inject `entries` for tests/offline use."""

    def __init__(self, entries: Optional[dict] = None, index_path: Optional[Path] = None):
        self._entries: dict[str, CanonEntry] = {}
        if entries is not None:
            for doi, e in entries.items():
                self._entries[doi] = CanonEntry(doi=doi, **e) if isinstance(e, dict) else e
        else:
            self._load_index(index_path or _DEFAULT_INDEX)

    def _load_index(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        for rec in data:
            doi = rec.get("doi") or ""
            if not doi:
                continue
            # a record present in the published canon index is, by construction, gate-passed
            self._entries[doi] = CanonEntry(
                doi=doi, verified=True, lean_module=rec.get("id", ""), name=rec.get("name", "")
            )

    def resolve(self, doi: str) -> Optional[CanonEntry]:
        return self._entries.get(doi)

    def is_gate_passed(self, doi: str) -> bool:
        e = self.resolve(doi)
        return bool(e and e.verified)
