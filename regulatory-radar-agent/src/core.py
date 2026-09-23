"""
RegulatoryRadarCore: Environmental regulation monitoring, compliance scoring, and opportunity detection.

Scans global regulatory landscape, assesses company compliance gaps, and identifies business opportunities
from regulatory changes. Generates TNFD and CSRD reports aligned with international standards.

--- INVARIANTS (spec-invariance contract; one test each in tests/test_invariants.py) ---
G1  process() never raises; a validation failure returns the full error
    envelope {status:"error", error_type, field, value, constraint, message,
    timestamp}.
G2  Unknown action -> error envelope naming the supported actions.
G3  scan requires jurisdiction; a valid scan returns a regulations list with
    total_regulations >= urgent_count >= 0.
G4  A valid assess returns success with a compliance assessment.
G5  describe().name == health().agent; capabilities are non-empty.
G6  health() exposes regulations_in_db >= 0.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from enum import Enum

from .validation import (
    validate_scan_input,
    validate_compliance_assessment_input,
    validate_monitor_changes_input,
    validate_evidence_pack_input,
    ValidationError,
    ValidationWarning,
)
from .live_sources import (
    PACK_SCHEMA,
    collect_source_evidence,
    fetch_official_source,
    load_snapshot_store,
    public_source_catalog,
    save_snapshot_store,
    select_sources,
)

logger = logging.getLogger(__name__)


class Jurisdiction(Enum):
    """Major regulatory jurisdictions."""
    EU = "eu"
    UK = "uk"
    US = "us"
    CALIFORNIA = "california"
    CANADA = "ca"
    AUSTRALIA = "au"
    JAPAN = "jp"
    SINGAPORE = "sg"
    GLOBAL = "global"


class Sector(Enum):
    """Industry sectors with distinct regulatory profiles."""
    AGRICULTURE = "agriculture"
    ENERGY = "energy"
    FORESTRY = "forestry"
    FISHERIES = "fisheries"
    MANUFACTURING = "manufacturing"
    FINANCIAL_SERVICES = "financial_services"
    CONSUMER_GOODS = "consumer_goods"
    TECHNOLOGY = "technology"


class ComplianceLevel(Enum):
    """Compliance status levels."""
    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class Regulation:
    """Single regulatory requirement."""
    id: str
    name: str
    jurisdiction: Jurisdiction
    sector: Optional[Sector]
    effective_date: datetime
    reporting_deadline: Optional[datetime]
    requirements: List[str]
    penalties: str
    standards: List[str]  # e.g., ["TNFD", "CSRD", "EU Taxonomy"]
    description: str
    resource_link: Optional[str] = None
    legal_status: str = "binding"
    date_type: str = "reporting_deadline"
    scope_note: Optional[str] = None
    source_verified_on: Optional[str] = None

    def days_until_deadline(self) -> Optional[int]:
        """Days remaining until the entry's key date."""
        if not self.reporting_deadline:
            return None
        return (self.reporting_deadline - datetime.utcnow()).days

    def deadline_status(self) -> str:
        """Classify the key date without treating past dates as upcoming."""
        days_left = self.days_until_deadline()
        if days_left is None:
            return "not_applicable"
        if days_left < 0:
            return "past"
        if days_left == 0:
            return "due_today"
        return "upcoming"


@dataclass
class ComplianceGap:
    """Single compliance gap for a company."""
    regulation_id: str
    regulation_name: str
    requirement: str
    gap_description: str
    remediation_steps: List[str]
    estimated_effort_hours: int
    deadline_days: int
    risk_level: str  # "critical", "high", "medium", "low"


@dataclass
class RegulatoryOpportunity:
    """Business opportunity from regulatory change."""
    jurisdiction: Jurisdiction
    sector: Sector
    opportunity_type: str  # e.g., "new_mandate", "compliance_gap", "carbon_pricing"
    description: str
    affected_companies_estimated: int
    viridis_fit_score: float  # 0-1: how well Viridis solves this
    market_size_estimate: str  # "$XXM annually"
    timeline_months: int


@dataclass
class ComplianceAssessment:
    """Complete compliance assessment for a company."""
    company_name: str
    jurisdiction: Jurisdiction
    sector: Sector
    assessment_date: datetime
    overall_compliance_level: ComplianceLevel
    compliance_percentage: float  # 0-100
    applicable_regulations: List[Regulation]
    gaps: List[ComplianceGap]
    priority_actions: List[str]
    summary: str


@dataclass
class TNFDReport:
    """TNFD-aligned disclosure report."""
    company_name: str
    report_date: datetime
    governance: Dict[str, str]  # Board oversight, management structure, etc.
    strategy: Dict[str, str]  # Business model, impacts, dependencies
    risk_management: Dict[str, str]  # Identification, assessment, integration
    metrics_targets: Dict[str, str]  # KPIs, science-based targets
    executive_summary: str


@dataclass
class CSRDReport:
    """CSRD-aligned sustainability report."""
    company_name: str
    report_date: datetime
    governance_and_organization: Dict[str, str]
    strategy_and_value_creation: Dict[str, str]
    double_materiality_assessment: Dict[str, List[str]]
    metrics_and_targets: Dict[str, str]
    action_plans: Dict[str, List[str]]
    executive_summary: str


@dataclass
class RegulatoryForecast:
    """Prediction of upcoming regulatory changes."""
    jurisdiction: Jurisdiction
    forecast_period_months: int
    likely_changes: List[Dict[str, str]]
    confidence_level: str  # "high", "medium", "low"
    political_signals: List[str]
    consultation_status: Dict[str, str]  # regulation -> "draft", "public_comment", "finalization"
    recommendation: str


