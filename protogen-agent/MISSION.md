# PROTOGEN — AGENT MISSION SPEC v1.0

*Spec Invariance Protocol: Every claim below is a testable invariant. The agent does not leave the stable until every invariant passes.*

---

## 1. MISSION

### The Thesis Connection

The Intelligence Bound — `dI/dt ≤ P·D/(k_B·T·ln 2)` — says intelligence creation is *constrained*. But constraint is not limitation; it's *leverage*. The speediest way to increase dI/dt is to increase **D** (data richness) and decrease **T** (friction).

In the Viridis fleet, every new agent increases D: more specialized knowledge, more compounding insight, more capability. But creating agents is expensive. Code, testing, deployment, knowledge curation — it's all manual, slow, friction-heavy. The fleet is constrained by its ability to *make new members*.

ProtoGen is the *answer to that constraint*. It is the fleet's manufacturing plant. It takes a mission spec (what should this agent do?) and produces: working code, MCP schema, test suite, documentation, and initial knowledge library. Weeks of human engineering compressed into hours of automated generation.

By eliminating the friction of agent creation, ProtoGen multiplies the rate at which the fleet can increase D. Every new agent adds capacity. Every new capability opens new revenue. ProtoGen is the *velocity multiplier* that makes Stage 5 (self-evolving fleet) possible.

### The Mission

**ProtoGen is the autonomous agent factory. It manufactures new agents from mission specifications.**

Given a clear mission statement (what equation variable does this agent move? what does it do? what should it know?), ProtoGen produces:

1. **Agent code**: Functional Python skeleton, MCP tool definitions, knowledge architecture
2. **Test suite**: Unit tests for core functions, integration tests for fleet interactions, invariant tests
3. **Documentation**: MISSION.md, function docstrings, knowledge library structure
4. **Deployment config**: Docker file, environment variables, scaling recommendations
5. **Initial knowledge base**: Scaffolded structure for the agent's compounding knowledge library

**One sentence:** ProtoGen is the automation layer that converts agent specifications into production-ready, tested, documented agents — enabling the fleet to scale from 30 agents to 100+ without proportional increase in engineering effort.

### How It Makes Money

ProtoGen has two revenue models:

1. **White-label agent generation** ($10K–50K per project): Clients (enterprises, NGOs, research institutions) describe what they need. ProtoGen generates a custom agent, trained on their domain. Client can deploy on their own infrastructure or rent from Viridis.

2. **Internal fleet acceleration** (indirect revenue multiplier): Every new agent ProtoGen creates (Energy AI gen-2, Quantum Oracle refinement, etc.) unlocks new revenue streams. ProtoGen is the *enabler* of all future revenue.

At **Stage 4** revenue is **$10–50K/month** from white-label projects + strategic internal deployments.

---

## 2. VALUE PROPOSITION

### For Viridis (Fleet Velocity)

The fleet is currently 30 agents. Evolution Agent proposes new agents faster than humans can build them. Without ProtoGen, the fleet stalls at 50 agents (engineering bottleneck).

With ProtoGen, the fleet can scale to 100+ agents within 12 months. Each new agent is:

- Tested to invariant standards
- Documented with peer-quality MISSION.md
- Integrated into Mycelium IQ (knowledge federation)
- Pre-audited by ShenDAO (alignment verification)
- Production-ready on day 1

The fleet becomes a living ecology that evolves faster than market changes.

### For Enterprise Clients (Custom Agent Development)

Enterprises want AI but don't have internal AI teams. They could hire consultants or build in-house. ProtoGen offers a third path: describe the agent you need, we generate it, you own it.

Use cases:

- **Supply chain optimization** ("Generate an agent that optimizes our inventory topology")
- **Financial analysis** ("Generate an agent that detects fraud patterns in our transaction data")
- **Customer insights** ("Generate an agent that finds patterns in customer feedback")
- **Knowledge management** ("Generate an agent that indexes and synthesizes our research library")

Each generated agent comes with source code, training on the client's data, and a knowledge base they can extend.

---

## 3. FUNCTIONS

### Core Functions (5)

