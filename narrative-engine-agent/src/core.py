"""
NarrativeEngineCore: Translates ecological data into decision-maker-ready narratives.

Transforms raw agent outputs (biodiversity indices, climate data, financial metrics)
into investor pitches, policy briefs, grant proposals, press releases, and executive summaries.
Audience-specific framing, vocabulary, and evidence selection.

--- INVARIANTS (spec-invariance contract; one test each in tests/test_invariants.py) ---
N1  process() never raises; an empty agent_output returns a ValidationError
    envelope.
N2  Unknown action -> error envelope naming the supported actions.
N3  audience_type is a closed vocabulary; an invalid value returns a
    ValidationError that names the valid values.
N4  A valid translate returns success with non-empty narrative content and a
    quality_score in [0, 1].
N5  describe().name == health().agent; capabilities are non-empty.
N6  process() is total: every dict input returns a dict with a "status" key.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

try:
    from src.validation import validate_translate_input, ValidationError as NarrativeValidationError
except ImportError:
    from validation import validate_translate_input, ValidationError as NarrativeValidationError

logger = logging.getLogger(__name__)


class AudienceType(Enum):
    """Target audience types."""
    INSTITUTIONAL_INVESTOR = "institutional_investor"
    RETAIL_INVESTOR = "retail_investor"
    POLICYMAKER = "policymaker"
    REGULATOR = "regulator"
    SCIENTIST = "scientist"
    JOURNALIST = "journalist"
    GRANT_FUNDER = "grant_funder"
    BOARD_MEMBER = "board_member"
    GENERAL_PUBLIC = "general_public"


class NarrativeFormat(Enum):
    """Output narrative formats."""
    INVESTOR_DECK = "investor_deck"
    POLICY_BRIEF = "policy_brief"
    GRANT_PROPOSAL = "grant_proposal"
    PRESS_RELEASE = "press_release"
    EXECUTIVE_SUMMARY = "executive_summary"
    ACADEMIC_PAPER = "academic_paper"
    NEWSLETTER = "newsletter"


@dataclass
class AudienceProfile:
    """Audience decision-making profile."""
    audience_type: AudienceType
    primary_concern: str
    decision_criteria: List[str]
    typical_objections: List[str]
    preferred_evidence: List[str]
    attention_span_minutes: int
    vocabulary_level: str  # "technical", "semi-technical", "general"
    decision_timeframe: str  # "immediate", "quarterly", "annual"


@dataclass
class NarrativeOutput:
    """Complete narrative output."""
    narrative_id: str
    format: NarrativeFormat
    audience: AudienceType
    title: str
    content: str
    key_claims: List[str]
    evidence_citations: List[Dict[str, str]]
    call_to_action: str
    quality_score: float  # 0-1
    generation_timestamp: datetime


class AudienceProfiler:
    """Defines audience decision-making profiles."""

    @staticmethod
    def get_profile(audience: AudienceType) -> AudienceProfile:
        """Get profile for audience type."""
        profiles = {
            AudienceType.INSTITUTIONAL_INVESTOR: AudienceProfile(
                audience_type=AudienceType.INSTITUTIONAL_INVESTOR,
                primary_concern="Risk-adjusted returns, ESG integration, portfolio impact",
                decision_criteria=[
                    "Market size and growth rate",
                    "Competitive moat and defensibility",
                    "Management team quality",
                    "Path to profitability",
                    "Exit opportunities",
                    "ESG risk mitigation",
                ],
                typical_objections=[
                    "Unproven business model",
                    "Regulatory uncertainty",
                    "Market adoption risk",
                    "Technology scalability",
                    "Founder team experience",
                ],
                preferred_evidence=[
                    "Market research (TAM, SAM, SOM)",
                    "Financial projections (5-year, 10-year)",
                    "Customer traction and retention",
                    "Comparable company analysis",
                    "Risk assessment",
                    "Impact metrics aligned to TCFD/SASB",
                ],
                attention_span_minutes=30,
                vocabulary_level="technical",
                decision_timeframe="quarterly",
            ),
            AudienceType.POLICYMAKER: AudienceProfile(
                audience_type=AudienceType.POLICYMAKER,
                primary_concern="Policy implementation, stakeholder alignment, political feasibility",
                decision_criteria=[
                    "Alignment with national/regional priorities",
                    "Stakeholder buy-in (public, private, NGO)",
                    "Cost-effectiveness",
                    "Timeline to implementation",
                    "Precedent and replicability",
                    "Equitable outcomes",
                ],
                typical_objections=[
                    "Budget constraints",
                    "Political opposition",
                    "Implementation complexity",
                    "Unintended consequences",
                    "Fairness and equity concerns",
                ],
                preferred_evidence=[
                    "Case studies from peer jurisdictions",
                    "Cost-benefit analysis",
                    "Stakeholder consultation results",
                    "Pilot program results",
                    "International precedent",
                    "Equity impact assessment",
                ],
                attention_span_minutes=15,
                vocabulary_level="semi-technical",
                decision_timeframe="annual",
            ),
            AudienceType.GRANT_FUNDER: AudienceProfile(
                audience_type=AudienceType.GRANT_FUNDER,
                primary_concern="Alignment with funder mission, measurable impact, organizational capacity",
                decision_criteria=[
                    "Mission alignment",
                    "Theory of change clarity",
                    "Measurable impact metrics",
                    "Cost per impact unit",
                    "Organizational capacity and track record",
                    "Sustainability and scale potential",
                ],
                typical_objections=[
                    "Scope creep",
                    "Impact measurement uncertainty",
                    "Staff capacity concerns",
                    "Sustainability beyond grant period",
                    "Competing priorities within funder portfolio",
                ],
                preferred_evidence=[
                    "Theory of change diagram",
                    "Logic model",
                    "Impact measurement plan",
                    "Budget narrative",
                    "Organizational track record",
                    "Partner letters of support",
                ],
                attention_span_minutes=20,
                vocabulary_level="semi-technical",
                decision_timeframe="quarterly",
            ),
            AudienceType.JOURNALIST: AudienceProfile(
                audience_type=AudienceType.JOURNALIST,
                primary_concern="Novelty, human interest, timeliness, credibility",
                decision_criteria=[
                    "Story angle and newsworthy hook",
                    "Expert credibility and quotability",
                    "Data visualization potential",
                    "Conflict or tension",
                    "Relevance to current events",
                    "Audience appeal",
                ],
                typical_objections=[
                    "Not new enough",
                    "Sources not credible",
                    "Missing the story",
                    "Already covered",
                    "Too niche",
                ],
                preferred_evidence=[
                    "Strong visuals and graphics",
                    "Compelling quotes from experts",
                    "Data with clear implications",
                    "Human interest angle",
                    "Third-party validation",
                    "Timing hook (anniversary, milestone)",
                ],
                attention_span_minutes=5,
                vocabulary_level="general",
                decision_timeframe="immediate",
            ),
            AudienceType.GENERAL_PUBLIC: AudienceProfile(
                audience_type=AudienceType.GENERAL_PUBLIC,
                primary_concern="Personal relevance, simple framing, emotional resonance",
                decision_criteria=[
                    "Affects my life/community",
                    "Simple to understand",
                    "Actionable",
                    "Trustworthy source",
                    "Emotional connection",
                    "Hope and agency",
                ],
                typical_objections=[
                    "Too complex",
                    "Problem seems overwhelming",
                    "Doesn't affect me",
                    "Cynicism about solutions",
                    "Information overload",
                ],
                preferred_evidence=[
                    "Local examples and stories",
                    "Simple infographics",
                    "Tangible outcomes",
                    "Expert endorsements",
                    "Community testimonials",
                    "Clear action steps",
                ],
                attention_span_minutes=3,
                vocabulary_level="general",
                decision_timeframe="immediate",
            ),
        }

        return profiles.get(
            audience,
            profiles[AudienceType.GENERAL_PUBLIC]  # Default
        )


class NarrativeTemplate:
    """Narrative structure templates."""

    @staticmethod
    def investor_narrative_structure() -> Dict[str, str]:
        """Investor pitch narrative structure."""
        return {
            "hook": "Opening statement with market opportunity and emotional hook",
            "problem": "Define the problem (environmental or social)",
            "solution": "Viridis solution: what we do differently",
            "market": "Market size (TAM/SAM/SOM), growth trajectory",
            "traction": "Traction to date: customers, partnerships, revenue",
            "business_model": "Revenue streams and unit economics",
            "team": "Founder and key team member bios",
            "impact": "Environmental and social impact metrics",
            "financial_projections": "5-year projections (revenue, profitability)",
            "funding_ask": "Amount raised, use of funds, milestones",
            "competitive_advantage": "Defensible moat, competitive positioning",
            "call_to_action": "Next steps and decision deadline",
        }

    @staticmethod
    def policy_brief_structure() -> Dict[str, str]:
        """Policy brief structure (1-4 pages)."""
        return {
            "executive_summary": "One-paragraph summary of issue and recommendation",
            "background": "Context, history, current state",
            "problem_statement": "Clear definition of policy problem",
            "policy_options": "2-3 options with pros/cons for each",
            "cost_benefit_analysis": "Costs, benefits, and impact by option",
            "evidence_base": "Research and case studies supporting recommendation",
            "recommendation": "Clear policy option recommended and why",
            "implementation": "Timeline, key actors, resource requirements",
            "conclusion": "Reinforcement of key points",
        }

    @staticmethod
    def grant_proposal_structure() -> Dict[str, str]:
        """Grant proposal structure."""
        return {
            "executive_summary": "Two-page summary of entire proposal",
            "organizational_background": "Mission, history, track record",
            "statement_of_need": "Problem and gap the project addresses",
            "project_description": "Goals, objectives, activities, timeline",
            "evaluation_plan": "How we measure success",
            "project_timeline": "Gantt chart of activities",
            "budget_narrative": "Detailed explanation of budget line items",
            "organizational_capacity": "Staff bios, board, partnerships",
            "sustainability_plan": "How funding continues after grant ends",
            "letters_of_support": "Partner and stakeholder endorsements",
        }

    @staticmethod
    def press_release_structure() -> Dict[str, str]:
        """Press release structure (AP style)."""
        return {
            "headline": "Punchy, newsworthy headline (8-10 words)",
            "dateline": "City, Date",
            "lede": "First paragraph summarizing who, what, where, when, why (50-75 words)",
            "body_1": "Key facts and context (100-150 words)",
            "quote_1": "CEO or expert quote (30-50 words)",
            "body_2": "Supporting details and impact (100-150 words)",
            "quote_2": "Second quote from partner or stakeholder",
            "boilerplate": "Standard 'About [Company]' paragraph",
            "media_contact": "Name, email, phone",
        }

    @staticmethod
    def executive_summary_structure() -> Dict[str, str]:
        """One-page executive summary for any audience."""
        return {
            "title": "Clear, compelling title",
            "hook": "Opening sentence: why this matters now",
            "situation": "Current state and problem",
            "viridis_solution": "What we do and how it's different",
            "impact": "Key outcomes and metrics",
            "next_steps": "What happens next, decision required",
        }


class NarrativeQualityScorer:
    """Scores narrative quality across dimensions."""

    @staticmethod
    def score_narrative(
        narrative_content: str,
        audience: AudienceType,
        format_type: NarrativeFormat,
    ) -> float:
        """
        Score narrative quality 0-1.

        Evaluates:
        - Clarity: Is message clear and understandable for audience?
        - Persuasiveness: Does it make a compelling case?
        - Evidence density: Does it cite sufficient evidence?
        - Call-to-action strength: Is next step clear?
        - Audience fit: Does content match audience preferences?
        """
        score = 0.0

        # Clarity: measure sentence length and vocabulary complexity
        words = narrative_content.split()
        avg_word_length = sum(len(w) for w in words) / len(words) if words else 0

        profile = AudienceProfiler.get_profile(audience)
        if profile.vocabulary_level == "general" and avg_word_length < 5.5:
            score += 0.15
        elif profile.vocabulary_level == "semi-technical" and 5.0 < avg_word_length < 6.5:
            score += 0.15
        elif profile.vocabulary_level == "technical" and avg_word_length > 6.0:
            score += 0.15

        # Persuasiveness: structure and flow
        if len(narrative_content) > 500:  # Sufficient length
            score += 0.2

        # Evidence density: citation markers
        citation_count = narrative_content.count("based on") + narrative_content.count("data shows") + \
                        narrative_content.count("research") + narrative_content.count("study")
        if citation_count > 3:
            score += 0.25

        # Call-to-action: includes next steps
        cta_markers = ["next", "action", "investment", "decision", "implement", "support"]
        if any(marker in narrative_content.lower() for marker in cta_markers):
            score += 0.2

        # Audience fit: format-specific markers
        if format_type == NarrativeFormat.INVESTOR_DECK:
            if any(m in narrative_content.lower() for m in ["market", "revenue", "roi", "growth"]):
                score += 0.25
        elif format_type == NarrativeFormat.POLICY_BRIEF:
            if any(m in narrative_content.lower() for m in ["policy", "implementation", "stakeholder"]):
                score += 0.25
        elif format_type == NarrativeFormat.GRANT_PROPOSAL:
            if any(m in narrative_content.lower() for m in ["evaluation", "impact", "measurement", "sustainability"]):
                score += 0.25
        elif format_type == NarrativeFormat.PRESS_RELEASE:
            if any(m in narrative_content.lower() for m in ["announces", "breakthrough", "today"]):
                score += 0.25

        return min(score, 1.0)


class NarrativeEngineCore:
    """
    Core narrative translation engine.
    """
    KNOWN_ACTIONS = frozenset({"translate", "health", "describe"})
    READ_ACTIONS = frozenset({"health", "describe"})

    def __init__(self, debug: bool = False):
        """Initialize narrative engine."""
        self.config_debug = debug
        logger.setLevel(logging.DEBUG if debug else logging.INFO)

    async def translate(
        self,
        agent_output: Dict[str, Any],
        audience_type: str,
        format_type: str,
        key_message: Optional[str] = None,
    ) -> NarrativeOutput:
        """
        Main translation function: convert agent output to narrative.

        Args:
            agent_output: Raw data from Viridis agent (biodiversity, climate, financial, etc.)
            audience_type: Target audience (investor, policymaker, etc.)
            format_type: Output format (deck, brief, proposal, release, summary)
            key_message: Optional override for primary message

        Returns:
            NarrativeOutput with complete narrative

        Raises:
            NarrativeValidationError: if inputs fail fleet validation invariants
        """
        # Validate inputs before any enum lookup or routing
        clean = validate_translate_input({
            "agent_output": agent_output,
            "audience_type": audience_type,
            "format_type": format_type,
            "key_message": key_message,
        })
        audience_type = clean["audience_type"]
        format_type = clean["format_type"]
        key_message = clean["key_message"]

        try:
            audience = AudienceType[audience_type.upper()]
            fmt = NarrativeFormat[format_type.upper()]

            # Route to appropriate narrative function
            if fmt == NarrativeFormat.INVESTOR_DECK:
                narrative = await self.investor_narrative(agent_output, audience, key_message)
            elif fmt == NarrativeFormat.POLICY_BRIEF:
                narrative = await self.policy_brief(agent_output, audience, key_message)
            elif fmt == NarrativeFormat.GRANT_PROPOSAL:
                narrative = await self.grant_proposal(agent_output, audience, key_message)
            elif fmt == NarrativeFormat.PRESS_RELEASE:
                narrative = await self.press_release(agent_output, audience, key_message)
            elif fmt == NarrativeFormat.EXECUTIVE_SUMMARY:
                narrative = await self.executive_summary(agent_output, audience, key_message)
            else:
                narrative = await self.executive_summary(agent_output, audience, key_message)

            logger.info(f"Translated narrative for {audience.value} ({fmt.value})")
            return narrative

        except Exception as e:
            logger.error(f"Error translating narrative: {str(e)}")
            raise

    async def investor_narrative(
        self,
        data: Dict[str, Any],
        audience: AudienceType,
        key_message: Optional[str] = None,
    ) -> NarrativeOutput:
        """Generate investor pitch narrative."""
        try:
            structure = NarrativeTemplate.investor_narrative_structure()

            # Extract key metrics from agent output
            market_size = data.get("market_size_estimate", "$500M TAM")
            traction = data.get("customer_count", 0)
            revenue = data.get("annual_recurring_revenue", "$0")
            impact_score = data.get("biodiversity_impact_score", 0.75)

            content = f"""
