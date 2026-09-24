# Example: Building Your First Viridis Agent

This document walks through creating a simple text processing agent from this template.

## Overview

We'll build a **TextProcessingAgent** that:
- Takes text input
- Applies transformations (uppercase, lowercase, reverse, etc.)
- Returns processed text
- Can be deployed to FastAPI, Docker, MCP, or Claude Code

## Step 1: Update the Manifest

Edit `agent.yaml`:

```yaml
name: "text-processor"
version: "0.1.0"
description: "Transforms text with various operations"
pillar: "infrastructure"
status: "prototype"
owner: "justin@viridis.earth"
revenue_model: "internal tooling for document processing"
dependencies:
  - "fastapi>=0.104.0"
  - "uvicorn>=0.24.0"
ports:
  http: 8080
  health: /health
env_vars:
  - "AGENT_NAME"
  - "LOG_LEVEL"
```

## Step 2: Implement Core Logic

Replace `src/core.py` with your implementation:

```python
"""Text Processing Agent"""
from src.core import AgentCore, AgentConfig

class TextProcessorAgent(AgentCore):
    """Transforms text with various operations."""

    async def process(self, input_data: dict) -> dict:
        """
        Process text.

        Args:
            input_data: {
                "text": "input string",
                "operation": "upper|lower|reverse|title" (optional, default: "upper")
            }

        Returns:
            {
                "status": "ok",
                "data": {
                    "original": "input string",
                    "result": "TRANSFORMED",
                    "operation": "upper"
                }
            }
        """
        # Validate
        self.validate_input(input_data, ["text"])

        text = input_data["text"]
        operation = input_data.get("operation", "upper")

        # Transform
        if operation == "upper":
            result = text.upper()
        elif operation == "lower":
            result = text.lower()
        elif operation == "reverse":
            result = text[::-1]
        elif operation == "title":
            result = text.title()
        else:
            raise ValueError(f"Unknown operation: {operation}")

        return self._wrap_result(data={
            "original": text,
            "result": result,
            "operation": operation
        })

    def describe(self) -> dict:
        """Describe agent capabilities."""
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Text transformation agent",
            "capabilities": ["uppercase", "lowercase", "reverse", "titlecase"],
            "inputs": {
                "text": "str (required)",
                "operation": "str (optional: upper|lower|reverse|title, default: upper)"
            },
            "outputs": {
                "status": "str (ok|error)",
                "data": {
                    "original": "str",
                    "result": "str",
                    "operation": "str"
                }
            }
        }
```

## Step 3: Update FastAPI Adapter

Edit `adapters/fastapi_server.py` to use your agent:

```python
# ... (keep the existing imports and setup)

# Import your agent
from src.core import TextProcessorAgent, AgentConfig

# ... (keep existing config setup)

# Replace the agent initialization
config = AgentConfig(
    name=AGENT_NAME,
    version=AGENT_VERSION,
    debug=(LOG_LEVEL == "DEBUG")
)
agent = TextProcessorAgent(config)  # Use your subclass!

# ... (rest of the file stays the same)
```

## Step 4: Write Tests

Update `tests/test_core.py`:

```python
import pytest
from src.core import TextProcessorAgent, AgentConfig

@pytest.mark.asyncio
async def test_text_processor_uppercase():
    """Test uppercase transformation."""
    config = AgentConfig(name="text-processor")
    agent = TextProcessorAgent(config)

    result = await agent.process({
        "text": "hello world",
        "operation": "upper"
    })

    assert result["status"] == "ok"
    assert result["data"]["result"] == "HELLO WORLD"
    assert result["data"]["operation"] == "upper"

@pytest.mark.asyncio
async def test_text_processor_reverse():
    """Test reverse transformation."""
    config = AgentConfig(name="text-processor")
    agent = TextProcessorAgent(config)

    result = await agent.process({
        "text": "hello",
        "operation": "reverse"
    })

    assert result["status"] == "ok"
    assert result["data"]["result"] == "olleh"

@pytest.mark.asyncio
async def test_text_processor_validation():
    """Test input validation."""
    config = AgentConfig(name="text-processor")
    agent = TextProcessorAgent(config)

    with pytest.raises(ValueError):
        await agent.process({})  # Missing "text"

@pytest.mark.asyncio
async def test_text_processor_invalid_operation():
    """Test invalid operation error."""
    config = AgentConfig(name="text-processor")
    agent = TextProcessorAgent(config)

    with pytest.raises(ValueError, match="Unknown operation"):
        await agent.process({
            "text": "hello",
            "operation": "invalid"
        })
```

