# Viridis Agent Template - Start Here

Welcome to the canonical agent template for Viridis. This is your starting point for building agents that deploy to multiple platforms with zero code duplication.

## What Is This?

A complete, production-ready agent framework that:
- Separates **business logic** from **deployment concerns**
- Deploys the **same code** to FastAPI, Docker, Cloud Run, Kubernetes, Cloudflare Workers, MCP, and Claude Code
- Provides **standard interfaces** for discovery, composition, and monitoring
- Includes **comprehensive tests**, **complete documentation**, and **security best practices**

## 5-Minute Quick Start

```bash
# 1. Copy the template
cp -r _AGENT_TEMPLATE my-agent
cd my-agent

# 2. Edit your agent metadata
nano agent.yaml

# 3. Implement your business logic
nano src/core.py

# 4. Test it
make install
make test
make dev

# 5. In another terminal, test the endpoint
curl -X POST http://localhost:8080/process \
  -H "Content-Type: application/json" \
  -d '{"your": "input"}'
```

That's it. You now have a working agent running on FastAPI, with auto-generated Swagger docs at `http://localhost:8080/docs`.

## Where to Go From Here

### Reading Order

1. **This file (INDEX.md)** - Overview and quick start (you are here)
2. **TEMPLATE_SUMMARY.txt** - 2-minute reference of structure
3. **README.md** - Complete architecture and usage patterns
4. **EXAMPLE.md** - Concrete walkthrough: Build a text processor agent
5. **DEPLOYMENT_GUIDE.md** - Deploy to every platform (GCP, AWS, K8s, Workers, MCP, Skill)

### By Use Case

**I want to build a new agent:**
→ Follow EXAMPLE.md step-by-step

**I want to understand the architecture:**
→ Read README.md sections "Design Philosophy" and "Directory Structure"

**I want to deploy to production:**
→ See DEPLOYMENT_GUIDE.md for your specific platform

**I want a quick reference:**
→ TEMPLATE_SUMMARY.txt has a concise overview

**I want to know what files are included:**
→ INVENTORY.md lists everything with explanations

## The Template Structure

```
_AGENT_TEMPLATE/
├── agent.yaml                 # Your agent's metadata
├── src/core.py               # YOUR CODE GOES HERE (business logic)
├── adapters/
│   ├── fastapi_server.py     # (don't edit) HTTP deployment
│   ├── mcp_server.py         # (don't edit) MCP deployment
│   ├── cloudflare_worker.js  # (don't edit) Workers deployment
│   └── claude_skill.md       # (don't edit) Skill deployment
├── tests/test_core.py        # Add tests here
├── Dockerfile                # (don't edit) Docker build
├── Makefile                  # Run `make help` for commands
├── requirements.txt          # Python dependencies
└── README.md, DEPLOYMENT_GUIDE.md, EXAMPLE.md
   └── Full documentation
```

## Core Concept: Your Code vs. The Template

You write:
- **agent.yaml** - What is your agent?
- **src/core.py** - What does your agent do?
- **tests/test_core.py** - How do you test it?

The template provides:
- **Adapters** - HTTP, MCP, Workers, Skill endpoints (pre-built)
- **Build system** - Docker, Makefile (pre-configured)
- **Documentation** - Guides for every platform (ready to use)

## Key Design Patterns

### 1. Standard Interface
Every agent, everywhere, implements:

```python
async def process(input_data: dict) -> dict
async def health() -> dict
def describe() -> dict
```

Whether deployed to FastAPI, MCP, Workers, or Skill, your code is called the same way.

### 2. Modular Adapters
All adapters import from your `src/core.py`:

```python
from src.core import MyAgent, AgentConfig

# In adapters/fastapi_server.py
agent = MyAgent(config)

# In adapters/mcp_server.py
agent = MyAgent(config)

# In adapters/claude_skill.md
agent = MyAgent(config)
```

Zero code duplication. One change to core logic = updated everywhere.

### 3. Configuration-Driven
No hardcoded values. Everything via YAML + environment variables:

```bash
# Local
AGENT_NAME=agent LOG_LEVEL=DEBUG make dev

# Docker
docker run -e AGENT_NAME=agent -e LOG_LEVEL=INFO agent:latest

# Cloud Run
gcloud run deploy agent --set-env-vars AGENT_NAME=agent,LOG_LEVEL=INFO
```

## The Four Pillars