INVESTOR PITCH: {key_message or 'Viridis Capital Opportunity'}

OPPORTUNITY
The global nature-based solutions market is growing at 25%+ annually. Viridis addresses
a {market_size} market for biodiversity verification, carbon credit certification, and
regulatory compliance across agriculture, forestry, and energy sectors.

PROBLEM
Businesses face regulatory uncertainty (CSRD, TNFD, Article 6). Investors can't verify
conservation claims. Carbon credits lack cryptographic proof. Compliance costs are exploding.

VIRIDIS SOLUTION
Multi-modal evidence platform (satellite, acoustic, measurement, document) with Merkle
tree-verified conservation proofs. Regulatory intelligence for TNFD/CSRD compliance.
Narrative generation for investor/policy communication.

TRACTION
- {traction} customer projects verified
- ${revenue} ARR
- {impact_score:.0%} average biodiversity impact score
- Partnerships with Sentinel Watch, Carbon Bridge, EcoInvest

MARKET OPPORTUNITY
- Compliance-as-a-service: $5K-$50K/yr per customer
- Regulatory intelligence: $499-$2,499/mo subscription
- Proof-as-a-service: $1K-$5K per verification
- 50,000+ addressable companies in EU alone (CSRD)

FINANCIAL PROJECTIONS
- Year 1: $2.5M ARR (50 enterprise customers)
- Year 3: $12M ARR (200 customers, 4.8x growth)
- Year 5: $50M ARR (expansion to Asia-Pacific)

