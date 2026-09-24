"""
Regulatory dataset for RegulatoryRadarCore.

Extracted from core._build_database by Nightkeeper 2026-04-20 (Night 20,
queue #3). Keeping data here and business logic in core.py means the
dataset can be updated without touching or risk-of-breaking the processing
code, and vice versa.

Design: zero imports. All types (Regulation, Jurisdiction, Sector, datetime)
are injected by the caller via build_regulations(). This avoids the circular
import that would arise if this module imported from core.py.

Usage in core.py:
    from .data.regulations import build_regulations
    ...
    def _build_database(self) -> Dict[str, Regulation]:
        return build_regulations(Regulation, Jurisdiction, Sector, datetime)

Adding a new regulation: append a new entry to the dict returned below.
No other file needs to change.
"""


def build_regulations(Regulation, Jurisdiction, Sector, datetime):
    """
    Return the full regulations database as {id: Regulation(...)}.

    All four type arguments are injected by the caller (core._build_database)
    to avoid circular imports — this module has no imports of its own.
    """
    return {
        # ─── Foundation: global frameworks ────────────────────────────────
        "tnfd-disclosure-2024": Regulation(
            id="tnfd-disclosure-2024",
            name="TNFD Recommendations",
            jurisdiction=Jurisdiction.GLOBAL,
            sector=None,
            effective_date=datetime(2023, 9, 18),
            reporting_deadline=None,
            requirements=[
                "Assess nature-related risks and opportunities",
                "Disclose governance structure for nature oversight",
                "Provide biodiversity impact assessment",
                "Set science-based nature targets",
            ],
            penalties="No direct legal penalty unless incorporated into another binding regime",
            standards=["TNFD"],
            description="Voluntary global recommendations for nature-related financial disclosure",
            resource_link="https://tnfd.global/recommendations-of-the-tnfd/",
            legal_status="voluntary_framework",
            date_type="none",
            scope_note=(
                "TNFD is a voluntary disclosure framework, not a universal "
                "company reporting mandate."
            ),
            source_verified_on="2026-07-24",
        ),
        "kunming-montreal-biodiversity": Regulation(
            id="kunming-montreal-cbd",
            name="Kunming-Montreal Global Biodiversity Framework",
            jurisdiction=Jurisdiction.GLOBAL,
            sector=None,
            effective_date=datetime(2022, 12, 19),
            reporting_deadline=None,
            requirements=[
                "Implement nature-positive business practices",
                "Halt biodiversity loss by 2030",
                "Restore 30% of degraded ecosystems by 2030",
                "Reduce chemical pollution by 50%",
                "National biodiversity strategy implementation",
            ],
            penalties="No direct company penalty; implementation occurs through national measures",
            standards=["CBD", "GBF"],
            description="Intergovernmental framework for national action to halt and reverse biodiversity loss",
            resource_link="https://www.cbd.int/gbf",
            legal_status="intergovernmental_framework",
            date_type="none",
            scope_note=(
                "The framework binds parties at the international level; "
                "company obligations depend on national implementation."
            ),
            source_verified_on="2026-07-24",
        ),
        "article-6-carbon-market": Regulation(
            id="article-6-carbon",
            name="Paris Agreement Article 6 - International Carbon Markets",
            jurisdiction=Jurisdiction.GLOBAL,
            sector=None,
            effective_date=datetime(2021, 11, 1),
            reporting_deadline=None,
            requirements=[
                "Track carbon credit origin and authenticity",
                "Prevent double counting of emissions reductions",
                "Register and report carbon transactions",
                "Ensure environmental integrity of credits",
            ],
            penalties="No universal company penalty; mechanism-specific and national rules apply",
            standards=["Paris Agreement", "Article 6"],
            description="International framework for cross-border carbon credit trading and cooperation",
            resource_link="https://unfccc.int/process-and-meetings/the-paris-agreement/article-6",
            legal_status="intergovernmental_mechanism",
            date_type="none",
            scope_note=(
                "Relevant to participating states and authorised market "
                "mechanisms, not a general corporate reporting deadline."
            ),
            source_verified_on="2026-07-24",
        ),

        # ─── EU regulations ────────────────────────────────────────────────
        "csrd-reporting-2024": Regulation(
            id="csrd-reporting-2024",
            name="Corporate Sustainability Reporting Directive (CSRD) — Wave 1",
            jurisdiction=Jurisdiction.EU,
            sector=None,
            effective_date=datetime(2024, 1, 1),
            reporting_deadline=None,
            requirements=[
                "Double materiality assessment (impact and financial)",
                "Report on governance, strategy, risk management",
                "Comprehensive ESG metrics",
                "Climate science-based targets",
                "Third-party assurance",
            ],
            penalties="Member State enforcement and penalties vary by national transposition",
            standards=["CSRD", "ESRS"],
            description=(
                "EU sustainability reporting requirements currently applying "
                "to first-wave companies; later waves were postponed"
            ),
            resource_link="https://finance.ec.europa.eu/financial-markets/company-reporting-and-auditing/company-reporting/corporate-sustainability-reporting_en",
            legal_status="binding_scope_in_transition",
            date_type="none",
            scope_note=(
                "First-wave companies reported for financial year 2024 in "
                "2025. Wave-two and wave-three entry was postponed; exact "
                "scope and filing timing require entity-specific review."
            ),
            source_verified_on="2026-07-24",
        ),
        "eu-taxonomy-2023": Regulation(
            id="eu-taxonomy-2023",
            name="EU Taxonomy Regulation Amendment 2023",
            jurisdiction=Jurisdiction.EU,
            sector=None,
            effective_date=datetime(2023, 1, 1),
            reporting_deadline=None,
            requirements=[
                "Classify economic activities by environmental sustainability",
                "Report percentage of revenue from sustainable activities",
                "Monitor alignment with climate targets",
                "Track biodiversity and water indicators",
            ],
            penalties="Reporting non-compliance, investor exclusion, funding restrictions",
            standards=["EU Taxonomy"],
            description="Classification system for sustainable economic activities in EU, expanded to include biodiversity",
            resource_link="https://finance.ec.europa.eu/sustainable-finance/tools-and-standards/eu-taxonomy-sustainable-activities_en",
            legal_status="binding_scope_in_transition",
            date_type="none",
            scope_note=(
                "Disclosure obligations depend on the reporting entity and "
                "current CSRD/Taxonomy scope; there is no universal year-end "
                "deadline for all companies."
            ),
            source_verified_on="2026-07-24",
        ),

        # ─── US regulations ────────────────────────────────────────────────
        "sec-climate-disclosure-2023": Regulation(
            id="sec-climate-disclosure-2023",
            name="SEC 2024 Climate Disclosure Rule — stayed; rescission proposed",
            jurisdiction=Jurisdiction.US,
            sector=None,
            effective_date=datetime(2024, 5, 28),
            reporting_deadline=None,
            requirements=[
                "Disclose Scope 1 and Scope 2 greenhouse gas emissions",
                "Climate risk impact on business and financial performance",
                "Governance structure for climate risk management",
                "Quantitative climate scenario analysis for high-impact risks",
            ],
            penalties="No current compliance penalty while the rule remains stayed",
            standards=["SEC", "TCFD"],
            description=(
                "The 2024 federal climate-disclosure rule remains stayed; "
                "the SEC proposed rescinding it in full on 29 May 2026"
            ),
            resource_link="https://www.sec.gov/newsroom/press-releases/2026-49-sec-proposes-rescission-climate-related-disclosure-rules",
            legal_status="stayed_rescission_proposed",
            date_type="none",
            scope_note=(
                "Do not treat this rule as an active federal reporting "
                "deadline. State and existing materiality-based disclosure "
                "requirements may still apply."
            ),
            source_verified_on="2026-07-24",
        ),
        "california-climate-accountability": Regulation(
            id="ca-sb261-2026",
            name=(
                "California SB 261 — Climate risk reports; enforcement "
                "enjoined"),
            jurisdiction=Jurisdiction.CALIFORNIA,
            sector=None,
            effective_date=datetime(2023, 10, 7),
            reporting_deadline=datetime(2026, 1, 1),
            requirements=[
                "Publish a climate-related financial risk report",
                "Describe measures adopted to reduce and adapt to disclosed risk",
                "Use the TCFD framework or an equivalent standard",
                "Post the report publicly on the entity website",
            ],
            penalties=(
                "CARB states it will not enforce failure to post or submit "
                "the January 1, 2026 report while the appellate injunction "
                "remains in effect"),
            standards=["California SB 261", "TCFD"],
            description=(
                "Biennial climate-related financial risk reporting for covered "
                "entities doing business in California"
            ),
            resource_link=(
                "https://ww2.arb.ca.gov/public-comments/"
                "climate-related-financial-risk-reports-sb-261-docket"),
            legal_status="statutory_requirement_enforcement_enjoined",
            date_type="first_reporting_deadline",
            scope_note=(
                "The statutory date has passed, but CARB says a Ninth Circuit "
                "injunction prevents enforcement for failure to post and "
                "submit by that date. CARB's public docket accepts voluntary "
                "reports. Verify current litigation and entity-specific "
                "coverage before relying on this entry."
            ),
            source_verified_on="2026-07-25",
        ),

        # ─── UK regulations ────────────────────────────────────────────────
        "uk-biodiversity-net-gain": Regulation(
            id="uk-bng-2023",
            name="UK Biodiversity Net Gain (BNG) Mandate",
            jurisdiction=Jurisdiction.UK,
            sector=None,
            effective_date=datetime(2024, 2, 12),
            reporting_deadline=None,
            requirements=[
                "Achieve minimum 10% biodiversity net gain on development",
                "Habitat baseline assessment and monitoring",
                "Maintain significant on-site or off-site gains for at least 30 years",
                "Use Defra Biodiversity Net Gain metric",
            ],
            penalties="Planning enforcement may apply for breach of the biodiversity gain condition or legal agreement",
            standards=["BNG", "Environment Act 2021"],
            description="England requirement for at least 10% biodiversity net gain on non-exempt development",
            resource_link="https://www.gov.uk/guidance/understanding-biodiversity-net-gain",
            legal_status="binding",
            date_type="none",
            scope_note=(
                "Applies in England, subject to exemptions and separate rules "
                "for nationally significant infrastructure projects."
            ),
            source_verified_on="2026-07-24",
        ),

        # ─── 2025–2026 regulatory wave (backfilled Night 19, queue #3) ────
        # All entries below have effective_date or reporting_deadline within
        # the 365-day lookback window from 2026-04-19 so monitor_changes
        # surfaces them. These are the compliance deadlines Carbon-Bridge,
        # Proof-of-Conservation, and enterprise customers must respond to.

        "csrd-wave2-delayed-2028": Regulation(
            id="csrd-wave2-delayed-2028",
            name="CSRD Wave 2 — entry postponed by Stop-the-clock Directive",
            jurisdiction=Jurisdiction.EU,
            sector=None,
            effective_date=datetime(2027, 1, 1),
            reporting_deadline=None,
            requirements=[
                "Confirm whether the undertaking remains within revised CSRD scope",
                "Prepare a double materiality assessment where in scope",
                "Prepare an ESRS-compliant sustainability statement",
                "Third-party limited assurance",
            ],
            penalties="Member State enforcement and penalties vary by national transposition",
            standards=["CSRD", "ESRS"],
            description=(
                "Wave-two and wave-three reporting entry was postponed by two "
                "years while the EU simplified CSRD scope and standards"
            ),
            resource_link="https://finance.ec.europa.eu/financial-markets/company-reporting-and-auditing/company-reporting/corporate-sustainability-reporting_en",
            legal_status="binding_delayed_scope_in_transition",
            date_type="none",
            scope_note=(
                "Do not use the former FY2025/2026 dates. Confirm current "
                "entity scope and national transposition before advising."
            ),
            source_verified_on="2026-07-24",
        ),
        "eudr-full-effect-2025": Regulation(
            id="eudr-2025",
            name="EU Deforestation Regulation (EUDR) — large/medium application",
            jurisdiction=Jurisdiction.EU,
            sector=None,
            effective_date=datetime(2026, 12, 30),
            reporting_deadline=datetime(2026, 12, 30),
            requirements=[
                "Prove zero-deforestation supply chain (cut-off 2020-12-31)",
                "Geolocation of all production plots via polygons",
                "Due diligence statement (DDS) per shipment covering 7 commodities",
                "Cattle, cocoa, coffee, palm oil, rubber, soy, wood + derived products",
                "Supply chain traceability to plot of origin",
            ],
            penalties="Up to 4% EU turnover, goods confiscation, exclusion from public procurement",
            standards=["EUDR", "Regulation (EU) 2023/1115"],
            description="Requires covered commodities placed on or exported from the EU market to be deforestation-free and legally produced",
            resource_link="https://environment.ec.europa.eu/topics/forests/deforestation/regulation-deforestation-free-products_en",
            legal_status="binding_application_upcoming",
            date_type="application_date",
            scope_note=(
                "Applies from 30 December 2026 to large and medium operators "
                "and EUTR-covered small operators; other micro and small "
                "operators start 30 June 2027."
            ),
            source_verified_on="2026-07-24",
        ),
        "cbam-definitive-2026": Regulation(
            id="cbam-definitive-2026",
            name="EU Carbon Border Adjustment Mechanism (CBAM) — Definitive Period",
            jurisdiction=Jurisdiction.EU,
            sector=None,
            effective_date=datetime(2026, 1, 1),
            reporting_deadline=datetime(2027, 9, 30),
            requirements=[
                "Import more than 50 tonnes annually of covered CBAM goods",
                "Hold authorised CBAM declarant status or a valid application reference",
                "Purchase and surrender CBAM certificates for embedded emissions",
                "Annual verified emissions declaration by CBAM authorized declarant",
                "Coverage: iron/steel, aluminium, cement, fertilisers, hydrogen, electricity",
                "Third-party verification by accredited verifier",
            ],
            penalties="€100/tCO2e plus underpayment × 3 for non-compliance; import blocking",
            standards=["CBAM", "Regulation (EU) 2023/956"],
            description="EU carbon-border regime in force for covered imports from 1 January 2026",
            resource_link="https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism/cbam-communication-and-faqs_en",
            legal_status="binding",
            date_type="first_declaration_and_surrender_deadline",
            scope_note=(
                "The first declaration and certificate surrender for 2026 "
                "imports is due 30 September 2027. Certificate purchases "
                "begin in February 2027."
            ),
            source_verified_on="2026-07-24",
        ),
        "ca-sb253-first-filing-2026": Regulation(
            id="ca-sb253-2026",
            name="California SB 253 — First Mandatory Scope 1+2 Filing",
            jurisdiction=Jurisdiction.CALIFORNIA,
            sector=None,
            effective_date=datetime(2026, 1, 1),
            reporting_deadline=datetime(2026, 8, 10),
            requirements=[
                "First mandatory Scope 1 and Scope 2 GHG disclosure for entities with >$1B revenue",
                "Third-party limited assurance on Scope 1+2 (reasonable assurance from 2030)",
                "GHG Protocol aligned reporting",
                "California-specific data granularity",
            ],
            penalties="Up to $500,000/year administrative penalties (CARB enforcement)",
            standards=["California Climate Code", "GHG Protocol"],
            description="California mandatory Scope 1 and Scope 2 emissions filing for covered entities in 2026",
            resource_link="https://ww2.arb.ca.gov/news/carb-approves-climate-transparency-regulation-entities-doing-business-california",
            legal_status="binding",
            date_type="first_reporting_deadline",
            scope_note=(
                "Applies to U.S.-based entities with more than $1 billion in "
                "annual revenue doing business in California. Scope 3 "
                "reporting begins in 2027."
            ),
            source_verified_on="2026-07-25",
        ),
        "tnfd-sector-guidance-2025": Regulation(
            id="tnfd-sector-2025",
            name="TNFD Sector Guidance — Financial & Nature-Sensitive Sectors",
            jurisdiction=Jurisdiction.GLOBAL,
            sector=None,
            effective_date=datetime(2025, 4, 1),
            reporting_deadline=None,
            requirements=[
                "Apply TNFD LEAP approach with sector-specific materiality",
                "Financial sector: portfolio-level nature-related exposure disclosure",
                "Ag/forestry/fisheries: dependency and impact pathway quantification",
                "Extractives: site-level biodiversity footprint per operation",
            ],
            penalties="No direct legal penalty unless incorporated into another binding regime",
            standards=["TNFD", "ISSB S2", "GBF"],
            description="TNFD expands from cross-sector recommendations to sector-specific guidance covering financials and 8 highest-impact sectors",
            resource_link="https://tnfd.global/recommendations-of-the-tnfd/sector-guidance/",
            legal_status="voluntary_framework",
            date_type="none",
            scope_note="Voluntary guidance, not a universal reporting deadline.",
            source_verified_on="2026-07-24",
        ),
        "uk-sdr-asset-managers-2025": Regulation(
            id="uk-sdr-2025",
            name="UK Sustainability Disclosure Requirements (SDR) — Asset Managers",
            jurisdiction=Jurisdiction.UK,
            sector=None,
            effective_date=datetime(2025, 12, 2),
            reporting_deadline=None,
            requirements=[
                "Use one of 4 approved SDR labels (Focus, Improvers, Impact, Mixed Goals) or no label",
                "Anti-greenwashing rule applies to all FCA-regulated firms",
                "Consumer-facing product disclosures (2-page summary)",
                "Pre-contractual and ongoing sustainability disclosures",
                "Entity-level public product report",
            ],
            penalties="FCA supervisory or enforcement action may apply for breaches of binding rules",
            standards=["UK SDR", "FCA ESG Sourcebook"],
            description="UK regime for sustainable investment labels and anti-greenwashing, phased through 2024-2026 for asset managers and products",
            resource_link="https://www.fca.org.uk/firms/climate-change-and-sustainable-finance/sustainability-disclosure-requirements-sdr-regime",
            legal_status="binding_with_voluntary_labels",
            date_type="none",
            scope_note=(
                "Mandatory naming, marketing and disclosure rules apply to "
                "in-scope firms; use of an SDR investment label is voluntary."
            ),
            source_verified_on="2026-07-24",
        ),
    }
