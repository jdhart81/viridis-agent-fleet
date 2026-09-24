#!/usr/bin/env python3
"""
Viridis Agent Scaffolder — Programmatic Agent Generation

Generates a complete new agent directory from the _AGENT_TEMPLATE with all
necessary files, configs, and boilerplate code.

Usage:
    # CLI mode with flags
    python scaffold.py --name "my-agent" --description "What it does" \\
        --pillar revenue --deploy fastapi

    # From YAML spec
    python scaffold.py --from-spec proposal.yaml

    # Interactive mode
    python scaffold.py --interactive

    # With all options
    python scaffold.py \\
        --name "carbon-bridge" \\
        --description "Bridges carbon offset verification with financial ledger" \\
        --pillar revenue \\
        --deploy fastapi,mcp \\
        --revenue-model "per-verification" \\
        --capabilities "verify,audit,report" \\
        --dependencies "carbon-core,ledger-agent" \\
        --force

Specification YAML format:
    name: agent-name
    description: Agent purpose
    pillar: revenue|climate-intelligence|high-ceiling|infrastructure
    status: spec|prototype|mvp|production
    owner: email@viridis.earth
    revenue_model: How it drives revenue
    deploy_targets:
      primary: fastapi|mcp|cloudflare-worker|claude-skill
      secondary: [list of other targets]
    dependencies:
      services: [external service names]
      agents: [other agent names]
    env_vars: [environment variable names]
    capabilities:
      methods: [method names]
      inputs: [input field names]
      outputs: [output field names]
    justification:
      gap_filled: What gap this fills
      thesis_alignment: How it aligns with thesis
      expected_revenue: Revenue estimate
      connections: [list of agent connections]
"""

import sys
import os
import argparse
import yaml
import re
import asyncio
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime


# ============================================================================
# Configuration & Constants
# ============================================================================

VALID_PILLARS = {"revenue", "climate-intelligence", "high-ceiling", "infrastructure"}
VALID_DEPLOY_TARGETS = {"fastapi", "mcp", "cloudflare-worker", "claude-skill"}
VALID_STATUSES = {"spec", "prototype", "mvp", "production"}

# Get template directory (assume scaffold.py is in _AGENT_TEMPLATE)
TEMPLATE_DIR = Path(__file__).parent.absolute()
AGENTS_ROOT = TEMPLATE_DIR.parent.absolute()


@dataclass
class AgentSpec:
    """Agent specification data class."""
    name: str
    description: str
    pillar: str
    status: str = "spec"
    owner: str = "justin@viridis.earth"
    revenue_model: str = ""
    deploy_primary: str = "fastapi"
    deploy_secondary: List[str] = None
    dependencies_services: List[str] = None
    dependencies_agents: List[str] = None
    env_vars: List[str] = None
    capabilities_methods: List[str] = None
    capabilities_inputs: List[str] = None
    capabilities_outputs: List[str] = None
    justification_gap: str = ""
    justification_thesis: str = ""
    justification_revenue: str = ""
    justification_connections: List[str] = None

    def __post_init__(self):
        if self.deploy_secondary is None:
            self.deploy_secondary = []
        if self.dependencies_services is None:
            self.dependencies_services = []
        if self.dependencies_agents is None:
            self.dependencies_agents = []
        if self.env_vars is None:
            self.env_vars = ["AGENT_NAME", "LOG_LEVEL"]
        if self.capabilities_methods is None:
            self.capabilities_methods = ["process"]
        if self.capabilities_inputs is None:
            self.capabilities_inputs = ["input"]
        if self.capabilities_outputs is None:
            self.capabilities_outputs = ["status", "data"]
        if self.justification_connections is None:
            self.justification_connections = []


# ============================================================================
# Utility Functions
# ============================================================================