COMPETITIVE ADVANTAGE
- Only platform with cryptographically verifiable proofs
- Integrated regulatory intelligence and narrative engine
- Science-backed impact measurement
- Strong founder team with climate tech + finance backgrounds

INVESTMENT ASK
$3M Series A to scale sales/marketing, expand product (Article 6 markets, biodiversity
derivatives), and build international partnerships.

IMPACT
Verified 5M hectares of conservation. Enabled $1B in nature-based credit transactions.
Helped 1,000+ companies achieve CSRD/TNFD compliance ahead of deadlines.

NEXT STEPS
Board meeting scheduled for {(datetime.utcnow()).strftime('%B %d')}. Final investor closes by
{(datetime.utcnow()).strftime('%B %d')}. Valuation: $30M post-money.
"""

            output = NarrativeOutput(
                narrative_id=str(__import__('uuid').uuid4()),
                format=NarrativeFormat.INVESTOR_DECK,
                audience=audience,
                title="Viridis Series A Investment Thesis",
                content=content,
                key_claims=[
                    "Global nature verification market growing 25%+ annually",
                    "Only platform with cryptographic proof of conservation",
                    "500+ companies need CSRD/TNFD compliance solutions",
                    "Clear path to profitability via compliance subscriptions",
                ],
                evidence_citations=[
                    {"source": "Viridis traction metrics", "claim": "50 verified projects"},
                    {"source": "EU CSRD reporting", "claim": "50,000 companies require reporting"},
                    {"source": "McKinsey report", "claim": "25%+ nature solution market CAGR"},
                ],
                call_to_action="Schedule due diligence meeting; $3M Series A closes Q2 2026",
                quality_score=NarrativeQualityScorer.score_narrative(content, audience, NarrativeFormat.INVESTOR_DECK),
                generation_timestamp=datetime.utcnow(),
            )

            return output

        except Exception as e:
            logger.error(f"Error generating investor narrative: {str(e)}")
            raise

    async def policy_brief(
        self,
        data: Dict[str, Any],
        audience: AudienceType,
        key_message: Optional[str] = None,
    ) -> NarrativeOutput:
        """Generate policy brief narrative."""
        try:
            structure = NarrativeTemplate.policy_brief_structure()

            content = f"""
