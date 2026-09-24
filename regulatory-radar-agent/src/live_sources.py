"""Authoritative-source monitoring for Regulatory Radar.

The source registry is code-owned. Callers cannot supply arbitrary URLs, which
keeps the network boundary auditable and prevents the evidence-pack surface
from becoming an SSRF proxy. Snapshot persistence is optional and journaled.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import unified_diff
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PACK_SCHEMA = "viridis-regulatory-change-evidence-pack-v1"
SNAPSHOT_SCHEMA = "viridis-regulatory-source-snapshots-v1"
JOURNAL_SCHEMA = "viridis-regulatory-source-journal-v1"
NORMALIZER_VERSION = "visible-text-v2"
MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class OfficialSource:
    source_id: str
    title: str
    authority: str
    jurisdiction: str
    topics: tuple[str, ...]
    url: str
    published_on: str | None
    screening_summary: str
    review_focus: str


OFFICIAL_SOURCES: tuple[OfficialSource, ...] = (
    OfficialSource(
        source_id="sec-climate-disclosure-2026",
        title="SEC proposal to rescind climate-related disclosure rules",
        authority="U.S. Securities and Exchange Commission",
        jurisdiction="us",
        topics=("climate", "disclosure", "sec", "reporting"),
        url=(
            "https://www.sec.gov/newsroom/press-releases/"
            "2026-49-sec-proposes-rescission-climate-related-disclosure-rules"
        ),
        published_on="2026-05-29",
        screening_summary=(
            "The SEC proposed rescinding its 2024 climate-disclosure rules. "
            "Existing securities-law materiality obligations and state-level "
            "requirements may still need separate review."
        ),
        review_focus=(
            "Track proposal status and effective dates; separately assess "
            "materiality-based and state disclosure duties."
        ),
    ),
    OfficialSource(
        source_id="eu-csrd-delegated-acts",
        title="Corporate Sustainability Reporting Directive delegated acts",
        authority="European Commission",
        jurisdiction="eu",
        topics=("csrd", "esrs", "disclosure", "reporting"),
        url=(
            "https://finance.ec.europa.eu/regulation-and-supervision/"
            "financial-services-legislation/implementing-and-delegated-acts/"
            "corporate-sustainability-reporting-directive_en"
        ),
        published_on=None,
        screening_summary=(
            "The Commission page centralizes delegated acts under the CSRD. "
            "It is monitored for revised standards, amendments, corrigenda, "
            "and adoption-status changes."
        ),
        review_focus=(
            "Confirm the controlling delegated act, scrutiny status, effective "
            "date, and entity-specific scope before implementation."
        ),
    ),
    OfficialSource(
        source_id="eu-esrs-revision-2026",
        title="European Commission revised sustainability reporting standards",
        authority="European Commission",
        jurisdiction="eu",
        topics=("csrd", "esrs", "disclosure", "reporting"),
        url=(
            "https://finance.ec.europa.eu/news/"
            "commission-adopts-revised-sustainability-reporting-standards-"
            "reduce-administrative-burdens-eu-2026-07-03_en"
        ),
        published_on="2026-07-03",
        screening_summary=(
            "The Commission says it adopted shorter revised ESRS and a "
            "voluntary standard for smaller companies, with mandatory "
            "datapoints reduced by more than 60 percent."
        ),
        review_focus=(
            "Reconfirm CSRD scope, map the current materiality and data "
            "inventory to the revised datapoints, and verify legal timing."
        ),
    ),
    OfficialSource(
        source_id="carb-corporate-climate-program",
        title="California corporate climate reporting program",
        authority="California Air Resources Board",
        jurisdiction="california",
        topics=("sb253", "sb261", "emissions", "climate", "reporting"),
        url=(
            "https://ww2.arb.ca.gov/our-work/programs/"
            "california-corporate-greenhouse-gas-reporting-and-climate-"
            "related-financial-risk"
        ),
        published_on=None,
        screening_summary=(
            "CARB's program page tracks SB 253 and SB 261 implementation, "
            "including rulemaking, fees, reporting milestones, and enforcement "
            "resources."
        ),
        review_focus=(
            "Verify the current effective date and reporting calendar, covered-"
            "entity thresholds, fees, assurance requirements, litigation, and "
            "enforcement posture."
        ),
    ),
    OfficialSource(
        source_id="carb-climate-disclosure-rulemaking",
        title="California corporate climate disclosure initial rulemaking",
        authority="California Air Resources Board",
        jurisdiction="california",
        topics=("sb253", "sb261", "emissions", "climate", "reporting"),
        url=(
            "https://ww2.arb.ca.gov/rulemaking/2025/"
            "california-corporate-greenhouse-gas-reporting-and-climate-"
            "related-financial-risk"
        ),
        published_on=None,
        screening_summary=(
            "CARB's rulemaking page publishes the initial regulation record, "
            "final package, OAL submission status, and controlling materials."
        ),
        review_focus=(
            "Verify OAL determination and effective date, the final regulation "
            "order, first-year reporting deadline, and fee definitions."
        ),
    ),
    OfficialSource(
        source_id="carb-climate-disclosure-resources",
        title="California corporate climate disclosure resources",
        authority="California Air Resources Board",
        jurisdiction="california",
        topics=("sb253", "sb261", "emissions", "climate", "reporting"),
        url=(
            "https://ww2.arb.ca.gov/our-work/programs/"
            "corporate-ghg-reporting/resources"
        ),
        published_on=None,
        screening_summary=(
            "CARB's resources page publishes FAQs, covered-entity lists, "
            "reporting templates, enforcement notices, and docket links."
        ),
        review_focus=(
            "Check the dates and versions of FAQs, entity lists, templates, "
            "enforcement guidance, and the SB 261 docket status."
        ),
    ),
)


_SOURCE_BY_ID = {source.source_id: source for source in OFFICIAL_SOURCES}
_ALLOWED_HOSTS = {
    (urlparse(source.url).hostname or "").lower()
    for source in OFFICIAL_SOURCES
}


class SourceFetchError(RuntimeError):
    """An official source could not be retrieved safely."""


class _VisibleTextParser(HTMLParser):
    _IGNORED = {
        "script", "style", "svg", "noscript", "nav", "header", "footer",
        "aside",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._main_depth = 0
        self.parts: list[str] = []
        self.main_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._IGNORED:
            self._ignored_depth += 1
        if tag.lower() in {"main", "article"}:
            self._main_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._IGNORED and self._ignored_depth:
            self._ignored_depth -= 1
        if tag.lower() in {"main", "article"} and self._main_depth:
            self._main_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)
            if self._main_depth:
                self.main_parts.append(data)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_text(raw: str, content_type: str = "text/html") -> str:
    """Return stable visible text suitable for hashing and line diffs."""
    if "html" in content_type.lower() or "xml" in content_type.lower():
        parser = _VisibleTextParser()
        parser.feed(raw)
        selected = parser.main_parts if parser.main_parts else parser.parts
        raw = "\n".join(selected)
    lines = []
    for line in raw.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _validate_final_url(source: OfficialSource, final_url: str) -> None:
    parsed = urlparse(final_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in _ALLOWED_HOSTS:
        raise SourceFetchError(
            f"unsafe redirect for {source.source_id}: {parsed.scheme}://{host}"
        )


def fetch_official_source(
    source: OfficialSource,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Fetch one registry-owned official source with bounded resources."""
    _validate_final_url(source, source.url)
    request = Request(
        source.url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain",
            "User-Agent": (
                "Viridis-Regulatory-Radar/0.2 "
                "(+https://viridisconservation.com)"
            ),
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            final_url = response.geturl()
            _validate_final_url(source, final_url)
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SourceFetchError(
                    f"source exceeds {MAX_RESPONSE_BYTES} bytes: {source.source_id}"
                )
            text = raw.decode(charset, errors="replace")
            normalized = normalize_text(text, content_type)
            if len(normalized) < 80:
                raise SourceFetchError(
                    f"source returned too little visible text: {source.source_id}"
                )
            return {
                "source_id": source.source_id,
                "title": source.title,
                "authority": source.authority,
                "jurisdiction": source.jurisdiction,
                "topics": list(source.topics),
                "source_url": source.url,
                "final_url": final_url,
                "retrieved_at": _utc_now(),
                "http_status": getattr(response, "status", 200),
                "content_type": content_type,
                "content_bytes": len(raw),
                "normalizer_version": NORMALIZER_VERSION,
                "published_on": source.published_on,
                "screening_summary": source.screening_summary,
                "review_focus": source.review_focus,
                "normalized_text": normalized,
                "sha256": sha256(normalized.encode("utf-8")).hexdigest(),
            }
    except SourceFetchError:
        raise
    except Exception as exc:
        raise SourceFetchError(f"{source.source_id}: {exc}") from exc


def select_sources(
    jurisdiction: str,
    topics: Iterable[str] = (),
    source_ids: Iterable[str] = (),
) -> list[OfficialSource]:
    requested_ids = tuple(source_ids)
    if requested_ids:
        unknown = sorted(set(requested_ids) - _SOURCE_BY_ID.keys())
        if unknown:
            raise ValueError(f"unknown official source ids: {unknown}")
        candidates = [_SOURCE_BY_ID[source_id] for source_id in requested_ids]
    else:
        included = {jurisdiction}
        if jurisdiction in {"us", "california"}:
            included.update({"us", "california"})
        if jurisdiction == "global":
            included.update(source.jurisdiction for source in OFFICIAL_SOURCES)
        candidates = [
            source for source in OFFICIAL_SOURCES
            if source.jurisdiction in included
        ]

    topic_set = {str(topic).strip().lower() for topic in topics if str(topic).strip()}
    if topic_set:
        candidates = [
            source for source in candidates
            if topic_set.intersection(source.topics)
        ]
    return sorted(candidates, key=lambda source: source.source_id)


def _file_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha256(path.read_bytes()).hexdigest()


def load_snapshot_store(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"schema": SNAPSHOT_SCHEMA, "sources": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError("unsupported regulatory source snapshot schema")
    if not isinstance(payload.get("sources"), dict):
        raise ValueError("regulatory source snapshot store has no source map")
    return payload


def save_snapshot_store(path: Path, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Atomically persist snapshots and append a before/after hash journal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    before_sha = _file_sha(path)
    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "updated_at": _utc_now(),
        "sources": {
            snapshot["source_id"]: snapshot
            for snapshot in snapshots
        },
    }
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    after_sha = sha256(encoded).hexdigest()
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    journal_path = path.with_suffix(path.suffix + ".journal.jsonl")
    journal_record = {
        "schema": JOURNAL_SCHEMA,
        "written_at": _utc_now(),
        "path": str(path),
        "before_sha256": before_sha,
        "after_sha256": after_sha,
        "source_count": len(snapshots),
    }
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(journal_record, sort_keys=True) + "\n")
    return journal_record


def _diff_excerpt(previous: str, current: str, word_limit: int = 25) -> list[str]:
    diff = unified_diff(
        previous.splitlines(),
        current.splitlines(),
        fromfile="previous",
        tofile="current",
        lineterm="",
        n=2,
    )
    lines = []
    remaining = word_limit
    for line in diff:
        if line.startswith(("---", "+++", "@@")):
            lines.append(line)
            continue
        words = line[1:].split() if line[:1] in {"+", "-", " "} else line.split()
        if not words:
            lines.append(line)
            continue
        selected = words[:remaining]
        prefix = line[:1] if line[:1] in {"+", "-", " "} else ""
        lines.append(prefix + " ".join(selected))
        remaining -= len(selected)
        if remaining <= 0:
            lines.append("... exact diff excerpt limited to 25 source words ...")
            break
    return lines


def collect_source_evidence(
    sources: list[OfficialSource],
    previous_store: dict[str, Any],
    *,
    fetcher: Callable[[OfficialSource], dict[str, Any]] = fetch_official_source,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch sources and return public evidence, persistable state, and errors."""
    previous_sources = previous_store.get("sources", {})
    evidence: list[dict[str, Any]] = []
    persisted: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for source in sources:
        try:
            snapshot = fetcher(source)
            normalized_text = str(snapshot["normalized_text"])
            previous = previous_sources.get(source.source_id)
            if not previous:
                change_status = "baseline_created"
                diff_excerpt: list[str] = []
            elif previous.get("normalizer_version") != snapshot.get(
                "normalizer_version"
            ):
                change_status = "baseline_reset_normalizer_changed"
                diff_excerpt = []
            elif previous.get("sha256") == snapshot.get("sha256"):
                change_status = "unchanged"
                diff_excerpt = []
            else:
                change_status = "changed"
                diff_excerpt = _diff_excerpt(
                    str(previous.get("normalized_text", "")), normalized_text
                )

            stored_snapshot = dict(snapshot)
            persisted.append(stored_snapshot)
            public_snapshot = {
                key: value for key, value in snapshot.items()
                if key != "normalized_text"
            }
            public_snapshot.update({
                "change_status": change_status,
                "content_excerpt": " ".join(normalized_text.split()[:25]),
                "diff_excerpt": diff_excerpt,
            })
            evidence.append(public_snapshot)
        except Exception as exc:
            errors.append({
                "source_id": source.source_id,
                "source_url": source.url,
                "error_type": type(exc).__name__,
                "message": str(exc),
            })
    return evidence, persisted, errors


def public_source_catalog() -> list[dict[str, Any]]:
    return [asdict(source) for source in OFFICIAL_SOURCES]
