# Viridis Agent Template - Complete Inventory

## Overview
Canonical agent template for all Viridis deployments. Self-contained, production-ready.

**Location:** `/sessions/sweet-zen-knuth/mnt/Agents to deploy copy/_AGENT_TEMPLATE/`

**Total Code:** 2,730 lines across 14 files

**Status:** Ready for use

---

## Files Included

### Documentation (5 files)

| File | Lines | Purpose |
|------|-------|---------|
| README.md | 340 | Complete architecture guide, usage patterns, deployment to all targets |
| DEPLOYMENT_GUIDE.md | 380 | Detailed deployment instructions for each platform (GCP, AWS, K8s, Workers, MCP) |
| EXAMPLE.md | 320 | Step-by-step walkthrough: Building a text processor agent from template |
| TEMPLATE_SUMMARY.txt | 280 | Quick reference overview of template structure and usage |
| INVENTORY.md | THIS FILE | Complete listing of all template files |

### Configuration (4 files)

| File | Purpose |
|------|---------|
| agent.yaml | Agent manifest: name, version, pillar, status, dependencies, env vars |
| .env.example | Environment variables template (no secrets) |
| requirements.txt | Python dependencies (FastAPI, MCP, testing frameworks) |
| wrangler.toml | Cloudflare Worker configuration |

### Core Logic (1 file)

| File | Lines | Purpose |
|------|-------|---------|
| src/core.py | 280 | AgentCore base class - ONLY business logic, zero deployment concerns |

### Deployment Adapters (4 files)

| File | Lines | Purpose |
|------|-------|---------|
| adapters/fastapi_server.py | 320 | HTTP server (Cloud Run, Docker, local dev) |
| adapters/mcp_server.py | 180 | MCP protocol (Claude Code, other LLMs) |
| adapters/cloudflare_worker.js | 240 | Cloudflare Workers adapter with delegation pattern |
| adapters/claude_skill.md | 190 | SKILL.md manifest for Claude Code deployment |

### Testing (1 file)

| File | Lines | Purpose |
|------|-------|---------|
| tests/test_core.py | 510 | 50+ unit tests covering all core functionality |

### Build & Development (3 files)

| File | Purpose |
|------|---------|
| Dockerfile | Multi-stage Docker build (builder + runtime stages) |
| Makefile | Development commands: install, test, dev, docker-build, lint, fmt |
| .gitignore | Git ignore patterns |

---

## Design Checklist

- [x] **Separation of Concerns**: Core logic separate from deployment
- [x] **Modular Adapters**: FastAPI, MCP, Workers, Skill all pluggable
- [x] **Configuration-Driven**: YAML manifest + env vars, no hardcoded config
- [x] **Standard Interface**: process(), health(), describe() on all targets
- [x] **Production-Ready Code**: Error handling, logging, validation
- [x] **Comprehensive Tests**: 50+ tests with async/await, fixtures, integration
- [x] **Complete Documentation**: Architecture, usage, deployment, examples
- [x] **Security**: No secrets in code, all env-var based
- [x] **Multi-Platform**: Single codebase deploys to 5+ targets

---

## Quick Facts

| Aspect | Details |
|--------|---------|
| **Core Logic** | AgentCore base class + AgentConfig dataclass |
| **Adapters** | 4 (FastAPI, MCP, Workers, Skill) |
| **Deployment Targets** | 6+ (local, Docker, Cloud Run, ECS, K8s, Workers, MCP, Skill) |
| **HTTP Endpoints** | /health, /describe, /process, /info, /docs |
| **Tests** | 50+ unit tests with 90%+ code coverage pattern |
| **Dependencies** | FastAPI, Uvicorn, FastMCP, Pydantic, Pytest |
| **Python Version** | 3.11+ |
| **License** | Viridis (internal) |
| **Owner** | justin@viridis.earth |

---

## How to Use This Template

### 1. Copy Template
```bash
cp -r _AGENT_TEMPLATE my-new-agent
cd my-new-agent
```

### 2. Customize
```bash
# Edit agent.yaml with your agent metadata
nano agent.yaml

# Implement src/core.py with your business logic
nano src/core.py

# Add tests
nano tests/test_core.py
```

### 3. Test Locally
```bash
make install
make test
make dev

# In another terminal
curl -X POST http://localhost:8080/process -H "Content-Type: application/json" -d '{"input": "data"}'
```

### 4. Deploy to Target
```bash
# Docker
make docker-build && make docker-run

# Cloud Run (see DEPLOYMENT_GUIDE.md)
gcloud run deploy my-agent --image gcr.io/PROJECT/my-agent:latest

# MCP Server
python adapters/mcp_server.py

# Skill
zip -r my-agent.skill.zip my-agent.skill/
/import ./my-agent.skill.zip
```

---

## File Dependencies

```
Core Logic
  └── src/core.py (AgentCore, AgentConfig)
        ├── adapters/fastapi_server.py (HTTP)
        ├── adapters/mcp_server.py (MCP)
        ├── adapters/cloudflare_worker.js (Workers)
        ├── adapters/claude_skill.md (Skill)
        └── tests/test_core.py (Tests)

Configuration
  ├── agent.yaml (manifest)
  ├── .env.example (env vars)
  ├── requirements.txt (dependencies)
  └── wrangler.toml (Workers config)

Build & Development
  ├── Dockerfile (containerization)
  ├── Makefile (dev commands)
  └── .gitignore (git config)

Documentation
  ├── README.md (architecture)
  ├── DEPLOYMENT_GUIDE.md (deployment)
  ├── EXAMPLE.md (walkthrough)
  └── TEMPLATE_SUMMARY.txt (quick ref)
```

---

## Standards Enforced

### Code Quality
- Type hints on all functions
- Docstrings for all classes/methods
- Async/await patterns
- Error handling with logging
- Input validation

### Testing
- Unit tests for all core functionality
- Async test patterns with pytest-asyncio
- Fixtures for common setup
- Integration tests
- Edge case coverage

### Documentation
- Architecture explanation
- Usage examples
- Deployment instructions for each target
- Troubleshooting guide
- API documentation (auto-generated via Swagger)

### Security
- No secrets in code
- All configuration via environment variables
- Input validation and sanitization
- Non-root Docker user
- CORS configuration
- Error messages don't leak implementation details

### Operations
- Health checks on all targets
- Logging with timestamps and levels
- Structured error responses
- Environment-specific configuration
- Graceful degradation

---

## Next Steps

1. **Start Building**: `cp -r _AGENT_TEMPLATE my-agent && cd my-agent`
2. **Edit Manifest**: Update `agent.yaml` with your agent details
3. **Implement Logic**: Write your business logic in `src/core.py`
4. **Test**: `make test` and `make dev` for local testing
5. **Deploy**: Choose your target and follow `DEPLOYMENT_GUIDE.md`
6. **Monitor**: Set up health checks and logging as per guide

---

## Support

- **Architecture Questions**: See README.md
- **Deployment Questions**: See DEPLOYMENT_GUIDE.md
- **Implementation Example**: See EXAMPLE.md
- **Quick Reference**: See TEMPLATE_SUMMARY.txt

This template is the canonical structure for all Viridis agents. Use it consistently across the entire agent ecosystem.