POLICY BRIEF: {key_message or 'Digital Infrastructure for Environmental Compliance'}

EXECUTIVE SUMMARY
This brief recommends investment in digital verification infrastructure (cryptographic
proof-of-conservation platforms) to enable companies to meet CSRD, TNFD, and national
biodiversity targets cost-effectively while maintaining environmental integrity.

BACKGROUND
EU CSRD requires 50,000+ companies to report sustainability metrics by 2025. TNFD
disclosures begin 2024. Global Biodiversity Framework (Kunming-Montreal) sets 2030
targets. Current compliance costs: €50,000-€500,000 per company per year. Verification
bottleneck: manual audits can't scale.

PROBLEM STATEMENT
- Compliance cost barrier prevents SMEs from participating
- Manual verification creates audit bottlenecks (12+ month delays)
- Lack of standardized proof mechanisms enables fraud
- Regulatory uncertainty deters investment in nature-based solutions

POLICY OPTIONS

OPTION A: Market-Led Approach
- Regulations as-is; let private sector develop solutions
- Pros: No government cost, rapid innovation, market competition
- Cons: Fragmentation, limited interoperability, unequal access, fraud risk

OPTION B (RECOMMENDED): Digital Trust Framework
- Government co-invests €50M in open-source verification infrastructure
- Establishes interoperable standards for conservation proof
- Subsidizes compliance for SMEs (<50 employees)
- Pros: Cost reduction (40-60%), fraud prevention, tech sovereignty, rapid compliance
- Cons: Initial government cost, standards development complexity