def validate_agent_name(name: str) -> bool:
    """Validate agent name: lowercase, hyphens, no spaces."""
    return bool(re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", name))


def validate_pillar(pillar: str) -> bool:
    """Validate pillar is one of allowed values."""
    return pillar in VALID_PILLARS


def validate_deploy_targets(targets: List[str]) -> bool:
    """Validate all deploy targets are valid."""
    return all(t in VALID_DEPLOY_TARGETS for t in targets)


def validate_status(status: str) -> bool:
    """Validate status is one of allowed values."""
    return status in VALID_STATUSES


def name_to_class(name: str) -> str:
    """Convert hyphenated name to PascalCase class name.

    Examples:
        carbon-bridge -> CarbonBridgeCore
        my-agent -> MyAgentCore
        x -> XCore
    """
    parts = name.split("-")
    class_name = "".join(p.capitalize() for p in parts) + "Core"
    return class_name


def name_to_module(name: str) -> str:
    """Convert hyphenated name to snake_case module name.

    Examples:
        carbon-bridge -> carbon_bridge
        my-agent -> my_agent
    """
    return name.replace("-", "_")


def print_header(text: str):
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")


def print_success(text: str):
    """Print success message."""
    print(f"✓ {text}")


def print_error(text: str):
    """Print error message."""
    print(f"✗ {text}")


def print_info(text: str):
    """Print info message."""
    print(f"→ {text}")


def validate_python_syntax(code: str) -> bool:
    """Check if Python code is syntactically valid."""
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError as e:
        print_error(f"Python syntax error: {e}")
        return False


# ============================================================================
# Specification Parsing
# ============================================================================

def load_yaml_spec(filepath: str) -> AgentSpec:
    """Load agent specification from YAML file."""
    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print_error(f"Specification file not found: {filepath}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print_error(f"YAML parsing error: {e}")
        sys.exit(1)

    # Map YAML structure to AgentSpec
    return AgentSpec(
        name=data.get("name", ""),
        description=data.get("description", ""),
        pillar=data.get("pillar", ""),
        status=data.get("status", "spec"),
        owner=data.get("owner", "justin@viridis.earth"),
        revenue_model=data.get("revenue_model", ""),
        deploy_primary=data.get("deploy_targets", {}).get("primary", "fastapi"),
        deploy_secondary=data.get("deploy_targets", {}).get("secondary", []),
        dependencies_services=data.get("dependencies", {}).get("services", []),
        dependencies_agents=data.get("dependencies", {}).get("agents", []),
        env_vars=data.get("env_vars", ["AGENT_NAME", "LOG_LEVEL"]),
        capabilities_methods=data.get("capabilities", {}).get("methods", ["process"]),
        capabilities_inputs=data.get("capabilities", {}).get("inputs", ["input"]),
        capabilities_outputs=data.get("capabilities", {}).get("outputs", ["status", "data"]),
        justification_gap=data.get("justification", {}).get("gap_filled", ""),
        justification_thesis=data.get("justification", {}).get("thesis_alignment", ""),
        justification_revenue=data.get("justification", {}).get("expected_revenue", ""),
        justification_connections=data.get("justification", {}).get("connections", []),
    )


def interactive_spec() -> AgentSpec:
    """Collect agent specification interactively from user input."""
    print_header("VIRIDIS AGENT SCAFFOLDER — INTERACTIVE MODE")

    # Agent name
    while True:
        name = input("\nAgent name (lowercase, hyphens OK): ").strip()
        if not name:
            print_error("Name cannot be empty.")
            continue
        if not validate_agent_name(name):
            print_error("Invalid name. Use lowercase letters, numbers, hyphens only.")
            continue
        break

    # Description
    description = input("Description (one line): ").strip()
    if not description:
        description = "Agent for Viridis ecosystem"

    # Pillar
    print(f"\nPillar options: {', '.join(VALID_PILLARS)}")
    while True:
        pillar = input("Pillar: ").strip()
        if not validate_pillar(pillar):
            print_error(f"Invalid pillar. Choose from: {', '.join(VALID_PILLARS)}")
            continue
        break

    # Status
    print(f"\nStatus options: {', '.join(VALID_STATUSES)}")
    status = input("Status [spec]: ").strip() or "spec"
    if not validate_status(status):
        status = "spec"

    # Revenue model
    revenue_model = input("Revenue model (optional): ").strip()

    # Deploy targets
    print(f"\nDeploy target options: {', '.join(VALID_DEPLOY_TARGETS)}")
    deploy_primary = input("Primary deployment target [fastapi]: ").strip() or "fastapi"
    deploy_secondary_input = input("Secondary targets (comma-separated, optional): ").strip()
    deploy_secondary = [t.strip() for t in deploy_secondary_input.split(",") if t.strip()]

    if not validate_deploy_targets([deploy_primary] + deploy_secondary):
        print_error("Invalid deployment target(s)")
        deploy_primary = "fastapi"
        deploy_secondary = []

    # Dependencies
    dependencies_agents_input = input("\nDependent agents (comma-separated, optional): ").strip()
    dependencies_agents = [a.strip() for a in dependencies_agents_input.split(",") if a.strip()]

    dependencies_services_input = input("External services (comma-separated, optional): ").strip()
    dependencies_services = [s.strip() for s in dependencies_services_input.split(",") if s.strip()]

    # Capabilities
    capabilities_input = input("\nCapability methods (comma-separated, default: process): ").strip()
    capabilities_methods = [c.strip() for c in capabilities_input.split(",") if c.strip()] or ["process"]

    capabilities_input_fields = input("Input fields (comma-separated, default: input): ").strip()
    capabilities_inputs = [i.strip() for i in capabilities_input_fields.split(",") if i.strip()] or ["input"]

    capabilities_output_fields = input("Output fields (comma-separated, default: status,data): ").strip()
    capabilities_outputs = [o.strip() for o in capabilities_output_fields.split(",") if o.strip()] or ["status", "data"]

    # Environment variables
    env_vars_input = input("\nEnvironment variables (comma-separated, default: AGENT_NAME,LOG_LEVEL): ").strip()
    env_vars = [e.strip().upper() for e in env_vars_input.split(",") if e.strip()] or ["AGENT_NAME", "LOG_LEVEL"]

    return AgentSpec(
        name=name,
        description=description,
        pillar=pillar,
        status=status,
        revenue_model=revenue_model,
        deploy_primary=deploy_primary,
        deploy_secondary=deploy_secondary,
        dependencies_agents=dependencies_agents,
        dependencies_services=dependencies_services,
        capabilities_methods=capabilities_methods,
        capabilities_inputs=capabilities_inputs,
        capabilities_outputs=capabilities_outputs,
        env_vars=env_vars,
    )


# ============================================================================
# Validation
# ============================================================================

def validate_spec(spec: AgentSpec, output_dir: Path, force: bool = False) -> bool:
    """Validate agent specification before generating."""
    errors = []

    if not spec.name:
        errors.append("Agent name is required")
    elif not validate_agent_name(spec.name):
        errors.append(f"Invalid agent name '{spec.name}'. Use lowercase, hyphens, no spaces.")

    if not spec.description:
        errors.append("Agent description is required")

    if not spec.pillar:
        errors.append("Pillar is required")
    elif not validate_pillar(spec.pillar):
        errors.append(f"Invalid pillar '{spec.pillar}'. Must be one of: {', '.join(VALID_PILLARS)}")

    if not validate_status(spec.status):
        errors.append(f"Invalid status '{spec.status}'. Must be one of: {', '.join(VALID_STATUSES)}")

    if not validate_deploy_targets([spec.deploy_primary] + spec.deploy_secondary):
        errors.append(f"Invalid deployment target(s). Must be one of: {', '.join(VALID_DEPLOY_TARGETS)}")

    if output_dir.exists():
        if not force:
            errors.append(f"Output directory already exists: {output_dir}. Use --force to overwrite.")

    if errors:
        print_error("Validation failed:")
        for error in errors:
            print(f"  - {error}")
        return False

    return True


# ============================================================================
# File Generation
# ============================================================================

def generate_agent_yaml(spec: AgentSpec) -> str:
    """Generate agent.yaml configuration file."""
    dependencies = spec.dependencies_agents + [f"{s}" for s in spec.dependencies_services]

    return f"""name: {spec.name}
version: "0.1.0"
description: {spec.description}
pillar: {spec.pillar}
status: {spec.status}
owner: {spec.owner}
revenue_model: {spec.revenue_model}
dependencies: {dependencies if dependencies else "[]"}  # Package list and agent dependencies
ports:
  http: 8080
  health: /health
env_vars: {spec.env_vars}  # List of required env var names (NO VALUES here — use .env.example)
"""


def generate_core_py(spec: AgentSpec) -> str:
    """Generate src/core.py with proper class structure."""
    class_name = name_to_class(spec.name)
    methods_code = _generate_capability_methods(spec.capabilities_methods)
    imports_needed = _determine_imports(spec)
    capability_routing = _generate_capability_routing(spec)

    return f'''"""
{spec.name.title()} Agent Core Module

{spec.description}

This module contains ONLY domain logic. No HTTP, no deployment concerns.
All deployment targets (FastAPI, Workers, MCP, Skill) import from here.
"""

import logging
import asyncio
from typing import Any, Dict, Optional{imports_needed}
from src.core import AgentCore, AgentConfig

logger = logging.getLogger(__name__)


class {class_name}(AgentCore):
    """
    {spec.name.title()} Agent Implementation

    {spec.description}

    Capabilities:
{chr(10).join("        - " + m for m in spec.capabilities_methods)}

    Input fields:
{chr(10).join("        - " + i for i in spec.capabilities_inputs)}

    Output fields:
{chr(10).join("        - " + o for o in spec.capabilities_outputs)}
    """

    async def process(self, input_data: dict) -> dict:
        """
        Main processing entry point.

        Routes to appropriate capability method based on input.

        Args:
            input_data: Dictionary with request data
                Expected keys: {', '.join(spec.capabilities_inputs)}

        Returns:
            Standard result dict with status, data, and optional error

        Raises:
            ValueError: If required fields are missing
            RuntimeError: If processing fails
        """
        try:
            # Validate required inputs
            self.validate_input(input_data, {spec.capabilities_inputs})

            # Route to capability
            capability = input_data.get("capability", "{spec.capabilities_methods[0]}")

            if capability == "{spec.capabilities_methods[0]}":
                return await self._{name_to_module(spec.name)}_{spec.capabilities_methods[0]}(input_data)
{capability_routing}
            else:
                return self._wrap_result(
                    error=f"Unknown capability: {{capability}}. Available: {', '.join(spec.capabilities_methods)}"
                )

        except ValueError as e:
            self.logger.error(f"Input validation error: {{e}}")
            return self._wrap_result(error=str(e))
        except Exception as e:
            self.logger.error(f"Processing error: {{e}}", exc_info=True)
            return self._wrap_result(error=f"Processing failed: {{str(e)}}")

    def describe(self) -> dict:
        """Describe agent capabilities for discovery and composition."""
        return {{
            "name": self.config.name,
            "version": self.config.version,
            "description": "{spec.description}",
            "pillar": "{spec.pillar}",
            "status": "{spec.status}",
            "capabilities": {spec.capabilities_methods},
            "inputs": {{{', '.join(f'"{i}": "str"' for i in spec.capabilities_inputs)}}},
            "outputs": {{{', '.join(f'"{o}": "str"' for o in spec.capabilities_outputs)}}},
            "dependencies": {{
                "agents": {spec.dependencies_agents},
                "services": {spec.dependencies_services}
            }}
        }}

    async def health(self) -> dict:
        """Health check with capability-specific checks."""
        base_health = await super().health()

        # Add capability-specific health checks
        base_health["checks"]["capabilities"] = "ok"

        return base_health

{methods_code}
'''


def _generate_capability_methods(methods: List[str]) -> str:
    """Generate placeholder methods for each capability."""
    code_blocks = []

    for method in methods:
        if method == "process":
            continue  # Already generated in main process()

        code_blocks.append(f'''
    async def _{name_to_module(method)}(self, input_data: dict) -> dict:
        """
        {method.title()} capability implementation.

        TODO: Implement this capability

        Args:
            input_data: Input data dictionary

        Returns:
            Result dictionary with status and data
        """
        try:
            # TODO: Implement {method} logic here
            self.logger.info(f"Executing {method} capability")

            result = {{
                "method": "{method}",
                "status": "not_implemented"
            }}

            return self._wrap_result(data=result)

        except Exception as e:
            self.logger.error(f"{method} failed: {{e}}", exc_info=True)
            return self._wrap_result(error=f"{method} failed: {{str(e)}}")
''')

    return "\n".join(code_blocks) if code_blocks else ""


def _generate_capability_routing(spec: AgentSpec) -> str:
    """Generate routing for additional capabilities."""
    if len(spec.capabilities_methods) <= 1:
        return ""

    lines = []
    for method in spec.capabilities_methods[1:]:
        lines.append(f'            elif capability == "{method}":')
        lines.append(f'                return await self._{name_to_module(method)}(input_data)')

    return "\n".join(lines)


def _determine_imports(spec: AgentSpec) -> str:
    """Determine additional imports based on dependencies."""
    imports = []

    if "aiohttp" in spec.dependencies_services or "http" in spec.description.lower():
        imports.append("aiohttp")

    if "postgres" in spec.description.lower() or "db" in spec.description.lower():
        imports.append("psycopg")

    if "redis" in spec.description.lower() or "cache" in spec.description.lower():
        imports.append("redis")

    if imports:
        return "\n" + ", ".join(imports)
    return ""


def generate_test_core_py(spec: AgentSpec) -> str:
    """Generate tests/test_core.py with tests for each capability."""
    class_name = name_to_class(spec.name)
    module_name = name_to_module(spec.name)

    test_methods = []
    for method in spec.capabilities_methods:
        test_methods.append(f'''
    @pytest.mark.asyncio
    async def test_{method}_capability(self, agent):
        """Test {method} capability."""
        input_data = {{{', '.join(f'"{i}": "test_value"' for i in spec.capabilities_inputs[:2])}}}
        result = await agent.process(input_data)

        assert result["status"] in ["ok", "error", "not_implemented"]
        assert "data" in result or "error" in result
''')

    return f'''"""
Unit tests for {spec.name} agent core logic.

Run with:
    pytest tests/test_core.py -v

With coverage:
    pytest tests/test_core.py --cov=src --cov-report=html
"""

import pytest
import asyncio
from src.{module_name} import {class_name}, AgentConfig


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def agent_config():
    """Create a test agent configuration."""
    return AgentConfig(
        name="{spec.name}",
        version="0.1.0",
        debug=True
    )


@pytest.fixture
def agent(agent_config):
    """Create a test agent instance."""
    return {class_name}(agent_config)


@pytest.fixture
def valid_input():
    """Valid input data for testing."""
    return {{{', '.join(f'"{i}": "test_value"' for i in spec.capabilities_inputs)}}}


# ============================================================================
# Initialization Tests
# ============================================================================

class TestAgentInit:
    """Test agent initialization."""

    def test_agent_init(self, agent, agent_config):
        """Test agent initialization."""
        assert agent.config.name == agent_config.name
        assert agent.config.version == agent_config.version

    def test_agent_logger_setup(self, agent):
        """Test that logger is properly configured."""
        assert agent.logger is not None


# ============================================================================
# Process Method Tests
# ============================================================================

class TestAgentProcess:
    """Test the process() method."""

    @pytest.mark.asyncio
    async def test_process_with_valid_input(self, agent, valid_input):
        """Test process with valid input."""
        result = await agent.process(valid_input)
        assert result["status"] in ["ok", "error", "not_implemented"]

    @pytest.mark.asyncio
    async def test_process_validation_error(self, agent):
        """Test that process validates inputs."""
        with pytest.raises(ValueError):
            await agent.process({{}})

{chr(10).join(test_methods)}

# ============================================================================
# Describe Method Tests
# ============================================================================

class TestAgentDescribe:
    """Test the describe() method."""

    def test_describe_returns_dict(self, agent):
        """Test that describe() returns a dictionary."""
        result = agent.describe()
        assert isinstance(result, dict)

    def test_describe_required_fields(self, agent):
        """Test that describe() includes required fields."""
        result = agent.describe()
        assert "name" in result
        assert "capabilities" in result
        assert "inputs" in result
        assert "outputs" in result

    def test_describe_capabilities(self, agent):
        """Test that describe lists all capabilities."""
        result = agent.describe()
        capabilities = result["capabilities"]
        assert isinstance(capabilities, list)
        assert len(capabilities) > 0


# ============================================================================
# Health Check Tests
# ============================================================================

class TestAgentHealth:
    """Test the health() method."""

    @pytest.mark.asyncio
    async def test_health_status(self, agent):
        """Test that health check returns valid status."""
        result = await agent.health()
        assert result["status"] in ["ok", "degraded", "error"]


# ============================================================================
# Integration Tests
# ============================================================================

class TestAgentIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, agent, valid_input):
        """Test complete agent workflow."""
        # Test describe
        desc = agent.describe()
        assert desc["name"] == "{spec.name}"

        # Test health
        health = await agent.health()
        assert health["status"] in ["ok", "degraded", "error"]

        # Test process
        result = await agent.process(valid_input)
        assert result["status"] in ["ok", "error", "not_implemented"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
'''


def generate_fastapi_adapter(spec: AgentSpec) -> str:
    """Generate adapters/fastapi_server.py."""
    module_name = name_to_module(spec.name)
    class_name = name_to_class(spec.name)

    return f'''"""
FastAPI HTTP Server Adapter for {spec.name} Agent

Exposes the agent as a REST API with:
- POST /process — Main processing endpoint
- GET /health — Health check
- GET /describe — Agent metadata
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from src.{module_name} import {class_name}, AgentConfig

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================

class ProcessRequest(BaseModel):
    """Request body for /process endpoint."""
    {': str = "test"'.join(f'{i}' for i in spec.capabilities_inputs[:1])}

    class Config:
        json_schema_extra = {{
            "example": {{{', '.join(f'"{i}": "example_value"' for i in spec.capabilities_inputs)}}}
        }}


class ProcessResponse(BaseModel):
    """Response from /process endpoint."""
    status: str
    data: dict = None
    error: str = None


# ============================================================================
# FastAPI Application
# ============================================================================

# Global agent instance
agent_instance: {class_name} = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage agent lifecycle."""
    global agent_instance

    # Startup
    agent_config = AgentConfig(
        name=os.getenv("AGENT_NAME", "{spec.name}"),
        version="0.1.0",
        debug=os.getenv("DEBUG", "false").lower() == "true"
    )
    agent_instance = {class_name}(agent_config)
    logger.info(f"Agent {{agent_config.name}} initialized")

    yield

    # Shutdown
    logger.info("Agent shutdown")


app = FastAPI(
    title="{spec.name}",
    description="{spec.description}",
    version="0.1.0",
    lifespan=lifespan
)


# ============================================================================
# Routes
# ============================================================================

@app.post("/process", response_model=ProcessResponse)
async def process(request: ProcessRequest):
    """
    Main processing endpoint.

    Accepts input data and routes to agent's process() method.
    """
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        input_dict = request.model_dump()
        result = await agent_instance.process(input_dict)
        return ProcessResponse(**result)
    except Exception as e:
        logger.error(f"Process error: {{e}}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Health check endpoint."""
    if not agent_instance:
        return {{"status": "error", "detail": "Agent not initialized"}}

    return await agent_instance.health()


@app.get("/describe")
async def describe():
    """Get agent metadata and capabilities."""
    if not agent_instance:
        return {{"status": "error", "detail": "Agent not initialized"}}

    return agent_instance.describe()


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {{
        "name": "{spec.name}",
        "description": "{spec.description}",
        "version": "0.1.0",
        "endpoints": {{
            "POST /process": "Main processing endpoint",
            "GET /health": "Health check",
            "GET /describe": "Agent metadata"
        }}
    }}


# ============================================================================
# Server Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run(
        "adapters.fastapi_server:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true"
    )
'''


def generate_mcp_adapter(spec: AgentSpec) -> str:
    """Generate adapters/mcp_server.py for Model Context Protocol."""
    module_name = name_to_module(spec.name)
    class_name = name_to_class(spec.name)

    return f'''"""
MCP Server Adapter for {spec.name} Agent

Exposes agent capabilities via Model Context Protocol.
Compatible with Claude and other MCP clients.

Usage:
    python -m adapters.mcp_server
"""

import os
import json
import logging
from typing import Any
from fastmcp import FastMCP
from dotenv import load_dotenv

from src.{module_name} import {class_name}, AgentConfig

load_dotenv()

logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("{spec.name}")

# Global agent instance
agent_instance: {class_name} = None


def init_agent():
    """Initialize agent instance."""
    global agent_instance
    if agent_instance is None:
        agent_config = AgentConfig(
            name=os.getenv("AGENT_NAME", "{spec.name}"),
            version="0.1.0",
            debug=os.getenv("DEBUG", "false").lower() == "true"
        )
        agent_instance = {class_name}(agent_config)
        logger.info(f"Agent {{agent_config.name}} initialized for MCP")


@mcp.tool()
async def process(
    {', '.join(f'{i}: str = ""' for i in spec.capabilities_inputs[:2])}
) -> str:
    """
    Process request through {spec.name} agent.

    {spec.description}
    """
    init_agent()

    input_data = {{
{chr(10).join(f'        "{i}": {i},' for i in spec.capabilities_inputs[:2])}
    }}

    result = await agent_instance.process(input_data)
    return json.dumps(result, indent=2)


@mcp.tool()
def describe() -> str:
    """Get agent capabilities and metadata."""
    init_agent()
    return json.dumps(agent_instance.describe(), indent=2)


@mcp.tool()
async def health() -> str:
    """Check agent health status."""
    init_agent()
    result = await agent_instance.health()
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    import asyncio
    mcp.run()
'''


def generate_requirements_txt(spec: AgentSpec) -> str:
    """Generate requirements.txt with base and conditional dependencies."""
    reqs = """# Core agent framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0

# MCP Server support
fastmcp==0.1.0

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
httpx==0.25.0

# Development utilities
python-dotenv==1.0.0

# Logging and monitoring
python-json-logger==2.0.7
pyyaml==6.0.1

"""

    # Add conditional dependencies based on spec
    optional_deps = []

    if "http" in spec.description.lower():
        optional_deps.append("aiohttp==3.9.1")

    if "postgres" in spec.description.lower() or "database" in spec.description.lower():
        optional_deps.append("psycopg[binary]==3.9")

    if "redis" in spec.description.lower() or "cache" in spec.description.lower():
        optional_deps.append("redis==5.0.1")

    if "data" in spec.description.lower():
        optional_deps.append("pandas==2.1.3")

    if optional_deps:
        reqs += "\n# Agent-specific dependencies\n"
        reqs += "\n".join(optional_deps)

    return reqs


def generate_env_example(spec: AgentSpec) -> str:
    """Generate .env.example file."""
    content = """# Agent Configuration
# Copy this file to .env and fill in actual values
# NEVER commit .env with real secrets

# Agent identity and logging
AGENT_NAME={name}
LOG_LEVEL=INFO
DEBUG=false

# Deployment
PORT=8080

"""

    # Add agent-specific env vars
    if spec.env_vars:
        content += "# Agent-specific variables\n"
        for var in spec.env_vars:
            if var not in ["AGENT_NAME", "LOG_LEVEL"]:
                content += f"{var}=\n"

    return content.format(name=spec.name)


def generate_readme(spec: AgentSpec) -> str:
    """Generate README.md with comprehensive documentation."""
    class_name = name_to_class(spec.name)
    deploy_targets = [spec.deploy_primary] + spec.deploy_secondary

    return f"""# {spec.name.title()}

{spec.description}

## Overview

- **Status**: {spec.status}
- **Pillar**: {spec.pillar}
- **Owner**: {spec.owner}
- **Revenue Model**: {spec.revenue_model or "TBD"}

## Capabilities

This agent provides the following capabilities:

{chr(10).join(f"- **{method}**: TODO — describe this capability" for method in spec.capabilities_methods)}

### Inputs

{chr(10).join(f"- `{i}` (str): Description of {i}" for i in spec.capabilities_inputs)}

### Outputs

{chr(10).join(f"- `{o}` (str): Description of {o}" for o in spec.capabilities_outputs)}

## Dependencies

### Services

{chr(10).join(f"- {s}" for s in spec.dependencies_services) if spec.dependencies_services else "None"}

### Agents

{chr(10).join(f"- {a}" for a in spec.dependencies_agents) if spec.dependencies_agents else "None"}

## Deployment

This agent can be deployed to:

{chr(10).join(f"- **{target}**: {target.replace('-', ' ').title()}" for target in deploy_targets)}

### FastAPI Server

```bash
pip install -r requirements.txt
python adapters/fastapi_server.py
```

Server will start on `http://localhost:8080`

Endpoints:
- `POST /process` — Main processing endpoint
- `GET /health` — Health check
- `GET /describe` — Agent metadata

### MCP Server

```bash
python -m adapters.mcp_server
```

For use with Claude or other MCP clients.

## Development

### Setup

```bash
pip install -r requirements.txt
```

### Running Tests

```bash
pytest tests/test_core.py -v
```

With coverage:

```bash
pytest tests/test_core.py --cov=src --cov-report=html
```

### Environment Variables

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

Required variables:
{chr(10).join(f"- `{var}`" for var in spec.env_vars)}

## Implementation Checklist

- [ ] Implement `{name_to_module(spec.name)}_process()` in `src/core.py`
{chr(10).join(f"- [ ] Implement `{name_to_module(m)}()` capability" for m in spec.capabilities_methods[1:])}
- [ ] Add unit tests in `tests/test_core.py`
- [ ] Test with: `pytest tests/test_core.py -v`
- [ ] Document API schema (if using FastAPI)
- [ ] Update this README with implementation details
- [ ] Deploy to target: {', '.join(deploy_targets)}

## Justification

### Gap Filled

{spec.justification_gap or "TODO — describe the gap this agent fills"}

### Thesis Alignment

{spec.justification_thesis or "TODO — explain alignment with thermodynamic economics thesis"}

### Expected Revenue

{spec.justification_revenue or "TBD"}

### Connections

{chr(10).join(f"- {c}" for c in spec.justification_connections) if spec.justification_connections else "None identified yet"}

## Viridis Architecture

For details on agent architecture, see `/DEPLOYMENT_GUIDE.md` in template directory.

---

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""


def generate_proposal_template() -> str:
    """Generate proposal_template.yaml for spec submissions."""
    return """# Viridis Agent Proposal — fill this in and run: python scaffold.py --from-spec proposal.yaml

name: ""                          # Agent name (lowercase, hyphens OK)
description: ""                   # One-line description of purpose
pillar: ""                         # revenue | climate-intelligence | high-ceiling | infrastructure
status: "prototype"                # spec | prototype | mvp | production
owner: "justin@viridis.earth"      # Agent owner email
revenue_model: ""                  # How this agent drives/unlocks revenue
deploy_targets:
  primary: ""                      # fastapi | mcp | cloudflare-worker | claude-skill
  secondary: []                    # Additional deployment targets
dependencies:
  services: []                     # External service dependencies
  agents: []                       # Other agents this depends on
env_vars: []                       # Environment variable names (no values)
capabilities:
  methods: []                      # List of capability method names
  inputs: []                       # Input field names this agent expects
  outputs: []                      # Output field names this agent returns
justification:
  gap_filled: ""                   # What problem does this solve?
  thesis_alignment: ""             # How does it align with thermodynamic economics thesis?
  expected_revenue: ""             # Estimated revenue or value
  connections: []                  # Which agents does this connect with?
"""


# ============================================================================
# Main Generation Pipeline
# ============================================================================

def generate_agent(spec: AgentSpec, output_dir: Path, force: bool = False) -> bool:
    """Generate complete agent from specification."""

    # Validate specification
    if not validate_spec(spec, output_dir, force):
        return False

    print_header(f"GENERATING AGENT: {spec.name}")
    print_info(f"Description: {spec.description}")
    print_info(f"Pillar: {spec.pillar}")
    print_info(f"Status: {spec.status}")
    print_info(f"Output directory: {output_dir}")

    # Create directory structure
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "src").mkdir(exist_ok=True)
        (output_dir / "adapters").mkdir(exist_ok=True)
        (output_dir / "tests").mkdir(exist_ok=True)
        print_success("Created directory structure")
    except Exception as e:
        print_error(f"Failed to create directories: {e}")
        return False

    # Generate files
    files_to_create = {
        "agent.yaml": generate_agent_yaml(spec),
        "src/__init__.py": f"\"\"\"Generated {spec.name} agent module.\"\"\"\n\nfrom .core import {name_to_class(spec.name)}, AgentConfig\n\n__all__ = [{name_to_class(spec.name)!r}, 'AgentConfig']\n",
        f"src/{name_to_module(spec.name)}.py": generate_core_py(spec),
        "tests/__init__.py": "\"\"\"Generated tests module.\"\"\"\n",
        "tests/test_core.py": generate_test_core_py(spec),
        "requirements.txt": generate_requirements_txt(spec),
        ".env.example": generate_env_example(spec),
        "README.md": generate_readme(spec),
    }

    # Add deployment adapters
    if "fastapi" in [spec.deploy_primary] + spec.deploy_secondary:
        files_to_create["adapters/fastapi_server.py"] = generate_fastapi_adapter(spec)

    if "mcp" in [spec.deploy_primary] + spec.deploy_secondary:
        files_to_create["adapters/mcp_server.py"] = generate_mcp_adapter(spec)

    # Write all files
    errors = []
    for filepath, content in files_to_create.items():
        full_path = output_dir / filepath

        # Validate Python files before writing
        if filepath.endswith(".py"):
            if not validate_python_syntax(content):
                errors.append(f"Syntax error in {filepath}")
                continue

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            print_success(f"Generated {filepath}")
        except Exception as e:
            errors.append(f"Failed to write {filepath}: {e}")
            print_error(f"Failed to write {filepath}: {e}")

    if errors:
        print_error(f"Generation completed with {len(errors)} error(s)")
        return False

    print_success(f"Agent generated successfully in {output_dir}")
    return True


def print_next_steps(spec: AgentSpec, output_dir: Path):
    """Print next steps for user."""
    print_header("NEXT STEPS")

    print(f"""1. Navigate to agent directory:
   cd {output_dir}

2. Install dependencies:
   pip install -r requirements.txt

3. Configure environment:
   cp .env.example .env
   # Edit .env with actual values

4. Implement agent logic:
   - Edit src/{name_to_module(spec.name)}.py
   - Implement capability methods: {', '.join(spec.capabilities_methods)}
   - See README.md for implementation checklist

5. Run tests:
   pytest tests/test_core.py -v

6. Start server (if FastAPI):
   python adapters/fastapi_server.py

7. Test endpoints:
   curl -X POST http://localhost:8080/process \\
     -H "Content-Type: application/json" \\
     -d '{{"input": "test"}}'

8. Review deployment guide:
   cat README.md

For more info, see:
  - {output_dir}/README.md
  - {output_dir}/agent.yaml
  - {TEMPLATE_DIR}/DEPLOYMENT_GUIDE.md
""")


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Viridis Agent Scaffolder — Generate complete agents from templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
Examples:
  # CLI mode with flags
  python scaffold.py --name "my-agent" --description "What it does" \\
      --pillar revenue --deploy fastapi

  # From YAML spec
  python scaffold.py --from-spec proposal.yaml

  # Interactive mode
  python scaffold.py --interactive

  # Create proposal template
  python scaffold.py --template
        """)
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--name",
        help="Agent name (lowercase, hyphens OK)"
    )
    input_group.add_argument(
        "--from-spec",
        metavar="FILE",
        help="Load specification from YAML file"
    )
    input_group.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode (prompts for each field)"
    )
    input_group.add_argument(
        "--template",
        action="store_true",
        help="Generate proposal_template.yaml"
    )

    # CLI-only arguments
    parser.add_argument(
        "--description",
        help="Agent description (required with --name)"
    )
    parser.add_argument(
        "--pillar",
        help="Pillar: revenue, climate-intelligence, high-ceiling, infrastructure (required with --name)"
    )
    parser.add_argument(
        "--status",
        choices=VALID_STATUSES,
        default="spec",
        help="Agent status (default: spec)"
    )
    parser.add_argument(
        "--deploy",
        default="fastapi",
        help="Deployment targets (comma-separated, default: fastapi)"
    )
    parser.add_argument(
        "--revenue-model",
        help="Revenue model description"
    )
    parser.add_argument(
        "--capabilities",
        help="Capability methods (comma-separated, default: process)"
    )
    parser.add_argument(
        "--dependencies",
        help="Dependent agents (comma-separated)"
    )
    parser.add_argument(
        "--output",
        help="Output directory (default: ../AGENT_NAME)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output directory"
    )

    args = parser.parse_args()

    # Handle template generation
    if args.template:
        output_path = TEMPLATE_DIR / "proposal_template.yaml"
        with open(output_path, "w") as f:
            f.write(generate_proposal_template())
        print_success(f"Template generated: {output_path}")
        sys.exit(0)

    # Collect specification
    if args.from_spec:
        spec = load_yaml_spec(args.from_spec)
    elif args.interactive:
        spec = interactive_spec()
    elif args.name:
        if not args.description or not args.pillar:
            parser.error("--description and --pillar are required with --name")

        deploy_targets = [t.strip() for t in args.deploy.split(",")]
        capabilities = [c.strip() for c in (args.capabilities or "process").split(",")]
        dependencies = [d.strip() for d in (args.dependencies or "").split(",") if d.strip()]

        spec = AgentSpec(
            name=args.name,
            description=args.description,
            pillar=args.pillar,
            status=args.status,
            revenue_model=args.revenue_model or "",
            deploy_primary=deploy_targets[0],
            deploy_secondary=deploy_targets[1:],
            dependencies_agents=dependencies,
            capabilities_methods=capabilities,
        )
    else:
        parser.print_help()
        sys.exit(1)

    # Determine output directory
    if args.output:
        output_dir = Path(args.output).absolute()
    else:
        output_dir = AGENTS_ROOT / spec.name

    # Generate agent
    success = generate_agent(spec, output_dir, force=args.force)

    if success:
        print_next_steps(spec, output_dir)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