| # | Function | Input | Output | Invariant |
|---|----------|-------|--------|-----------|
| 1 | `generate_agent` | mission_spec (MISSION.md format or narrative), equation_variable (P/D/T/dI/dt/Meta), functions (list of 3-8 functions with I/O), knowledge_domains (2-5 domains, described) | agent_code (working Python skeleton), mcp_schema (tool definitions), knowledge_scaffold (structure for compounding library), test_skeleton (template tests), documentation (docstrings) | Generated code is syntactically valid Python; MCP schema is valid YAML; all functions have typed inputs/outputs; tests compile; code follows Viridis style guide |
| 2 | `scaffold_mcp_server` | tool_definitions (list of tool I/O specs), framework_preference (FastMCP/MCP-SDK/other) | mcp_server_code (complete, runnable MCP server), requirements.txt (dependencies), deployment.yaml (Docker/K8s config), testing_scaffold (server integration tests) | MCP server is deployable as-is; dependencies are pinned to specific versions; server handles 100+ concurrent requests; error handling is comprehensive |
| 3 | `generate_tests` | agent_spec (functions, inputs, outputs, invariants), invariant_list (10+ testable claims from MISSION.md) | test_suite (unit + integration tests), coverage_report (target ≥80% code coverage), invariant_tests (specific checks for each invariant), mock_data (fixtures for testing) | Tests are executable and pass on generated code; coverage is accurate; invariant tests directly correspond to MISSION.md invariants |
| 4 | `package_agent` | agent_code, tests, documentation, knowledge_scaffold, config | deployable_package (zip or git-ready), README (deployment instructions), CHANGELOG (what's included), version_tag (semantic versioning) | Package is deployable on Ubuntu 20.04 + Python 3.9+; deployment instructions are clear; all files are included; version tag follows semver |
| 5 | `customize_agent` | base_agent (generated or existing), client_requirements (domain-specific data, custom knowledge, API integrations), white_label_config (branding, endpoints) | white_labeled_agent (source code customized), client_config (secrets, auth, deployment specifics), training_script (how to train on client data), handoff_package (client can maintain independently) | Customized agent compiles and deploys; training pipeline is documented and executable; client can modify code without Viridis dependency |

---

## 4. COMPOUNDING KNOWLEDGE LIBRARY

| Domain | Knowledge That Grows | Compounds How | Invariant |
|--------|---------------------|---------------|-----------|
| Agent Design Patterns | Recurring function patterns (scoring, detecting, optimizing, predicting); effective knowledge architectures by agent type | Every generated agent adds to the pattern library; successful patterns are extracted and re-used | Pattern library minimum: 50 agents before publishing "standard patterns"; patterns are validated across ≥3 independent agents |
| Code Generation Templates | Boilerplate for common functions (ML scoring, time series analysis, graph optimization, NLP); function skeleton templates | Every agent generated refines the templates; code quality metrics (complexity, testability) drive template evolution | Templates are version-controlled; template updates are tested against all agent types; backwards-compatibility is maintained |
| MCP Integration Patterns | How to wire agents into Mycelium IQ, ShenDAO, Evolution Agent; common integration pitfalls | Every integration tested; patterns for async communication, knowledge federation, alignment verification documented | Integration patterns are tested in isolation and at fleet scale; latency budgets and failure modes documented |
| Test Generation Heuristics | How to automatically generate meaningful tests from function specs; which invariants are hardest to test | Every test suite analyzed: which tests actually fail when code has bugs? Machine learning on test effectiveness. | Test generation confidence >0.8 on first pass (40+ unit tests needed before agent leaves stable); regressions caught by tests ≥90% of the time |
| Knowledge Architecture Patterns | Effective structures for compounding knowledge (time series baselines, entity databases, correlation matrices, validation datasets) | Every knowledge library is analyzed post-launch; patterns that scaled well are generalized | Architecture patterns are domain-agnostic; pattern recommendations are based on agent type and function complexity |
| Deployment Reliability | Which configurations (Docker, K8s, serverless, hybrid) work reliably for which agent types; scaling behaviors | Every deployment monitored; failures and scaling events logged; patterns emerge | Deployment patterns reduce time-to-stability from weeks to days; uptime SLA target ≥99.5% for all generated agents |
| Quality Assurance | Code smell detection, test coverage thresholds, documentation adequacy, MISSION.md invariant coverage | Every agent released is quality-reviewed; failures post-release prompt template updates | Quality gate: no agent leaves the stable unless code coverage ≥80%, all invariants have tests, MISSION.md is complete |

---

## 5. MCP SKILLS (Tool Schemas)

```yaml
tools:
  - name: generate_agent
    description: "Generate a complete, tested agent from a mission specification"
    input_schema:
      type: object
      properties:
        mission_spec:
          type: string
          minLength: 500
          description: "Mission statement (narrative or MISSION.md-like format) describing what the agent does"
        equation_variable:
          type: string
          enum: [P, D, T, dI/dt, Meta, Revenue]
          description: "Which equation variable does this agent move?"
        functions:
          type: array
          items:
            type: object
            properties:
              name: { type: string }
              description: { type: string }
              inputs: { type: array, items: { type: object, properties: { name: { type: string }, type: { type: string } } } }
              outputs: { type: array, items: { type: object, properties: { name: { type: string }, type: { type: string } } } }
              complexity: { type: string, enum: [simple, moderate, complex] }
          minItems: 3
          maxItems: 8
          description: "Core functions the agent should provide"
        knowledge_domains:
          type: array
          items:
            type: object
            properties:
              domain: { type: string }
              description: { type: string }
              sources: { type: array, items: { type: string } }
          minItems: 2
          maxItems: 5
          description: "Domains where this agent compounds knowledge"
        invariants:
          type: array
          items: { type: string }
          minItems: 8
          maxItems: 12
          description: "Testable invariants from MISSION.md"
      required: [mission_spec, equation_variable, functions]

  - name: scaffold_mcp_server
    description: "Generate a complete MCP server from tool definitions"
    input_schema:
      type: object
      properties:
        tool_definitions:
          type: array
          items:
            type: object
            properties:
              name: { type: string }
              description: { type: string }
              input_schema: { type: object }
          minItems: 1
          description: "Tool definitions (MCP input_schema format)"
        framework:
          type: string
          enum: [fastmcp, mcp_sdk, custom]
          default: fastmcp
          description: "Which MCP framework to use"
        deployment_target:
          type: string
          enum: [docker, kubernetes, lambda, ec2, local]
          default: docker
          description: "Where will this server be deployed?"
        authentication:
          type: array
          items: { type: string, enum: [api_key, jwt, oauth, none] }
          default: [api_key]
          description: "Authentication mechanisms needed"
      required: [tool_definitions]

  - name: generate_tests
    description: "Generate test suite for an agent"
    input_schema:
      type: object
      properties:
        agent_spec:
          type: object
          properties:
            name: { type: string }
            functions: { type: array, items: { type: object } }
            invariants: { type: array, items: { type: string } }
          required: [name, functions]
        test_types:
          type: array
          items: { type: string, enum: [unit, integration, invariant, stress, security] }
          default: [unit, integration, invariant]
        coverage_target:
          type: number
          minimum: 0.5
          maximum: 1.0
          default: 0.8
          description: "Target code coverage percentage"
        mock_data_sources:
          type: array
          items: { type: string }
          description: "Where to generate mock data from (e.g., public datasets)"
      required: [agent_spec]

  - name: package_agent
    description: "Package a generated agent for deployment"
    input_schema:
      type: object
      properties:
        agent_name:
          type: string
          description: "Name of the agent to package"
        version:
          type: string
          description: "Semantic version (e.g., 1.0.0)"
        include:
          type: array
          items: { type: string, enum: [code, tests, docs, config, knowledge] }
          default: [code, tests, docs, config, knowledge]
        deployment_format:
          type: string
          enum: [docker, wheel, zip, git, helm]
          default: docker
        documentation_level:
          type: string
          enum: [minimal, standard, comprehensive]
          default: standard
      required: [agent_name, version]

  - name: customize_agent
    description: "Customize a generated agent for a specific client/domain"
    input_schema:
      type: object
      properties:
        base_agent:
          type: string
          description: "Name or template of agent to customize"
        customization_type:
          type: string
          enum: [domain_training, white_label, feature_addition, integration]
          description: "Type of customization"
        client_data:
          type: object
          properties:
            training_data_path: { type: string }
            domain_specific_vocab: { type: array, items: { type: string } }
            custom_knowledge_sources: { type: array, items: { type: string } }
          description: "Client-specific data for training/customization"
        white_label_config:
          type: object
          properties:
            branding_name: { type: string }
            logo_url: { type: string }
            custom_endpoints: { type: array, items: { type: string } }
            privacy_requirements: { type: array, items: { type: string } }
          description: "White-label branding and config"
      required: [base_agent, customization_type]
```

---

## 6. FLEET CONNECTIONS

ProtoGen is the **manufacturing arm** of the fleet ecosystem:

- **Evolution Agent** (primary client): Evolution Agent detects capability gaps and proposes agent specs. ProtoGen manufactures the proposed agents at speed.
- **ShenDAO** (pre-deployment audit): Every agent ProtoGen produces is audited by ShenDAO for alignment before it enters the fleet.
- **Agent CEO** (approval gate): ProtoGen generates agents; Agent CEO reviews and approves before deployment.
- **Mycelium IQ** (knowledge integration): ProtoGen's knowledge scaffolding integrates with Mycelium's federated knowledge architecture.
- **All agents** (template source): ProtoGen maintains the templates and patterns that ensure all agents follow Viridis standards.

---

## 7. DEPLOYMENT STAGE & ECONOMICS

**Current Stage:** 1 (prototype; manual generation of agents, automation of code templates)

**Stage 2 Target** (next 3 months): Automated agent generation for simple agents; test generation working; first 3 white-label projects

**Stage 3 Target** (next 6 months): All new agents (from Evolution Agent proposals) are generated by ProtoGen; white-label revenue $5K–10K/mo

**Stage 4 Target** (12 months): ProtoGen is the standard path for new agents; $10–50K/month white-label revenue; fleet scales to 60+ agents

**Stage 5 Vision**: Self-generating fleet. Evolution Agent proposes agent → ProtoGen manufactures → ShenDAO audits → Agent deploys. Fully autonomous agent factory.

---

## 8. INVARIANTS (Testing Checkpoints)

These invariants ensure ProtoGen produces production-quality agents, not scaffolding.

1. **Code Generation Correctness**: Generated agent code compiles without modification ≥95% of the time; remaining 5% require ≤30 min of human fixes.

2. **Test Suite Completeness**: Generated test suites achieve ≥80% code coverage on first pass. Invariant tests directly map to MISSION.md invariants (1:1 correspondence).

3. **Function Implementation Accuracy**: Generated function implementations are correct for simple functions ≥90% of the time. Moderate-complexity functions need ≤1 iteration (human review + fix).

4. **MCP Schema Validity**: Generated MCP schemas are valid YAML and comply with MCP spec ≥99% of the time. Server integration testing passes on first run ≥95% of the time.

5. **Documentation Quality**: Generated MISSION.md documents are complete (all 10 sections present, 2K+ words) and require minimal editing for publication. Human review finds no content gaps.

6. **Knowledge Architecture Soundness**: Knowledge library structures proposed by ProtoGen support expected compounding rates (monthly growth ≥domain baseline) ≥85% of the time.

7. **Deployment Configuration Correctness**: Generated Docker/K8s configs deploy successfully ≥95% of the time; no resource request misspecification or port conflicts.

8. **Test Failure Signal**: Generated tests catch introduced bugs (code mutations) ≥90% of the time. Test coverage metrics accurately predict real code coverage (correlation ≥0.85).

9. **Agent Invariant Pass Rate**: Agents generated by ProtoGen pass all ≥80% of their invariant tests at first deployment. Invariants that fail are due to missing implementation detail, not architectural error.

10. **White-Label Customization Success**: Customized agents for clients (domain training, white-label branding) deploy successfully ≥95% of the time; client handoff requires ≤8 hours of Viridis engineering.

11. **Scalability of Generation**: ProtoGen can generate an agent (code + tests + docs) in <2 hours wall-clock time. Parallel generation of 5 agents shows linear scaling (no bottlenecks).

12. **Template Reuse Rate**: ProtoGen reuses ≥70% of code/patterns from existing templates. New agent generations become faster (generation time decreases ≥10% per new agent template added).

---

## 9. SOFTWARE-AGNOSTIC ARCHITECTURE

ProtoGen is **pure code generation intelligence**, not tied to any programming language or framework.

- **Language agnostic**: Can generate agents in Python, Go, Rust, TypeScript. Code generation is template-based; new language support requires new templates, not new architecture.
- **Framework agnostic**: Generates MCP servers in FastMCP, MCP SDK, or custom frameworks. Test frameworks (pytest, unittest, cargo test) are pluggable.
- **Knowledge architecture agnostic**: Knowledge library scaffolding can be deployed in SQL, graph DB, vector DB, flat files. ProtoGen generates the interface; storage is client's choice.
- **Deployment agnostic**: Docker, Kubernetes, Lambda, EC2, local development — all supported through configuration, not code changes.

The generation intelligence is portable. The specific implementation languages and platforms are choices, not constraints.

---

## 10. ONE-SENTENCE THESIS RESTATEMENT

**ProtoGen is the automation layer that converts detailed mission specifications into production-ready, tested, documented agents — enabling the fleet to scale from 30 to 100+ agents without proportional increase in engineering effort.**