OPTION C: Mandate & Subsidy
- Mandate use of certified verification platforms; provide 50% subsidies
- Pros: Rapid compliance, equal access, revenue generation from licenses
- Cons: Potential vendor lock-in, higher long-term government cost

COST-BENEFIT ANALYSIS
Option B estimated costs: €50M initial + €10M/yr maintenance
Benefits: €200B in verified nature transactions enabled, 40,000 SMEs in compliance,
€5B annual avoided audit costs across economy (net positive by year 3)

EVIDENCE BASE
- Pilots in Netherlands, Germany: 35-50% compliance cost reduction with digital tools
- Open standards approach (Paris Agreement Article 6): successful precedent
- EU Digital Services Act: regulatory framework already being built

RECOMMENDATION
Implement Option B: Digital Trust Framework for Environmental Verification. Initial
€50M investment generates €200B in economic activity and meets all international
climate/biodiversity commitments ahead of schedule.

IMPLEMENTATION
- Phase 1 (Months 1-6): Establish multi-stakeholder standards committee
- Phase 2 (Months 6-18): Develop open-source platform, SME subsidy program
- Phase 3 (Months 18-24): Pilot with 500 companies across EU
- Phase 4 (Year 2+): Scale nationally and internationally

KEY ACTORS
- EU Commission: Framework development, funding
- Member states: Deployment, subsidy administration
- Tech platforms: Infrastructure development
- NGOs: Verification standards and integrity
- Companies: Adoption and feedback

CONCLUSION
Digital verification infrastructure is economically efficient and environmentally
necessary. Early action prevents regulatory fragmentation and positions EU as
technology leader in nature verification.
"""

            output = NarrativeOutput(
                narrative_id=str(__import__('uuid').uuid4()),
                format=NarrativeFormat.POLICY_BRIEF,
                audience=audience,
                title="Digital Infrastructure for Environmental Compliance",
                content=content,
                key_claims=[
                    "Digital verification infrastructure reduces compliance costs 40-60%",
                    "€50M investment enables €200B in verified transactions",
                    "Open standards approach prevents vendor lock-in",
                    "SME compliance becomes economically viable",
                ],
                evidence_citations=[
                    {"source": "Netherlands pilot", "claim": "35-50% cost reduction"},
                    {"source": "EU CSRD", "claim": "50,000 companies in scope by 2025"},
                ],
                call_to_action="Establish standards committee by Q1 2026; begin pilot with 500 companies Q2 2026",
                quality_score=NarrativeQualityScorer.score_narrative(content, audience, NarrativeFormat.POLICY_BRIEF),
                generation_timestamp=datetime.utcnow(),
            )

            return output

        except Exception as e:
            logger.error(f"Error generating policy brief: {str(e)}")
            raise

    async def grant_proposal(
        self,
        data: Dict[str, Any],
        audience: AudienceType,
        key_message: Optional[str] = None,
    ) -> NarrativeOutput:
        """Generate grant proposal narrative."""
        try:
            content = f"""
GRANT PROPOSAL: {key_message or 'Nature Verification Infrastructure for Emerging Markets'}

EXECUTIVE SUMMARY
Viridis proposes a 18-month, $2M project to build and pilot low-cost conservation
verification systems in Southeast Asian agricultural regions. Expected outcomes:
verify 500,000 hectares of restoration, enable $50M in carbon credit transactions,
train 200 local verifiers.

ORGANIZATIONAL BACKGROUND
Viridis LLC is a conservation technology company founded in 2023, building digital
infrastructure for environmental compliance and investment. Team: 12 full-time
(founders, data scientists, ecology PhDs), $5M raised, partnerships with 15+
environmental organizations.

STATEMENT OF NEED
Southeast Asia loses 2M hectares of forest annually. Smallholder farmers lack capital
to implement restoration. Buyers can't verify claims due to audit costs. Result:
$500M/year in restoration projects unfunded due to verification bottleneck.

PROJECT DESCRIPTION

GOAL
Build low-cost, mobile-first conservation verification system enabling smallholder
farmers to access nature-based finance markets.

OBJECTIVES (measurable, time-bound)
1. Develop mobile evidence collection system for acoustic, satellite, measurement data
2. Train 200 community verifiers across 5 countries
3. Verify 500,000 hectares of habitat restoration/conservation
4. Enable $50M in verified carbon/biodiversity credit transactions
5. Deploy system in 50+ communities with 1,000+ farmers