@dataclass
class RegulatorAlertConfig:
    """Configuration for alert generation."""
    jurisdictions: List[Jurisdiction]
    sectors: List[Sector]
    alert_types: List[str] = field(default_factory=lambda: ["new_regulation", "deadline_approaching", "standard_update"])
    days_before_deadline: int = 90


class RegulatoryDatabase:
    """In-memory regulatory knowledge base with key global regulations."""

    def __init__(self):
        """Initialize with major global environmental regulations."""
        self.regulations: Dict[str, Regulation] = self._build_database()

    def _build_database(self) -> Dict[str, Regulation]:
        """
        Build comprehensive regulatory database.

        Delegated to src/data/regulations.py (Night 20, queue #3).
        Dataset updates no longer require touching core logic — edit
        regulatory-radar-agent/src/data/regulations.py instead.
        """
        from .data.regulations import build_regulations
        return build_regulations(Regulation, Jurisdiction, Sector, datetime)

    def get_regulations_by_jurisdiction(self, jurisdiction: Jurisdiction) -> List[Regulation]:
        """Get all regulations applicable to a jurisdiction."""
        included = {jurisdiction, Jurisdiction.GLOBAL}
        if jurisdiction == Jurisdiction.CALIFORNIA:
            included.add(Jurisdiction.US)
        elif jurisdiction == Jurisdiction.US:
            # Preserve the historical national scan, which included the
            # California climate-accountability entries before California
            # became a first-class jurisdiction.
            included.add(Jurisdiction.CALIFORNIA)
        return [
            reg for reg in self.regulations.values()
            if reg.jurisdiction in included
        ]

    @staticmethod
    def included_jurisdictions(jurisdiction: Jurisdiction) -> List[str]:
        """Expose the deterministic jurisdiction hierarchy used by scans."""
        included = {Jurisdiction.GLOBAL, jurisdiction}
        if jurisdiction == Jurisdiction.CALIFORNIA:
            included.add(Jurisdiction.US)
        elif jurisdiction == Jurisdiction.US:
            included.add(Jurisdiction.CALIFORNIA)
        return sorted(item.value for item in included)

    def get_regulations_by_sector(self, sector: Sector) -> List[Regulation]:
        """Get all regulations applicable to a sector."""
        return [
            reg for reg in self.regulations.values()
            if reg.sector is None or reg.sector == sector
        ]

    def get_urgent_regulations(self, days_threshold: int = 180) -> List[Regulation]:
        """Get regulations with approaching deadlines."""
        urgent = []
        for reg in self.regulations.values():
            if reg.reporting_deadline:
                days_left = reg.days_until_deadline()
                if (days_left is not None
                        and 0 <= days_left <= days_threshold):
                    urgent.append(reg)
        return sorted(urgent, key=lambda r: r.reporting_deadline or datetime.max)


