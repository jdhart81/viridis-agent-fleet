# Viridis Agent Template

This is the canonical template structure for all Viridis agents. It enforces modular design, separation of concerns, and deployment flexibility.

## Design Philosophy

- **Core Logic First**: Business logic lives in `src/core.py` — completely decoupled from deployment infrastructure
- **Modular Adapters**: Deploy the same agent to Cloudflare Workers, Docker/FastAPI, MCP Server, or Claude Code Skill via pluggable adapters
- **Configuration-Driven**: All configuration via YAML manifest and environment variables — no hardcoded secrets or deployment-specific logic
- **Standard Interface Contract**: Every agent exports the same core methods: `process()`, `health()`, `describe()`

## Directory Structure

```
my-agent/
├── README.md                      # This file
├── agent.yaml                     # Agent manifest: metadata, dependencies, ports
├── .env.example                   # Template environment variables (no secrets)
├── src/
│   └── core.py                    # Core logic — ONLY domain business logic here
├── adapters/
│   ├── cloudflare_worker.js       # Cloudflare Workers adapter
│   ├── fastapi_server.py          # FastAPI/Docker adapter
│   ├── mcp_server.py              # MCP Server adapter (FastMCP)
│   └── claude_skill.md            # Claude Code Skill adapter (SKILL.md format)
├── tests/
│   └── test_core.py               # Unit tests for core logic
├── Dockerfile                     # Multi-stage Docker build
└── wrangler.toml                  # Cloudflare Worker config (optional)
```

## Creating a New Agent from This Template

### 1. Copy the Template

```bash
cp -r _AGENT_TEMPLATE my-new-agent
cd my-new-agent
```

### 2. Update `agent.yaml`

```yaml
name: "my-new-agent"
version: "0.1.0"
description: "Brief description of what this agent does"
pillar: "revenue"  # or: climate-intelligence, high-ceiling, infrastructure
status: "spec"     # spec → prototype → mvp → production
owner: "justin@viridis.earth"
revenue_model: "describe how this agent drives/unlocks revenue"
dependencies:
  - "package1>=1.0.0"
  - "package2"
ports:
  http: 8080
  health: /health
env_vars:
  - "AGENT_NAME"
  - "API_KEY"
  - "LOG_LEVEL"
```

### 3. Implement Core Logic in `src/core.py`

Replace the stub `AgentCore` class with your domain logic:

```python
from src.core import AgentCore, AgentConfig

class MyAgentCore(AgentCore):
    async def process(self, input_data: dict) -> dict:
        """
        Your business logic here.
        - Accept any input_data structure you need
        - Return a dict with results
        - Raise informative exceptions on failure
        """
        # Validate inputs
        if "required_field" not in input_data:
            raise ValueError("Missing required_field in input")

        # Execute domain logic
        result = await self._do_work(input_data)
        return result

    async def describe(self) -> dict:
        """Describe capabilities for agent discovery/composition."""
        return {
            "name": self.config.name,
            "version": self.config.version,
            "capabilities": ["capability1", "capability2"],
            "inputs": {
                "required_field": "str",
                "optional_field": "str (optional)"
            },
            "outputs": {
                "status": "str",
                "data": "dict"
            }
        }

    async def _do_work(self, data: dict) -> dict:
        """Internal business logic."""
        return {"status": "ok", "result": data}
```

### 4. Deploy to Your Target Environment

#### FastAPI (Docker)

```bash
docker build -t my-agent .
docker run -e AGENT_NAME=my-agent -e LOG_LEVEL=INFO -p 8080:8080 my-agent
```

Then:
```bash
curl -X POST http://localhost:8080/process -H "Content-Type: application/json" -d '{"key": "value"}'
```

#### Cloudflare Workers

1. Update `wrangler.toml` with your account ID
2. Implement `adapters/cloudflare_worker.js` to call your core logic
3. Deploy:
   ```bash
   wrangler deploy
   ```

#### MCP Server

The agent automatically registers as an MCP server. Claude and other MCP clients can discover it:

```bash
python adapters/mcp_server.py
```

Then in your MCP client config:
```json
{
  "mcpServers": {
    "my-agent": {
      "command": "python",
      "args": ["adapters/mcp_server.py"]
    }
  }
}
```

#### Claude Code Skill