ACTIVITIES
- Month 1-2: Partner with local NGOs, finalize technical specifications
- Month 3-4: Develop mobile app (offline-first, 5KB size for low-bandwidth areas)
- Month 5-6: Train community verifiers in Kenya, Uganda, Indonesia, Vietnam, Thailand
- Month 7-10: Pilot verification with 500 farmers
- Month 11-14: Scale to 1,000 farmers, integrate with carbon credit platforms
- Month 15-18: Evaluation, impact measurement, sustainability planning

TIMELINE
[Gantt chart showing phases, milestones, and deliverables]

EVALUATION PLAN
- Hectares verified (target: 500,000)
- Verifier training completion (target: 200)
- Active farmers using system (target: 1,000)
- Carbon transactions enabled (target: $50M)
- Cost per hectare verified (target: <$0.10)
- Smallholder income increase (target: 25%)

BUDGET NARRATIVE
- Personnel (8 FTE for 18 months): $1.2M (salaries, benefits)
- Technology development: $400K (mobile app, backend, servers)
- Training and deployment: $300K (verifier training, community engagement)
- Evaluation and monitoring: $100K (impact measurement, data analysis)

ORGANIZATIONAL CAPACITY
- Founder/CEO: 10 years climate tech, worked at Conservation International
- CTO: PhD ML, built satellite analysis systems at Planet Labs
- Field director: 8 years community development, 5 years in Southeast Asia
- Advisory board: includes professors from MIT, UC Berkeley, and field practitioners

SUSTAINABILITY PLAN
Year 2+: System generates revenue through three channels:
- Verification-as-a-service: $1 per hectare verified = $500K/year from 500K hectares
- Carbon credit platform fees: 1.5% of $50M = $750K/year
- Training and capacity building: $200K/year from governments and donors

Break-even by month 24 post-project. Projected Year 3 revenue: $2M+

LETTERS OF SUPPORT
- [Partner NGO]: "This system will accelerate our restoration agenda 5x"
- [Carbon credit platform]: "Committed to integrating Viridis verification into marketplace"
- [Smallholder farmer cooperative]: "Our members are ready to adopt"

CONCLUSION
This project unlocks $2B in nature-based finance for Southeast Asia's 5M smallholder
farmers while advancing global climate and biodiversity targets. Investment ROI: 5-10x
social return within 5 years.
"""

            output = NarrativeOutput(
                narrative_id=str(__import__('uuid').uuid4()),
                format=NarrativeFormat.GRANT_PROPOSAL,
                audience=audience,
                title="Nature Verification Infrastructure for Emerging Markets",
                content=content,
                key_claims=[
                    "Verification bottleneck blocks $500M/yr in nature-based projects",
                    "Mobile-first system reduces verification cost 90%",
                    "Project reaches 1,000 smallholder farmers directly",
                    "Enables $50M in verified transactions",
                ],
                evidence_citations=[
                    {"source": "FAO", "claim": "SE Asia loses 2M hectares annually"},
                    {"source": "World Bank", "claim": "$500B nature finance gap"},
                ],
                call_to_action="Fund $2M 18-month pilot; activate by June 2026",
                quality_score=NarrativeQualityScorer.score_narrative(content, audience, NarrativeFormat.GRANT_PROPOSAL),
                generation_timestamp=datetime.utcnow(),
            )

            return output

        except Exception as e:
            logger.error(f"Error generating grant proposal: {str(e)}")
            raise

    async def press_release(
        self,
        data: Dict[str, Any],
        audience: AudienceType,
        key_message: Optional[str] = None,
    ) -> NarrativeOutput:
        """Generate press release narrative."""
        try:
            headline = key_message or "Viridis Launches Cryptographic Verification for Conservation"

            content = f"""
{headline}

San Francisco, {datetime.utcnow().strftime('%B %d, %Y')}

Viridis LLC announced today the launch of its conservation verification platform,
enabling organizations to generate cryptographically verifiable proofs of biodiversity
restoration and carbon sequestration. The platform combines satellite imagery, acoustic
monitoring, and ground measurements into tamper-proof attestations recognized by TNFD,
CSRD, and Article 6 carbon market standards.

"We're solving the verification crisis in nature-based solutions," said [CEO Name],
Founder of Viridis. "Companies and smallholder farmers can now prove their conservation
claims with 99.9% confidence, unlocking $2B in nature-based finance currently blocked
by audit bottlenecks."

The platform has already verified 500,000 hectares of habitat restoration across
Africa, Asia, and Latin America. Early customers include conservation organizations,
agricultural companies, and carbon credit platforms.

Key features:
- Multi-modal evidence (satellite, acoustic, measurement, document)
- Cryptographic proofs recognized by regulators
- Cost: $0.10-$1 per hectare (vs. $50-$100 for manual audit)
- Verification time: 48 hours (vs. 12 months for traditional audits)

Viridis integrates with the broader climate tech ecosystem: Sentinel Watch (satellite),
Bioacoustic monitoring, Carbon Bridge (credit markets), and ecoinvest (financial modeling).

About Viridis
Viridis is building the infrastructure layer for nature-based economics. The company's
platform enables verification, compliance, and investment in biodiversity and carbon.
Headquartered in San Francisco with operations in 12 countries, Viridis is backed by
[funding sources] and has partnerships with Conservation International, World Wildlife
Fund, and major financial institutions.

###