class RegulatoryRadarCore:
    """
    Core intelligence engine for regulatory monitoring and compliance assessment.
    """
    KNOWN_ACTIONS = frozenset({
        "scan", "assess", "monitor_changes", "build_evidence_pack",
    })
    READ_ACTIONS = frozenset()

    def __init__(
        self,
        debug: bool = False,
        *,
        live_fetcher=None,
        live_fetch_enabled: Optional[bool] = None,
        snapshot_store_path: Optional[str] = None,
    ):
        """Initialize the regulatory radar with knowledge base."""
        self.config_debug = debug
        self.db = RegulatoryDatabase()
        self.live_fetcher = live_fetcher or fetch_official_source
        self.live_fetch_enabled = (
            live_fetch_enabled
            if live_fetch_enabled is not None
            else os.getenv("REGULATORY_RADAR_LIVE_FETCH_ENABLED", "0") == "1"
        )
        configured_store = (
            snapshot_store_path
            if snapshot_store_path is not None
            else os.getenv("REGULATORY_RADAR_SNAPSHOT_STORE")
        )
        self.snapshot_store_path = (
            Path(configured_store) if configured_store else None
        )
        logger.setLevel(logging.DEBUG if debug else logging.INFO)

    async def process(self, input_data: dict) -> dict:
        """
        Fleet-standard process() router with input validation.

        Actions:
        - "scan": Scan regulations for a jurisdiction/sector
        - "assess": Assess company compliance against applicable regulations

        Input validation is enforced via src.validation before business logic.
        ValidationError → structured error response with field detail.
        """
        if not isinstance(input_data, dict):
            return {
                "status": "error",
                "error_type": "ValidationError",
                "field": "input_data",
                "value": type(input_data).__name__,
                "constraint": "input_data must be a dict",
                "message": (
                    "input_data must be a dict, got "
                    f"{type(input_data).__name__}"
                ),
                "timestamp": datetime.utcnow().isoformat(),
            }

        action = input_data.get("action", "scan")

        try:
            validation_warnings = []

            if action == "scan":
                validated = validate_scan_input(input_data)
                validation_warnings = [
                    str(w) for w in validated.pop("_validation_warnings", [])
                ]
                jurisdiction = Jurisdiction(validated["jurisdiction"])
                sector = Sector(validated["sector"]) if validated.get("sector") else None
                result = await self.scan_regulations(
                    jurisdiction=jurisdiction,
                    sector=sector,
                    query=validated.get("query"),
                )
            elif action == "assess":
                validated = validate_compliance_assessment_input(input_data)
                validation_warnings = [
                    str(w) for w in validated.pop("_validation_warnings", [])
                ]
                jurisdiction = Jurisdiction(validated["jurisdiction"])
                sector = Sector(validated["sector"]) if validated.get("sector") else None
                result = await self.assess_compliance(
                    company_name=validated["company_name"],
                    jurisdiction=jurisdiction,
                    sector=sector,
                    current_practices=input_data.get("current_practices", {}),
                )
            elif action == "monitor_changes":
                validated = validate_monitor_changes_input(input_data)
                validation_warnings = [
                    str(w) for w in validated.pop("_validation_warnings", [])
                ]
                jurisdiction = Jurisdiction(validated["jurisdiction"])
                result = await self.monitor_changes(
                    jurisdiction=jurisdiction,
                    topics=validated["topics"],
                    active_projects=validated["active_projects"],
                    lookback_days=validated["lookback_days"],
                )
            elif action == "build_evidence_pack":
                validated = validate_evidence_pack_input(input_data)
                validation_warnings = [
                    str(w) for w in validated.pop("_validation_warnings", [])
                ]
                jurisdiction = Jurisdiction(validated["jurisdiction"])
                result = await self.build_evidence_pack(
                    jurisdiction=jurisdiction,
                    topics=validated["topics"],
                    active_projects=validated["active_projects"],
                    lookback_days=validated["lookback_days"],
                    company_profile=validated["company_profile"],
                    source_ids=validated["source_ids"],
                    persist_snapshot=validated["persist_snapshot"],
                )
            else:
                return {
                    "status": "error",
                    "message": (
                        f"Unknown action: {action}. "
                        "Supported: scan, assess, monitor_changes, "
                        "build_evidence_pack"
                    ),
                    "timestamp": datetime.utcnow().isoformat(),
                }

            # Normalize result to dict
            if hasattr(result, '__dict__') and not isinstance(result, dict):
                result = {"result": str(result)}
            elif not isinstance(result, dict):
                result = {"result": result}

            if validation_warnings:
                result["validation_warnings"] = validation_warnings
            result["status"] = result.get("status", "success")
            result["timestamp"] = datetime.utcnow().isoformat()
            return result

        except ValidationError as ve:
            logger.warning(f"RegulatoryRadar validation rejected: {ve}")
            return {
                "status": "error",
                "error_type": "ValidationError",
                "field": ve.field,
                "value": str(ve.value),
                "constraint": ve.constraint,
                "message": str(ve),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"RegulatoryRadar process error: {e}", exc_info=True)
            return {
                "status": "error",
                "error_type": "InternalError",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def health(self) -> dict:
        """Health check — fleet standard interface."""
        return {
            "status": "ok",
            "agent": "regulatory-radar-agent",
            "timestamp": datetime.utcnow().isoformat(),
            "capabilities": [
                "scan_regulations",
                "assess_compliance",
                "monitor_changes",
                "build_evidence_pack",
            ],
            "live_source_monitoring": {
                "enabled": self.live_fetch_enabled,
                "official_source_count": len(public_source_catalog()),
                "snapshot_store_configured": self.snapshot_store_path is not None,
            },
        }

    def describe(self) -> dict:
        """Describe agent capabilities — fleet standard interface."""
        return {
            "name": "regulatory-radar-agent",
            "description": "Environmental regulation monitoring, compliance scoring, and opportunity detection.",
            "pillar": "infrastructure",
            "capabilities": [
                "regulatory_scan",
                "compliance_assessment",
                "change_monitoring",
                "authoritative_source_evidence_pack",
                "tnfd_csrd_reporting",
            ],
            "inputs": [
                "jurisdiction", "sector", "company_name", "current_practices",
                "topics", "active_projects", "lookback_days",
            ],
            "outputs": [
                "regulations", "compliance_score", "gaps", "recommendations",
                "changes", "alert_level",
                "source_snapshots", "source_hashes", "change_diffs",
                "delivery_receipt",
            ],
        }

    async def scan_regulations(
        self,
        jurisdiction: Jurisdiction,
        sector: Optional[Sector] = None,
        query: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Scan regulations applicable to jurisdiction and sector.

        Args:
            jurisdiction: Target jurisdiction (EU, US, UK, etc.)
            sector: Optional industry sector filter
            query: Optional text search filter

        Returns:
            Dictionary with applicable regulations and summary
        """
        try:
            # Get base regulations for jurisdiction
            regs = self.db.get_regulations_by_jurisdiction(jurisdiction)

            # Filter by sector if provided
            if sector:
                regs = [r for r in regs if r.sector is None or r.sector == sector]

            # Filter by text query if provided
            if query:
                query_lower = query.lower()
                regs = [
                    r for r in regs
                    if query_lower in r.name.lower()
                    or query_lower in r.description.lower()
                    or any(query_lower in req.lower() for req in r.requirements)
                ]

            urgent = []
            overdue = []
            for reg in regs:
                days_left = reg.days_until_deadline()
                if days_left is not None and 0 <= days_left <= 180:
                    urgent.append(reg)
                elif days_left is not None and days_left < 0:
                    overdue.append(reg)

            result = {
                "jurisdiction": jurisdiction.value,
                "included_jurisdictions":
                    self.db.included_jurisdictions(jurisdiction),
                "sector": sector.value if sector else None,
                "total_regulations": len(regs),
                "urgent_count": len(urgent),
                "past_key_date_count": len(overdue),
                "regulations": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "jurisdiction": r.jurisdiction.value,
                        "effective_date": r.effective_date.isoformat(),
                        "deadline": r.reporting_deadline.isoformat() if r.reporting_deadline else None,
                        "days_until_deadline": r.days_until_deadline(),
                        "deadline_status": r.deadline_status(),
                        "date_type": r.date_type,
                        "legal_status": r.legal_status,
                        "standards": r.standards,
                        "requirements_count": len(r.requirements),
                        "source_url": r.resource_link,
                        "source_verified_on": r.source_verified_on,
                        "scope_note": r.scope_note,
                    }
                    for r in sorted(regs, key=lambda x: x.reporting_deadline or datetime.max)
                ],
                "scan_timestamp": datetime.utcnow().isoformat(),
                "disclaimer": (
                    "Technology-assisted screening only; confirm applicability "
                    "and deadlines with the cited authority or qualified counsel."
                ),
            }

            logger.info(f"Scanned {len(regs)} regulations for {jurisdiction.value}")
            return result

        except Exception as e:
            logger.error(f"Error scanning regulations: {str(e)}")
            raise

    async def assess_compliance(
        self,
        company_name: str,
        jurisdiction: Jurisdiction,
        sector: Sector,
        current_practices: Dict[str, bool],
    ) -> ComplianceAssessment:
        """
        Assess company's compliance against applicable regulations.

        Args:
            company_name: Company identifier
            jurisdiction: Where company operates
            sector: Industry sector
            current_practices: Dict of {"practice_name": bool} for current implementations

        Returns:
            ComplianceAssessment with gaps and recommendations
        """
        try:
            applicable_regs = self.db.get_regulations_by_jurisdiction(jurisdiction)
            applicable_regs = [r for r in applicable_regs if r.sector is None or r.sector == sector]

            gaps: List[ComplianceGap] = []
            compliant_count = 0

            for reg in applicable_regs:
                # Simple compliance check: map requirements to practices
                reg_compliant = all(
                    current_practices.get(req.lower().replace(" ", "_"), False)
                    for req in reg.requirements
                )

                if not reg_compliant:
                    missing_reqs = [
                        req for req in reg.requirements
                        if not current_practices.get(req.lower().replace(" ", "_"), False)
                    ]

                    gap = ComplianceGap(
                        regulation_id=reg.id,
                        regulation_name=reg.name,
                        requirement=" | ".join(missing_reqs[:2]),
                        gap_description=f"Missing {len(missing_reqs)} of {len(reg.requirements)} requirements",
                        remediation_steps=[
                            f"Implement {req}" for req in missing_reqs[:3]
                        ],
                        estimated_effort_hours=40 * len(missing_reqs),
                        deadline_days=max(1, reg.days_until_deadline() or 365),
                        risk_level="critical" if reg.days_until_deadline() and reg.days_until_deadline() < 90
                        else "high" if reg.days_until_deadline() and reg.days_until_deadline() < 180
                        else "medium",
                    )
                    gaps.append(gap)
                else:
                    compliant_count += 1

            compliance_percentage = (compliant_count / len(applicable_regs) * 100) if applicable_regs else 0

            overall_level = (
                ComplianceLevel.COMPLIANT if compliance_percentage >= 90
                else ComplianceLevel.PARTIAL if compliance_percentage >= 50
                else ComplianceLevel.NON_COMPLIANT
            )

            priority_actions = [
                f"[CRITICAL] {g.regulation_name}: Due in {g.deadline_days} days"
                for g in sorted(gaps, key=lambda x: x.deadline_days)[:3]
            ]

            assessment = ComplianceAssessment(
                company_name=company_name,
                jurisdiction=jurisdiction,
                sector=sector,
                assessment_date=datetime.utcnow(),
                overall_compliance_level=overall_level,
                compliance_percentage=round(compliance_percentage, 1),
                applicable_regulations=applicable_regs,
                gaps=gaps,
                priority_actions=priority_actions,
                summary=f"{company_name} is {overall_level.value} with environmental regulations. "
                        f"{len(gaps)} compliance gaps identified, estimated {sum(g.estimated_effort_hours for g in gaps)} hours to remediate."
            )

            logger.info(f"Compliance assessment for {company_name}: {compliance_percentage:.1f}%")
            return assessment

        except Exception as e:
            logger.error(f"Error assessing compliance: {str(e)}")
            raise

    async def monitor_changes(
        self,
        jurisdiction: Jurisdiction,
        topics: Optional[List[str]] = None,
        active_projects: Optional[List] = None,
        lookback_days: int = 30,
    ) -> Dict[str, any]:
        """
        Monitor dated regulatory changes — MISSION.md §3 value function #3.

        Surfaces recently effective requirements plus effective dates and
        reporting deadlines approaching or recently passed within the same
        bounded window. This is a deterministic watch over the curated
        database, not a claim of a live external regulatory feed.

        Composes regulatory_forecast() (forward-looking signal) with
        urgent-deadline scan from RegulatoryDatabase (backward-looking
        baseline of recently effective regs).

        Args:
            jurisdiction: Target jurisdiction
            topics: Optional topic filters (informational; future enrichment)
            active_projects: Optional list of project ids/dicts to flag against
            lookback_days: Symmetric day window [1, 365]: recently effective
                dates and deadlines behind now, and key dates ahead of now.

        Returns:
            Dict with:
              - changes: list of detected changes (type, summary, deadline,
                impact_on_projects, action_required)
              - alert_level: aggregated severity
              - recommended_actions: prioritized actions
              - jurisdiction, lookback_days, monitored_topics, project_count
        """
        try:
            now = datetime.utcnow()
            window_start = now - timedelta(days=lookback_days)
            window_end = now + timedelta(days=lookback_days)

            # Get all regulations for jurisdiction (incl. GLOBAL)
            regs = self.db.get_regulations_by_jurisdiction(jurisdiction)

            # Topic filter (substring match against name/description/standards)
            if topics:
                topics_lower = [t.lower() for t in topics]
                topics_compact = [
                    re.sub(r"[^a-z0-9]+", "", topic)
                    for topic in topics_lower
                ]
                def _topic_match(r: Regulation) -> bool:
                    blob = " ".join([
                        r.name.lower(),
                        r.description.lower(),
                        " ".join(s.lower() for s in r.standards),
                    ])
                    blob_compact = re.sub(r"[^a-z0-9]+", "", blob)
                    return any(
                        topic in blob or compact in blob_compact
                        for topic, compact in zip(
                            topics_lower, topics_compact
                        )
                    )
                regs = [r for r in regs if _topic_match(r)]

            # Project IDs for impact tagging
            project_ids: List[str] = []
            if active_projects:
                for p in active_projects:
                    if isinstance(p, dict):
                        pid = p.get("project_id") or p.get("id")
                        if pid:
                            project_ids.append(str(pid))
                    else:
                        project_ids.append(str(p))

            changes: List[Dict[str, any]] = []

            for reg in regs:
                days_to_deadline = reg.days_until_deadline()
                days_to_effective = (reg.effective_date - now).days
                effective_recently = (
                    window_start <= reg.effective_date <= now)
                effective_upcoming = (
                    now < reg.effective_date <= window_end)
                deadline_upcoming = (
                    days_to_deadline is not None
                    and 0 <= days_to_deadline <= lookback_days)
                deadline_recently_passed = (
                    days_to_deadline is not None
                    and -lookback_days <= days_to_deadline < 0)

                if not (effective_recently
                        or effective_upcoming
                        or deadline_upcoming
                        or deadline_recently_passed):
                    continue

                legal_status = str(reg.legal_status or "").lower()
                if deadline_upcoming:
                    change_type = "deadline_approaching"
                elif deadline_recently_passed:
                    change_type = "deadline_recently_passed"
                elif effective_recently:
                    change_type = "new_regulation"
                elif any(token in legal_status for token in (
                        "proposed", "draft", "consultation")):
                    change_type = "proposed_rule"
                else:
                    change_type = "effective_date_approaching"

                urgency_candidates = [
                    days for days in (days_to_deadline, days_to_effective)
                    if days is not None and days >= 0
                ]
                urgency_days = (
                    min(urgency_candidates) if urgency_candidates else None)
                overdue_days = (
                    abs(days_to_deadline)
                    if deadline_recently_passed else None
                )
                if deadline_recently_passed:
                    urgency_days = 0
                action_required = (
                    urgency_days is not None
                    and urgency_days <= 90
                ) or change_type in {
                    "new_regulation", "deadline_recently_passed",
                }

                # Per-change alert_level — mirrors aggregate severity bands so
                # downstream consumers (Carbon-Bridge, Proof-of-Conservation)
                # can route each change without re-deriving urgency. Invariant:
                # max(per-change alert_level) == aggregate alert_level when
                # `changes` is non-empty. Nightkeeper 2026-04-21 (queue #5).
                if urgency_days is not None and urgency_days <= 30:
                    change_alert_level = "critical"
                elif urgency_days is not None and urgency_days <= 90:
                    change_alert_level = "high"
                else:
                    change_alert_level = "medium"

                changes.append({
                    "type": change_type,
                    "regulation_id": reg.id,
                    "regulation_name": reg.name,
                    "effective_date": reg.effective_date.isoformat(),
                    "days_until_effective": days_to_effective,
                    "deadline": reg.reporting_deadline.isoformat() if reg.reporting_deadline else None,
                    "days_until_deadline": days_to_deadline,
                    "overdue_days": overdue_days,
                    "urgency_days": urgency_days,
                    "summary": reg.description,
                    "standards": reg.standards,
                    "legal_status": reg.legal_status,
                    "date_type": reg.date_type,
                    "source_url": reg.resource_link,
                    "source_verified_on": reg.source_verified_on,
                    "scope_note": reg.scope_note,
                    "impact_on_projects": list(project_ids),
                    "action_required": action_required,
                    "alert_level": change_alert_level,
                })

            # Aggregate alert level from urgency
            critical = sum(
                1 for c in changes
                if c.get("urgency_days") is not None
                and c["urgency_days"] <= 30
            )
            high = sum(
                1 for c in changes
                if c.get("urgency_days") is not None
                and 30 < c["urgency_days"] <= 90
            )
            if critical > 0:
                alert_level = "critical"
            elif high > 0:
                alert_level = "high"
            elif changes:
                alert_level = "medium"
            else:
                alert_level = "low"

            recommended_actions: List[str] = []
            for c in sorted(
                changes,
                key=lambda x: (
                    x.get("urgency_days")
                    if x.get("urgency_days") is not None else 9_999),
            )[:5]:
                if c["action_required"]:
                    if c["type"] == "deadline_recently_passed":
                        timing = f"{c['overdue_days']}d past key date"
                    else:
                        timing = f"{c.get('urgency_days', '∞')}d to next key date"
                    recommended_actions.append(
                        f"[{c['type'].upper()}] {c['regulation_name']}: "
                        f"{timing} — "
                        "review applicability and compliance gap"
                    )

            result = {
                "jurisdiction": jurisdiction.value,
                "lookback_days": lookback_days,
                "monitored_topics": topics or [],
                "project_count": len(project_ids),
                "change_count": len(changes),
                "alert_level": alert_level,
                "changes": sorted(
                    changes,
                    key=lambda x: (
                        x.get("urgency_days")
                        if x.get("urgency_days") is not None else 9_999),
                ),
                "recommended_actions": recommended_actions,
                "monitored_at": now.isoformat(),
            }

            logger.info(
                f"monitor_changes: {len(changes)} changes for {jurisdiction.value} "
                f"(lookback={lookback_days}d, alert={alert_level})"
            )
            return result

        except Exception as e:
            logger.error(f"Error in monitor_changes: {e}")
            raise

    async def build_evidence_pack(
        self,
        jurisdiction: Jurisdiction,
        topics: Optional[List[str]] = None,
        active_projects: Optional[List] = None,
        lookback_days: int = 90,
        company_profile: Optional[Dict] = None,
        source_ids: Optional[List[str]] = None,
        persist_snapshot: bool = True,
    ) -> Dict[str, any]:
        """Build a source-hashed regulatory change evidence pack.

        This is the live product boundary. It fetches only registry-owned
        official URLs, compares their normalized contents with a journaled
        prior snapshot when configured, and combines that evidence with the
        curated deadline calendar. A first observation is always labelled a
        baseline, never a detected change.
        """
        if not self.live_fetch_enabled:
            return {
                "status": "error",
                "error_type": "PermissionError",
                "message": (
                    "live official-source retrieval is disabled; set "
                    "REGULATORY_RADAR_LIVE_FETCH_ENABLED=1 on an authorized "
                    "runtime"
                ),
                "live_source_status": "disabled",
            }

        try:
            sources = select_sources(
                jurisdiction.value,
                topics or [],
                source_ids or [],
            )
        except ValueError as exc:
            return {
                "status": "error",
                "error_type": "ValidationError",
                "field": "source_ids",
                "message": str(exc),
            }
        if not sources:
            return {
                "status": "error",
                "error_type": "ValidationError",
                "field": "topics",
                "message": (
                    "no registry-owned official sources match this "
                    "jurisdiction and topic selection"
                ),
            }

        try:
            previous_store = load_snapshot_store(self.snapshot_store_path)
        except Exception as exc:
            return {
                "status": "error",
                "error_type": "ContextError",
                "message": f"cannot read the source snapshot store: {exc}",
            }

        evidence, persistable, source_errors = await asyncio.to_thread(
            collect_source_evidence,
            sources,
            previous_store,
            fetcher=self.live_fetcher,
        )
        if not evidence:
            return {
                "status": "error",
                "error_type": "BackendError",
                "message": "no authoritative source could be retrieved",
                "live_source_status": "failed",
                "source_errors": source_errors,
            }

        persistence = {
            "requested": persist_snapshot,
            "status": "not_requested",
        }
        if persist_snapshot:
            if self.snapshot_store_path is None:
                persistence["status"] = "disabled_not_configured"
            else:
                previous_sources = dict(previous_store.get("sources", {}))
                previous_sources.update({
                    snapshot["source_id"]: snapshot
                    for snapshot in persistable
                })
                journal_record = await asyncio.to_thread(
                    save_snapshot_store,
                    self.snapshot_store_path,
                    list(previous_sources.values()),
                )
                persistence.update({
                    "status": "persisted",
                    "snapshot_store": str(self.snapshot_store_path),
                    "journal": journal_record,
                })

        curated = await self.monitor_changes(
            jurisdiction=jurisdiction,
            topics=topics,
            active_projects=active_projects,
            lookback_days=lookback_days,
        )
        company_profile = company_profile or {}
        changed = [
            item for item in evidence if item["change_status"] == "changed"
        ]
        baselines = [
            item for item in evidence
            if item["change_status"].startswith("baseline_")
        ]
        unchanged = [
            item for item in evidence
            if item["change_status"] == "unchanged"
        ]

        recommended_actions: List[str] = []
        for item in changed:
            recommended_actions.append(
                f"Review the detected text change at {item['authority']} "
                f"and assess entity-specific applicability."
            )
        recommended_actions.extend(curated.get("recommended_actions", []))
        if baselines and not changed:
            recommended_actions.append(
                "Retain this signed baseline; the next observation can prove "
                "whether official source text changed."
            )

        generated_at = datetime.utcnow().isoformat() + "Z"
        live_status = "complete" if not source_errors else "partial"
        pack = {
            "schema": PACK_SCHEMA,
            "status": "success",
            "generated_at": generated_at,
            "jurisdiction": jurisdiction.value,
            "topics": topics or [],
            "company_profile": company_profile,
            "applicability_posture": {
                "status": "screening_only",
                "company_specific_determination": False,
                "profile_fields_supplied": sorted(company_profile),
                "notice": (
                    "Technology-assisted regulatory screening, not legal "
                    "advice. Confirm applicability and deadlines with the "
                    "cited authority or qualified counsel."
                ),
            },
            "live_source_monitoring": {
                "status": live_status,
                "selected_source_count": len(sources),
                "retrieved_source_count": len(evidence),
                "changed_count": len(changed),
                "baseline_count": len(baselines),
                "unchanged_count": len(unchanged),
                "failed_count": len(source_errors),
                "sources": evidence,
                "source_errors": source_errors,
                "persistence": persistence,
            },
            "curated_deadline_calendar": curated,
            "recommended_actions": recommended_actions[:10],
        }
        canonical = json.dumps(
            pack, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        pack_hash = hashlib.sha256(canonical).hexdigest()
        pack["delivery_receipt"] = {
            "receipt_version": "durable_delivery_receipt_v1",
            "pack_sha256": pack_hash,
            "source_hashes": {
                item["source_id"]: item["sha256"] for item in evidence
            },
            "delivered": False,
            "buyer_acknowledged_useful": None,
            "would_buy_again": None,
        }
        return pack

    async def detect_opportunities(
        self,
        jurisdiction: Jurisdiction,
        sector: Sector,
    ) -> List[RegulatoryOpportunity]:
        """
        Identify business opportunities from regulatory changes.

        Args:
            jurisdiction: Target jurisdiction
            sector: Target industry sector

        Returns:
            List of RegulatoryOpportunity objects
        """
        try:
            applicable_regs = self.db.get_regulations_by_jurisdiction(jurisdiction)
            applicable_regs = [r for r in applicable_regs if r.sector is None or r.sector == sector]

            opportunities: List[RegulatoryOpportunity] = []

            for reg in applicable_regs:
                # Assess Viridis fit based on regulation type
                viridis_fit = 0.0
                if any(std in reg.standards for std in ["TNFD", "CSRD", "EU Taxonomy"]):
                    viridis_fit = 0.85  # High fit for biodiversity/sustainability reporting
                elif "carbon" in reg.name.lower() or "Article 6" in reg.name:
                    viridis_fit = 0.75  # High fit for carbon markets
                elif "biodiversity" in reg.name.lower() or "bng" in reg.id.lower():
                    viridis_fit = 0.9  # Excellent fit for biodiversity verification

                if viridis_fit > 0.6:
                    opp_type = "compliance_gap" if viridis_fit > 0.8 else "carbon_pricing"
                    estimated_companies = {"EU": 50000, "UK": 15000, "US": 100000, "GLOBAL": 500000}.get(
                        jurisdiction.value.upper(), 10000
                    )

                    opportunity = RegulatoryOpportunity(
                        jurisdiction=jurisdiction,
                        sector=sector,
                        opportunity_type=opp_type,
                        description=f"{reg.name} creates demand for {opp_type.replace('_', ' ')} solutions",
                        affected_companies_estimated=estimated_companies,
                        viridis_fit_score=viridis_fit,
                        market_size_estimate=f"${int(estimated_companies * 0.05)}M annually",
                        timeline_months=max(1, (reg.days_until_deadline() or 365) // 30),
                    )
                    opportunities.append(opportunity)

            logger.info(f"Identified {len(opportunities)} opportunities in {jurisdiction.value}/{sector.value}")
            return sorted(opportunities, key=lambda x: x.viridis_fit_score, reverse=True)

        except Exception as e:
            logger.error(f"Error detecting opportunities: {str(e)}")
            raise

    async def generate_tnfd_report(
        self,
        company_name: str,
        governance_data: Dict[str, str],
        strategy_data: Dict[str, str],
        risk_data: Dict[str, str],
        biodiversity_score: float,
    ) -> TNFDReport:
        """
        Generate TNFD-aligned disclosure report.

        Args:
            company_name: Company identifier
            governance_data: Board, committees, management structure
            strategy_data: Business model, impacts, dependencies
            risk_data: Identified risks, assessments
            biodiversity_score: Current biodiversity impact score (0-1)

        Returns:
            TNFDReport object
        """
        try:
            report = TNFDReport(
                company_name=company_name,
                report_date=datetime.utcnow(),
                governance=governance_data or {
                    "board_oversight": "Board-level sustainability committee established",
                    "management_structure": "Chief Sustainability Officer role created",
                    "accountability": "ESG metrics tied to executive compensation",
                },
                strategy=strategy_data or {
                    "business_model": "Integrated nature-positive practices into core operations",
                    "nature_dependencies": "Assessed supply chain biodiversity risks",
                    "time_horizons": "Short (0-2y), Medium (2-5y), Long-term (5-10y)",
                },
                risk_management=risk_data or {
                    "identification": "Nature-related risk assessment completed",
                    "assessment": "PESTLE analysis of regulatory, market, operational risks",
                    "integration": "Risks integrated into enterprise risk management",
                },
                metrics_targets={
                    "current_biodiversity_score": f"{biodiversity_score:.2f}/1.0",
                    "2030_target": "Increase by 30%",
                    "2050_target": "Nature-positive (>1.0)",
                    "key_indicators": "Species presence, ecosystem health, habitat extent",
                },
                executive_summary=(
                    f"{company_name} has assessed nature-related risks and opportunities across "
                    f"operations and value chain. Current biodiversity score: {biodiversity_score:.2f}/1.0. "
                    f"Strategic priorities: governance strengthening, supply chain resilience, "
                    f"science-based targets aligned with Kunming-Montreal GBF."
                )
            )

            logger.info(f"Generated TNFD report for {company_name}")
            return report

        except Exception as e:
            logger.error(f"Error generating TNFD report: {str(e)}")
            raise

    async def generate_csrd_report(
        self,
        company_name: str,
        environmental_data: Dict[str, str],
        governance_data: Dict[str, str],
        materiality_impacts: List[str],
        materiality_financial: List[str],
    ) -> CSRDReport:
        """
        Generate CSRD-aligned sustainability report.

        Args:
            company_name: Company identifier
            environmental_data: GHG, water, waste metrics
            governance_data: Board structure, ethics, compliance
            materiality_impacts: Material sustainability impacts
            materiality_financial: Financially material sustainability factors

        Returns:
            CSRDReport object
        """
        try:
            report = CSRDReport(
                company_name=company_name,
                report_date=datetime.utcnow(),
                governance_and_organization=governance_data or {
                    "board_composition": "Board includes sustainability expertise",
                    "ethics_and_compliance": "Code of conduct, whistleblower policy",
                    "stakeholder_engagement": "Regular stakeholder consultation process",
                },
                strategy_and_value_creation={
                    "business_model": "Value creation aligned with sustainability",
                    "opportunities": "Transition to sustainable practices creates competitive advantage",
                    "risks": "Climate, regulatory, market transition risks assessed",
                },
                double_materiality_assessment={
                    "impact_materiality": materiality_impacts or ["GHG emissions", "Biodiversity", "Water use"],
                    "financial_materiality": materiality_financial or ["Climate risk", "Transition costs", "Regulatory"],
                },
                metrics_and_targets=environmental_data or {
                    "scope_1_2_emissions": "Baseline established, 50% reduction target by 2030",
                    "biodiversity_metric": "Land use impact assessed, positive targets set",
                    "water_consumption": "Efficiency improvements, circular economy targets",
                },
                action_plans={
                    "climate_transition": ["Renewable energy transition", "Supply chain decarbonization"],
                    "biodiversity": ["Ecosystem restoration", "Sustainable sourcing"],
                    "governance": ["Enhanced reporting", "Stakeholder accountability"],
                },
                executive_summary=(
                    f"{company_name} has completed double materiality assessment identifying "
                    f"{len(materiality_impacts)} impact-material and {len(materiality_financial)} "
                    f"financial-material sustainability factors. CSRD compliance roadmap: "
                    f"Assurance year 1, full ESRS reporting year 2, continuous improvement framework."
                )
            )

            logger.info(f"Generated CSRD report for {company_name}")
            return report

        except Exception as e:
            logger.error(f"Error generating CSRD report: {str(e)}")
            raise

    async def regulatory_forecast(
        self,
        jurisdiction: Jurisdiction,
        forecast_months: int = 12,
    ) -> RegulatoryForecast:
        """
        Forecast upcoming regulatory changes.

        Args:
            jurisdiction: Target jurisdiction
            forecast_months: Forecast period in months

        Returns:
            RegulatoryForecast with predictions and signals
        """
        try:
            urgent_regs = self.db.get_urgent_regulations(days_threshold=forecast_months * 30)

            likely_changes = [
                {
                    "regulation": reg.name,
                    "expected_finalization": (reg.reporting_deadline or datetime.utcnow() + timedelta(days=180)).isoformat(),
                    "impact": f"Affects {reg.requirements[0] if reg.requirements else 'sustainability reporting'}"
                }
                for reg in urgent_regs[:5]
            ]

            political_signals = [
                "Global momentum toward nature-based solutions (Kunming-Montreal GBF adoption)",
                "EU regulatory expansion (CSRD broadening to more sectors)",
                "US climate focus despite political variations",
                "Article 6 carbon market activation (international cooperation)",
            ]

            forecast = RegulatoryForecast(
                jurisdiction=jurisdiction,
                forecast_period_months=forecast_months,
                likely_changes=likely_changes,
                confidence_level="high" if len(likely_changes) > 0 else "medium",
                political_signals=political_signals,
                consultation_status={
                    "tnfd_adoption": "active_implementation",
                    "csrd_expansion": "finalization_phase",
                    "article_6_markets": "operational_phase",
                },
                recommendation=(
                    "Prioritize TNFD and CSRD compliance: largest market impact. "
                    "Evaluate Article 6 carbon market participation for revenue generation. "
                    "Monitor national biodiversity strategies for sector-specific requirements."
                )
            )

            logger.info(f"Generated forecast for {jurisdiction.value}")
            return forecast

        except Exception as e:
            logger.error(f"Error generating forecast: {str(e)}")
            raise

    async def generate_alerts(
        self,
        watchlist: List[Tuple[Jurisdiction, Sector]],
        alert_config: Optional[RegulatorAlertConfig] = None,
    ) -> Dict[str, any]:
        """
        Generate regulatory alerts for watchlisted jurisdictions/sectors.

        Args:
            watchlist: List of (jurisdiction, sector) tuples to monitor
            alert_config: Alert configuration

        Returns:
            Dictionary with generated alerts
        """
        try:
            config = alert_config or RegulatorAlertConfig(
                jurisdictions=[Jurisdiction.EU, Jurisdiction.US],
                sectors=[Sector.FORESTRY, Sector.AGRICULTURE],
            )

            alerts = []

            for jurisdiction, sector in watchlist:
                regs = self.db.get_regulations_by_jurisdiction(jurisdiction)
                regs = [r for r in regs if r.sector is None or r.sector == sector]

                for reg in regs:
                    days_left = reg.days_until_deadline()
                    if (days_left is not None
                            and 0 <= days_left <= config.days_before_deadline):
                        alerts.append({
                            "type": "deadline_approaching",
                            "jurisdiction": jurisdiction.value,
                            "sector": sector.value,
                            "regulation": reg.name,
                            "days_remaining": days_left,
                            "severity": "critical" if days_left < 30 else "high" if days_left < 90 else "medium",
                            "action": f"Begin {reg.name} compliance implementation immediately"
                        })

                    if "new" in reg.name.lower() or reg.effective_date > datetime.utcnow() - timedelta(days=90):
                        alerts.append({
                            "type": "new_regulation",
                            "jurisdiction": jurisdiction.value,
                            "sector": sector.value,
                            "regulation": reg.name,
                            "effective_date": reg.effective_date.isoformat(),
                            "severity": "high",
                            "action": f"Review {reg.name} requirements and impact assessment"
                        })

            result = {
                "alert_count": len(alerts),
                "critical_count": sum(1 for a in alerts if a.get("severity") == "critical"),
                "high_count": sum(1 for a in alerts if a.get("severity") == "high"),
                "alerts": sorted(alerts, key=lambda x: x.get("days_remaining", 999))[:10],
                "generated_timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(f"Generated {len(alerts)} alerts")
            return result

        except Exception as e:
            logger.error(f"Error generating alerts: {str(e)}")
            raise

    async def health(self) -> Dict[str, any]:
        """Health check endpoint."""
        return {
            "status": "ok",
            "agent": "regulatory-radar",
            "version": "0.2.0",
            "regulations_in_db": len(self.db.regulations),
            "live_source_monitoring": {
                "enabled": self.live_fetch_enabled,
                "official_source_count": len(public_source_catalog()),
                "snapshot_store_configured": self.snapshot_store_path is not None,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    def describe(self) -> Dict[str, any]:
        """Describe agent capabilities."""
        return {
            "name": "regulatory-radar",
            "version": "0.2.0",
            "description": (
                "Authoritative-source regulatory change evidence, compliance "
                "screening, and deadline monitoring"
            ),
            "capabilities": [
                "scan_regulations",
                "assess_compliance",
                "detect_opportunities",
                "generate_tnfd_report",
                "generate_csrd_report",
                "regulatory_forecast",
                "generate_alerts",
                "monitor_changes",
                "build_evidence_pack",
            ],
            "inputs": [
                "jurisdiction", "industry_sector", "company_profile",
                "regulation_query", "topics", "active_projects",
                "lookback_days",
                "source_ids", "persist_snapshot",
            ],
            "outputs": [
                "compliance_assessment", "regulatory_alert",
                "opportunity_signal", "tnfd_report", "changes",
                "alert_level", "source_snapshots", "source_hashes",
                "change_diffs", "delivery_receipt",
            ],
        }