1. Create a `.skill` directory at the Viridis skill library location
2. Copy `adapters/claude_skill.md` into it as `SKILL.md`
3. Zip the directory as `my-agent.skill`
4. Reference it in Claude Code

## Development Workflow

### Testing

```bash
# Unit tests for core logic
pytest tests/test_core.py -v

# With coverage
pytest tests/test_core.py --cov=src --cov-report=html
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run FastAPI adapter locally
python -m uvicorn adapters.fastapi_server:app --reload --port 8080

# Or run MCP adapter
python adapters/mcp_server.py
```

### Environment Setup

Copy `.env.example` to `.env` and populate with your values:

```bash
cp .env.example .env
# Edit .env with actual values (never commit this)
```

## Agent Lifecycle

### Status Progression

- **spec**: Requirements and architecture documented, no code
- **prototype**: MVP implementation, tested locally, not production-ready
- **mvp**: Deployed to staging, validated with real workloads
- **production**: Deployed to production, monitored, SLAs defined

Update `agent.yaml` status as you progress.

### Adding Dependencies

1. Add to `agent.yaml` `dependencies` list
2. Add to `requirements.txt` (for pip) or `package.json` (for Node)
3. Update `Dockerfile` if needed
4. Test locally: `docker build -t test .`

## Integration Patterns

### Using This Agent in Another Agent

If you're composing agents, import the core:

```python
from my_agent.src.core import MyAgentCore, AgentConfig

async def my_pipeline():
    config = AgentConfig(name="my-agent")
    agent = MyAgentCore(config)
    result = await agent.process({"key": "value"})
    return result
```

### Calling via HTTP

From any environment:

```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://agent-host:8080/process",
        json={"input": "data"}
    )
    result = response.json()
```

### Chaining with MCP

Agents automatically register with MCP. Use any MCP-compatible client to call them:

```python
# In another MCP-aware application
result = await mcp_client.call_tool("my-agent", "process", {"data": "..."})
```

## Monitoring & Observability

### Health Checks

Every agent exposes `/health` endpoint:

```bash
curl http://localhost:8080/health
# Returns: {"status": "ok", "agent": "my-agent", "version": "0.1.0"}
```

### Logging

Use Python `logging` module in your core logic. Adapters will propagate logs:

```python
import logging
logger = logging.getLogger(__name__)

async def process(self, data: dict) -> dict:
    logger.info(f"Processing {data}")
    try:
        result = await self._work()
        logger.info(f"Success: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        raise
```

### Metrics

In your core logic, track important metrics:

```python
import time

async def process(self, data: dict) -> dict:
    start = time.time()
    try:
        result = await self._work()
        duration = time.time() - start
        logger.info(f"Processed in {duration:.2f}s")
        return result
    except Exception as e:
        logger.error(f"Failed after {time.time() - start:.2f}s: {e}")
        raise
```

## Deployment Checklists

### Before Moving to Staging

- [ ] All tests pass: `pytest tests/`
- [ ] Agent manifest (`agent.yaml`) is complete and accurate
- [ ] All required env vars documented in `.env.example`
- [ ] Health check returns `{"status": "ok"}`
- [ ] Core logic has logging at INFO level for key operations
- [ ] Core logic handles errors gracefully and raises informative exceptions
- [ ] Local Docker build succeeds
- [ ] README explains what the agent does and how to use it

### Before Moving to Production

- [ ] Tested with real data in staging
- [ ] Monitoring and alerting configured
- [ ] Logging aggregation set up
- [ ] Rollback plan documented
- [ ] SLAs and performance targets defined
- [ ] Security: no secrets in code, all env-var based
- [ ] Version bumped in `agent.yaml`
- [ ] CHANGELOG or release notes updated

## FAQ

**Q: Can I share code between agents?**
A: Yes. Create a `viridis-common/` package with shared utilities and import it in your core logic.

**Q: What if I need to call another agent?**
A: Use the HTTP pattern or import its core module directly. Keep coupling loose via config.

**Q: Can I add custom deployment adapters?**
A: Yes. Add new files to `adapters/` following the same pattern. Every adapter should import and delegate to `AgentCore`.

**Q: How do I handle secrets?**
A: Never hardcode them. Use environment variables defined in `.env.example` (with no values). Load them in your config or adapter init.

**Q: Can I modify the template structure?**
A: For a single agent, yes. But keep `src/core.py` as the canonical source of domain logic. For consistency across Viridis, use this structure as the baseline.