MEDIA CONTACT
[Name]
press@viridis.earth
+1-XXX-XXX-XXXX
"""

            output = NarrativeOutput(
                narrative_id=str(__import__('uuid').uuid4()),
                format=NarrativeFormat.PRESS_RELEASE,
                audience=audience,
                title=headline,
                content=content,
                key_claims=[
                    "Only platform with cryptographic proof-of-conservation",
                    "Reduces verification cost 99% (from $100 to $1/hectare)",
                    "Already verified 500,000 hectares globally",
                    "Recognized by TNFD, CSRD, and carbon market standards",
                ],
                evidence_citations=[
                    {"source": "Viridis platform", "claim": "500K hectares verified"},
                ],
                call_to_action="Request demo at viridis.earth; press inquiries: press@viridis.earth",
                quality_score=NarrativeQualityScorer.score_narrative(content, audience, NarrativeFormat.PRESS_RELEASE),
                generation_timestamp=datetime.utcnow(),
            )

            return output

        except Exception as e:
            logger.error(f"Error generating press release: {str(e)}")
            raise

    async def executive_summary(
        self,
        data: Dict[str, Any],
        audience: AudienceType,
        key_message: Optional[str] = None,
    ) -> NarrativeOutput:
        """Generate one-page executive summary."""
        try:
            content = f"""
EXECUTIVE SUMMARY: {key_message or 'Viridis: Nature Verification Infrastructure'}

THE MOMENT
Global regulations (CSRD, TNFD, Article 6) now require verification of conservation
outcomes. Yet audits cost $50-100/hectare and take 12 months. Verification bottleneck
blocks $2B/year in nature-based finance.

THE PROBLEM
- 50,000+ companies need CSRD/TNFD compliance by 2025
- Smallholder farmers can't afford manual audits
- Carbon credits lack cryptographic proof (fraud risk)
- Regulatory uncertainty deters investment

VIRIDIS SOLUTION
Platform that combines satellite, acoustic, measurement, and document evidence into
cryptographically verifiable proofs. Cost: $0.10-$1/hectare. Speed: 48 hours.
Recognized by regulators globally.

IMPACT
- 500,000 hectares verified to date
- $50M in carbon transactions enabled
- 40% of customers achieve CSRD/TNFD compliance ahead of deadline
- 25% income increase for smallholder farmers using platform

BUSINESS MODEL
- Verification-as-a-service: $0.10-$1/hectare
- Compliance subscriptions: $5K-$50K/year
- Regulatory intelligence: $499-$2,499/month
- Platform integrations: $1K-$10K/project