## Step 5: Test Locally

```bash
# Install dependencies
make install

# Run tests
make test

# Start development server
make dev
```

## Step 6: Test HTTP Endpoints

```bash
# Check health
curl http://localhost:8080/health

# Get description
curl http://localhost:8080/describe

# Process text
curl -X POST http://localhost:8080/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "hello world",
    "operation": "upper"
  }'

# Expected response:
# {
#   "status": "ok",
#   "data": {
#     "original": "hello world",
#     "result": "HELLO WORLD",
#     "operation": "upper"
#   },
#   "error": null
# }
```

## Step 7: Deploy to Docker

```bash
# Build image
make docker-build

# Run container
make docker-run

# Test from container
curl -X POST http://localhost:8080/process \
  -H "Content-Type: application/json" \
  -d '{"text": "hello", "operation": "reverse"}'
```

## Step 8: Deploy as MCP Server

```bash
# Run MCP adapter
python adapters/mcp_server.py

# In another terminal, connect via MCP client (e.g., Claude Code)
# It will expose:
# - process(input_data) -> dict
# - health() -> dict
# - describe() -> dict
```

## Step 9: Deploy as Claude Code Skill

```bash
# Create skill directory
mkdir text-processor.skill

# Copy files
cp adapters/claude_skill.md text-processor.skill/SKILL.md
cp src/core.py text-processor.skill/

# Create Python module
touch text-processor.skill/__init__.py
cat > text-processor.skill/__init__.py << 'EOF'
from src.core import TextProcessorAgent, AgentConfig

__all__ = ["TextProcessorAgent", "process"]

async def process(input_data: dict) -> dict:
    """Process text through TextProcessorAgent."""
    config = AgentConfig(name="text-processor")
    agent = TextProcessorAgent(config)
    return await agent.process(input_data)
EOF

# Zip it
zip -r text-processor.skill.zip text-processor.skill/

# Use in Claude Code
/import ./text-processor.skill.zip

# Then in Claude Code
from text_processor_skill import process

result = await process({
    "text": "hello world",
    "operation": "upper"
})
print(result)
```

## Step 10: Production Checklist

Before deploying to production:

- [ ] All tests pass: `make test`
- [ ] Code is formatted: `make fmt`
- [ ] No linting errors: `make lint`
- [ ] Docker builds successfully: `make docker-build`
- [ ] Health check works: `make health` (with running server)
- [ ] All endpoint tests pass: `curl http://localhost:8080/health`
- [ ] Agent manifest is complete and accurate
- [ ] Environment variables documented in `.env.example`
- [ ] Error handling is robust
- [ ] Logging is informative
- [ ] No secrets hardcoded

## Composition Example

Use your text processor with other agents:

```python
from text_processor_skill import process as process_text
from some_other_skill import process as analyze

async def pipeline(input_text):
    # Step 1: Process text
    text_result = await process_text({
        "text": input_text,
        "operation": "upper"
    })

    if text_result["status"] != "ok":
        return text_result

    # Step 2: Analyze processed text
    analyze_result = await analyze({
        "text": text_result["data"]["result"]
    })

    return analyze_result
```

## Troubleshooting

**Q: ImportError when running `make dev`**
A: Run `make install` first to install dependencies.

**Q: 404 on `/process` endpoint**
A: Make sure you're using POST, not GET:
```bash
curl -X POST http://localhost:8080/process ...
```

**Q: Tests fail with "ModuleNotFoundError"**
A: Make sure you're running from the agent root directory, not a subdirectory.

**Q: Docker container exits immediately**
A: Check logs:
```bash
docker run -p 8080:8080 viridis-agent:latest
# Look for error messages
```

**Q: Agent fails validation**
A: Ensure your input JSON includes all required fields:
```python
# Wrong - missing "text"
{"operation": "upper"}

# Correct
{"text": "hello", "operation": "upper"}
```

---

Now you have a complete, tested, deployable agent! The same code runs on FastAPI, Docker, MCP, and Claude Code with zero changes to core logic.
