"""
Agent Core Module — Business Logic Layer

This module contains ONLY domain logic. No HTTP, no deployment concerns.
All deployment targets (FastAPI, Workers, MCP, Skill) import from here.

Extend AgentCore and override process() and describe() for your agent's logic.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration loaded from environment or config file."""
    name: str
    version: str = "0.1.0"
    debug: bool = False


class AgentCore:
    """
    Base class for all Viridis agents.

    Subclass this and override process() and describe() with your domain logic.
    All deployment adapters (FastAPI, Workers, MCP, Skill) will import and use your subclass.

    Example:
        class MyAgent(AgentCore):
            async def process(self, input_data: dict) -> dict:
                # Your domain logic here
                result = await self._do_work(input_data)
                return {"status": "ok", "result": result}

            def describe(self) -> dict:
                return {
                    "name": self.config.name,
                    "capabilities": ["capability1"],
                    "inputs": {"field": "str"},
                    "outputs": {"status": "str", "result": "str"}
                }
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize agent with config.

        Args:
            config: AgentConfig instance with name, version, debug settings
        """
        self.config = config
        self.logger = logging.getLogger(self.config.name)

        if self.config.debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

        self.logger.info(f"Initialized {self.config.name} v{self.config.version}")

    async def process(self, input_data: dict) -> dict:
        """
        Main processing entry point. Override in subclass.

        Args:
            input_data: Dictionary with agent-specific inputs.
                       Expected structure depends on your agent's domain.

        Returns:
            Dictionary with results. Standard structure:
                {
                    "status": "ok" | "error",
                    "data": <any>,
                    "error": <optional error message if status is "error">
                }

        Raises:
            ValueError: If required fields are missing in input_data
            RuntimeError: If processing fails
            Any domain-specific exceptions from your subclass
        """
        raise NotImplementedError("Override process() in your AgentCore subclass")

    async def health(self) -> dict:
        """
        Health check endpoint. Override to add custom checks.

        Returns:
            Dictionary indicating health status.
            Standard structure:
                {
                    "status": "ok" | "degraded" | "error",
                    "agent": "<agent_name>",
                    "version": "<version>",
                    "checks": {
                        "dependency1": "ok",
                        "dependency2": "degraded"
                    }
                }
        """
        return {
            "status": "ok",
            "agent": self.config.name,
            "version": self.config.version,
            "checks": {}
        }

    def describe(self) -> dict:
        """
        Describe agent capabilities for discovery and composition.

        Override this to declare your agent's inputs, outputs, and capabilities.
        This enables agent composition and auto-documentation.

        Returns:
            Dictionary describing the agent:
                {
                    "name": "<agent_name>",
                    "version": "<version>",
                    "description": "<what it does>",
                    "capabilities": ["capability1", "capability2"],
                    "inputs": {
                        "required_field": "type (str|int|dict|list)",
                        "optional_field": "type (optional)"
                    },
                    "outputs": {
                        "status": "str (ok|error)",
                        "result": "dict",
                        "error": "str (present if status is error)"
                    }
                }
        """
        return {
            "name": self.config.name,
            "version": self.config.version,
            "description": "Override describe() in your subclass",
            "capabilities": [],
            "inputs": {},
            "outputs": {
                "status": "str (ok|error)",
                "error": "str (optional)"
            }
        }

    def validate_input(self, input_data: dict, required_fields: list) -> None:
        """
        Helper: Validate required fields in input data.

        Args:
            input_data: The input dictionary to validate
            required_fields: List of field names that must be present

        Raises:
            ValueError: If any required field is missing
        """
        missing = [f for f in required_fields if f not in input_data]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

    def _wrap_result(self, data: Any = None, error: Optional[str] = None) -> dict:
        """
        Helper: Wrap result in standard format.

        Args:
            data: Result data (if success)
            error: Error message (if failure)

        Returns:
            Standard response dict with status, data, and optional error
        """
        if error:
            return {
                "status": "error",
                "error": error,
                "data": None
            }
        return {
            "status": "ok",
            "data": data,
            "error": None
        }