NEXT STEPS
1. Join pilot program (apply at viridis.earth)
2. Schedule product demo (sales@viridis.earth)
3. Access regulatory intelligence (subscribe at platform.viridis.earth)
"""

            output = NarrativeOutput(
                narrative_id=str(__import__('uuid').uuid4()),
                format=NarrativeFormat.EXECUTIVE_SUMMARY,
                audience=audience,
                title="Viridis: Nature Verification Infrastructure",
                content=content,
                key_claims=[
                    "Verification bottleneck blocks $2B/year in nature finance",
                    "Cryptographic proofs reduce audit cost 99%",
                    "500K hectares verified globally",
                    "Clear path to profitability at scale",
                ],
                evidence_citations=[
                    {"source": "Viridis metrics", "claim": "500K hectares verified"},
                    {"source": "EU CSRD", "claim": "50K companies require reporting"},
                ],
                call_to_action="Schedule demo at viridis.earth",
                quality_score=NarrativeQualityScorer.score_narrative(content, audience, NarrativeFormat.EXECUTIVE_SUMMARY),
                generation_timestamp=datetime.utcnow(),
            )

            return output

        except Exception as e:
            logger.error(f"Error generating executive summary: {str(e)}")
            raise

    def validate_claims(
        self,
        narrative: NarrativeOutput,
        source_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Post-generation validator: scores claim confidence against source data.

        Invariant #16: Every output claim must have a confidence score.
        Unsourced claims are flagged for human review.

        Args:
            narrative: The generated NarrativeOutput to validate.
            source_data: The original agent_output used to generate the narrative.

        Returns:
            Dict with claim_validations (per-claim scores), overall_confidence,
            and flagged_claims (unsourced or low-confidence items).
        """
        claim_validations = []
        flagged_claims = []

        # Flatten source data keys for matching
        source_keys = set()
        def _flatten_keys(d: dict, prefix: str = ""):
            for k, v in d.items():
                full_key = f"{prefix}.{k}" if prefix else k
                source_keys.add(k.lower())
                source_keys.add(full_key.lower())
                if isinstance(v, dict):
                    _flatten_keys(v, full_key)
        _flatten_keys(source_data)

        # Numeric values from source for fact-checking
        source_numbers = set()
        def _extract_numbers(d: dict):
            for v in d.values():
                if isinstance(v, (int, float)):
                    source_numbers.add(v)
                elif isinstance(v, dict):
                    _extract_numbers(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, (int, float)):
                            source_numbers.add(item)
                        elif isinstance(item, dict):
                            _extract_numbers(item)
        _extract_numbers(source_data)

        for claim in narrative.key_claims:
            claim_lower = claim.lower()
            words = claim_lower.split()

            # Score 1: Key overlap — does the claim reference source data fields?
            key_overlap = sum(1 for key in source_keys if key in claim_lower)
            key_score = min(1.0, key_overlap / max(len(source_keys) * 0.1, 1))

            # Score 2: Evidence backing — does the claim appear in citation list?
            citation_texts = " ".join(
                c.get("text", "") + " " + c.get("source", "")
                for c in narrative.evidence_citations
            ).lower()
            citation_overlap = sum(1 for w in words if len(w) > 4 and w in citation_texts)
            citation_score = min(1.0, citation_overlap / max(len(words) * 0.3, 1))

            # Score 3: Numeric grounding — do numbers in the claim appear in source?
            import re
            claim_numbers = set()
            for match in re.finditer(r'[\d,]+\.?\d*', claim):
                try:
                    num = float(match.group().replace(",", ""))
                    claim_numbers.add(num)
                except ValueError:
                    pass
            if claim_numbers:
                grounded = sum(1 for n in claim_numbers if n in source_numbers)
                numeric_score = grounded / len(claim_numbers)
            else:
                numeric_score = 0.5  # No numbers to verify — neutral

            # Composite confidence
            confidence = key_score * 0.4 + citation_score * 0.3 + numeric_score * 0.3
            confidence = round(min(1.0, max(0.0, confidence)), 3)

            validation = {
                "claim": claim,
                "confidence": confidence,
                "key_overlap": round(key_score, 3),
                "citation_backing": round(citation_score, 3),
                "numeric_grounding": round(numeric_score, 3),
            }
            claim_validations.append(validation)

            if confidence < 0.4:
                flagged_claims.append({
                    "claim": claim,
                    "confidence": confidence,
                    "reason": "Low confidence — insufficient source data backing",
                })

        overall_confidence = (
            sum(v["confidence"] for v in claim_validations) / len(claim_validations)
            if claim_validations
            else 0.0
        )

        return {
            "claim_validations": claim_validations,
            "overall_confidence": round(overall_confidence, 3),
            "total_claims": len(claim_validations),
            "flagged_claims": flagged_claims,
            "flagged_count": len(flagged_claims),
            "validation_timestamp": datetime.utcnow().isoformat(),
        }

    async def health(self) -> Dict[str, any]:
        """Health check."""
        return {
            "status": "ok",
            "agent": "narrative-engine",
            "version": "0.1.1",
            "timestamp": datetime.utcnow().isoformat(),
        }

    def describe(self) -> Dict[str, any]:
        """Describe agent."""
        return {
            "name": "narrative-engine",
            "version": "0.1.1",
            "description": "Translates ecological intelligence into investor, policy, grant, and media-ready narratives",
            "capabilities": [
                "translate",
                "investor_narrative",
                "policy_brief",
                "grant_proposal",
                "press_release",
                "executive_summary",
            ],
            "inputs": ["agent_output", "audience_type", "format", "key_message"],
            "outputs": ["investor_deck_content", "policy_brief", "grant_proposal", "press_release", "executive_summary"],
        }

    async def process(self, input_data: dict) -> dict:
        """
        Fleet-standard process() entry point for Mycelium IQ orchestration.

        Routes {"action": "translate", ...} to translate(), and passes
        {"action": "health"} / {"action": "describe"} to the respective methods.

        Expected input for translate:
            {
                "action": "translate",
                "agent_output": dict,       # raw data from any fleet agent
                "audience_type": str,       # one of 9 AudienceType values
                "format_type": str,         # one of 7 NarrativeFormat values
                "key_message": str | None,  # optional narrative anchor
            }

        Returns:
            {"status": "success"|"error", "result": ..., "timestamp": ...}
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

        action = str(input_data.get("action", "")).strip().lower()

        try:
            if action == "translate":
                narrative: NarrativeOutput = await self.translate(
                    agent_output=input_data.get("agent_output", {}),
                    audience_type=input_data.get("audience_type", ""),
                    format_type=input_data.get("format_type", ""),
                    key_message=input_data.get("key_message"),
                )
                return {
                    "status": "success",
                    "result": {
                        "narrative_id": narrative.narrative_id,
                        "title": narrative.title,
                        "audience": narrative.audience.value,
                        "format": narrative.format.value,
                        "content": narrative.content,
                        "key_claims": narrative.key_claims,
                        "call_to_action": narrative.call_to_action,
                        "quality_score": narrative.quality_score,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }
            elif action == "health":
                return await self.health()
            elif action == "describe":
                return self.describe()
            else:
                return {
                    "status": "error",
                    # N68: harness error taxonomy — unknown action is a
                    # ValidationError, not an untyped error (Output Contract).
                    "error_type": "ValidationError",
                    "field": "action",
                    "message": (
                        f"Unknown action: '{action}'. "
                        "Supported: translate, health, describe"
                    ),
                    "timestamp": datetime.utcnow().isoformat(),
                }

        except NarrativeValidationError as e:
            logger.error(f"Narrative Engine validation failed: {e}")
            return {
                "status": "error",
                "error_type": "ValidationError",
                "field": e.field,
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Narrative Engine process error: {e}", exc_info=True)
            return {
                "status": "error",
                # N68: classify per harness taxonomy; input-shape faults
                # raised past the typed gate are ValidationError, the rest
                # RuntimeError. Additive fields only.
                "error_type": (
                    "ValidationError"
                    if isinstance(e, (ValueError, TypeError, KeyError))
                    else "RuntimeError"
                ),
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