### Separation of Concerns
- **src/core.py**: Pure business logic (no HTTP, no deployment)
- **adapters/**: Thin glue layers (HTTP, MCP, Workers, Skill)
- **No coupling**: Adapters are interchangeable

### Standard Interface
- **process()**: Main entry point
- **health()**: Status check
- **describe()**: Capabilities
- **Same methods** on all platforms

### Configuration-Driven
- **agent.yaml**: Manifest with metadata
- **Environment variables**: All secrets and config
- **No hardcoded values**: Code is completely portable

### Production-Ready
- **Tests**: 50+ unit tests included
- **Logging**: Structured, with levels
- **Error handling**: Graceful degradation
- **Security**: No secrets in code, validation on all inputs

## Deployment Targets

The same code runs on all of these:

| Target | Best For | Start Here |
|--------|----------|-----------|
| Local (FastAPI) | Development | `make dev` |
| Docker | Any cloud | `make docker-build && docker-run` |
| Cloud Run | Serverless GCP | DEPLOYMENT_GUIDE.md: "Cloud Run" |
| AWS ECS | Serverless AWS | DEPLOYMENT_GUIDE.md: "ECS" |
| Kubernetes | Large scale | DEPLOYMENT_GUIDE.md: "Kubernetes" |
| Cloudflare Workers | Edge computing | DEPLOYMENT_GUIDE.md: "Workers" |
| MCP Server | Claude Code | DEPLOYMENT_GUIDE.md: "MCP" |
| Claude Skill | Claude Code | DEPLOYMENT_GUIDE.md: "Skill" |

## Real Example

Build a text processor agent from template:

```python
# src/core.py
class TextProcessor(AgentCore):
    async def process(self, data: dict) -> dict:
        text = data["text"]
        operation = data.get("operation", "upper")
        
        if operation == "upper":
            result = text.upper()
        elif operation == "lower":
            result = text.lower()
        else:
            raise ValueError(f"Unknown: {operation}")
        
        return self._wrap_result(data={"result": result})
    
    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "capabilities": ["uppercase", "lowercase"],
            "inputs": {"text": "str", "operation": "str"},
            "outputs": {"result": "str"}
        }
```

Deploy it:

```bash
# Local dev
make dev
curl -X POST http://localhost:8080/process -d '{"text":"hello","operation":"upper"}'
# Response: {"status": "ok", "data": {"result": "HELLO"}}

# Docker
make docker-build && make docker-run
# Same endpoint available on :8080

# Cloud Run
docker push gcr.io/PROJECT/text-processor:latest
gcloud run deploy text-processor --image gcr.io/PROJECT/text-processor:latest
# Available at https://text-processor-xxx.run.app

# MCP (Claude Code)
python adapters/mcp_server.py
# Register in Claude Code settings

# Skill
zip -r text-processor.skill.zip text-processor.skill/
# /import ./text-processor.skill.zip in Claude Code
```

Same code. Six different deployment targets.

## Common Questions

**Q: How do I add dependencies?**
A: Add to `requirements.txt`, then `pip install -r requirements.txt`

**Q: How do I handle authentication?**
A: Use environment variables for API keys. Never hardcode them.

**Q: Can I call another agent?**
A: Yes, import its core module or call via HTTP: `await client.post("http://agent:8080/process", ...)`

**Q: How do I add monitoring?**
A: Log at INFO/ERROR level in your `process()` method. All adapters capture logs.

**Q: What's the smallest agent I can build?**
A: ~20 lines of code in `src/core.py`. Everything else is provided.

## Next Steps

1. **Copy the template**: `cp -r _AGENT_TEMPLATE my-agent && cd my-agent`
2. **Edit agent.yaml** with your agent's metadata
3. **Implement src/core.py** with your business logic
4. **Test**: `make install && make test && make dev`
5. **Deploy**: Pick a target from DEPLOYMENT_GUIDE.md

---

## Documentation Map

| File | Purpose | Read Time |
|------|---------|-----------|
| **INDEX.md** (this file) | Overview and quick start | 5 min |
| **TEMPLATE_SUMMARY.txt** | Structure reference | 2 min |
| **README.md** | Complete architecture guide | 15 min |
| **EXAMPLE.md** | Build a concrete agent | 20 min |
| **DEPLOYMENT_GUIDE.md** | Deploy to every platform | 30 min |
| **INVENTORY.md** | Complete file listing | 5 min |

---

## Philosophy

This template encodes Viridis agent best practices:

1. **Write once, deploy everywhere**: Single codebase, any platform
2. **Clear separation**: Business logic separate from infrastructure
3. **Configuration over code**: YAML + env vars, no hardcoding
4. **Standard interfaces**: Discover, compose, and monitor agents
5. **Production ready**: Tests, logging, error handling, security built in
6. **Minimal boilerplate**: Focus on your logic, not framework code

Use this template for all new Viridis agents. It maintains consistency, prevents mistakes, and accelerates development.

---

**Ready?** Start here: `cp -r _AGENT_TEMPLATE my-agent && cd my-agent && nano agent.yaml`
