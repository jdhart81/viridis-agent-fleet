"""
Unit tests for agent core logic.

Run with:
    pytest tests/test_core.py -v

With coverage:
    pytest tests/test_core.py --cov=src --cov-report=html
"""

import pytest
import asyncio
from src.core import AgentCore, AgentConfig


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def agent_config():
    """Create a test agent configuration."""
    return AgentConfig(
        name="test-agent",
        version="0.1.0",
        debug=True
    )


@pytest.fixture
def agent(agent_config):
    """Create a test agent instance."""
    return AgentCore(agent_config)


@pytest.fixture
def valid_input():
    """Valid input data for testing."""
    return {
        "field1": "value1",
        "field2": "value2"
    }


# ============================================================================
# Configuration Tests
# ============================================================================

class TestAgentConfig:
    """Test AgentConfig dataclass."""

    def test_config_creation(self, agent_config):
        """Test basic config creation."""
        assert agent_config.name == "test-agent"
        assert agent_config.version == "0.1.0"
        assert agent_config.debug is True

    def test_config_defaults(self):
        """Test config default values."""
        config = AgentConfig(name="test")
        assert config.version == "0.1.0"
        assert config.debug is False

    def test_config_immutability(self, agent_config):
        """Test that config is a proper dataclass."""
        # Dataclasses are mutable by default, but we can test the structure
        assert hasattr(agent_config, "name")
        assert hasattr(agent_config, "version")
        assert hasattr(agent_config, "debug")


# ============================================================================
# AgentCore Initialization Tests
# ============================================================================

class TestAgentCoreInit:
    """Test AgentCore initialization."""

    def test_agent_init(self, agent, agent_config):
        """Test agent initialization."""
        assert agent.config.name == agent_config.name
        assert agent.config.version == agent_config.version

    def test_agent_logger_setup(self, agent):
        """Test that logger is properly configured."""
        assert agent.logger is not None
        assert agent.logger.name == agent.config.name


# ============================================================================
# Process Method Tests
# ============================================================================

class TestAgentProcessMethod:
    """Test the process() method."""

    @pytest.mark.asyncio
    async def test_process_not_implemented(self, agent, valid_input):
        """Test that process() raises NotImplementedError in base class."""
        with pytest.raises(NotImplementedError):
            await agent.process(valid_input)

    @pytest.mark.asyncio
    async def test_process_with_custom_subclass(self):
        """Test process() with a custom subclass implementation."""

        class TestAgent(AgentCore):
            async def process(self, input_data: dict) -> dict:
                self.validate_input(input_data, ["field1"])
                return self._wrap_result(data={"result": input_data["field1"]})

        config = AgentConfig(name="test-custom")
        agent = TestAgent(config)

        result = await agent.process({"field1": "test"})
        assert result["status"] == "ok"
        assert result["data"]["result"] == "test"

    @pytest.mark.asyncio
    async def test_process_validation_error(self):
        """Test that process() properly validates inputs."""

        class TestAgent(AgentCore):
            async def process(self, input_data: dict) -> dict:
                self.validate_input(input_data, ["required_field"])
                return self._wrap_result(data={"ok": True})

        config = AgentConfig(name="test-validation")
        agent = TestAgent(config)

        with pytest.raises(ValueError, match="Missing required fields"):
            await agent.process({"other_field": "value"})


# ============================================================================
# Health Check Tests
# ============================================================================

class TestAgentHealthMethod:
    """Test the health() method."""

    @pytest.mark.asyncio
    async def test_health_returns_dict(self, agent):
        """Test that health() returns a dictionary."""
        result = await agent.health()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_health_contains_required_fields(self, agent):
        """Test that health() includes required fields."""
        result = await agent.health()
        assert "status" in result
        assert "agent" in result
        assert "version" in result

    @pytest.mark.asyncio
    async def test_health_status_ok(self, agent):
        """Test that health() returns ok status."""
        result = await agent.health()
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_agent_name(self, agent, agent_config):
        """Test that health() includes correct agent name."""
        result = await agent.health()
        assert result["agent"] == agent_config.name

    @pytest.mark.asyncio
    async def test_health_custom_checks(self):
        """Test that custom subclass can override health()."""

        class TestAgent(AgentCore):
            async def health(self) -> dict:
                base_health = await super().health()
                base_health["checks"]["custom_check"] = "ok"
                return base_health

        config = AgentConfig(name="test-health")
        agent = TestAgent(config)

        result = await agent.health()
        assert result["checks"]["custom_check"] == "ok"


# ============================================================================
# Describe Method Tests
# ============================================================================

class TestAgentDescribeMethod:
    """Test the describe() method."""

    def test_describe_returns_dict(self, agent):
        """Test that describe() returns a dictionary."""
        result = agent.describe()
        assert isinstance(result, dict)

    def test_describe_contains_required_fields(self, agent):
        """Test that describe() includes required fields."""
        result = agent.describe()
        assert "name" in result
        assert "version" in result
        assert "description" in result
        assert "capabilities" in result
        assert "inputs" in result
        assert "outputs" in result

    def test_describe_agent_info(self, agent, agent_config):
        """Test that describe() includes correct agent info."""
        result = agent.describe()
        assert result["name"] == agent_config.name
        assert result["version"] == agent_config.version

    def test_describe_custom_implementation(self):
        """Test that custom subclass can override describe()."""

        class TestAgent(AgentCore):
            def describe(self) -> dict:
                return {
                    "name": self.config.name,
                    "version": self.config.version,
                    "capabilities": ["capability1", "capability2"],
                    "inputs": {"input_field": "str"},
                    "outputs": {"result": "str"}
                }

        config = AgentConfig(name="test-describe")
        agent = TestAgent(config)

        result = agent.describe()
        assert "capability1" in result["capabilities"]
        assert "capability2" in result["capabilities"]


# ============================================================================
# Validation Helper Tests
# ============================================================================

class TestAgentValidation:
    """Test validation helper methods."""

    def test_validate_input_success(self, agent):
        """Test validate_input with all required fields present."""
        input_data = {"field1": "value1", "field2": "value2"}
        # Should not raise
        agent.validate_input(input_data, ["field1", "field2"])

    def test_validate_input_missing_field(self, agent):
        """Test validate_input with missing required field."""
        input_data = {"field1": "value1"}
        with pytest.raises(ValueError, match="Missing required fields"):
            agent.validate_input(input_data, ["field1", "field2"])

    def test_validate_input_extra_fields(self, agent):
        """Test that validate_input allows extra fields."""
        input_data = {"field1": "value1", "field2": "value2", "field3": "value3"}
        # Should not raise
        agent.validate_input(input_data, ["field1", "field2"])

    def test_validate_input_empty_required(self, agent):
        """Test validate_input with no required fields."""
        input_data = {"field1": "value1"}
        # Should not raise
        agent.validate_input(input_data, [])


# ============================================================================
# Result Wrapping Helper Tests
# ============================================================================

class TestAgentResultWrapping:
    """Test result wrapping helper methods."""

    def test_wrap_result_success(self, agent):
        """Test wrapping a successful result."""
        data = {"key": "value"}
        result = agent._wrap_result(data=data)
        assert result["status"] == "ok"
        assert result["data"] == data
        assert result["error"] is None

    def test_wrap_result_error(self, agent):
        """Test wrapping an error result."""
        error_msg = "Something went wrong"
        result = agent._wrap_result(error=error_msg)
        assert result["status"] == "error"
        assert result["error"] == error_msg
        assert result["data"] is None

    def test_wrap_result_empty(self, agent):
        """Test wrapping an empty success result."""
        result = agent._wrap_result()
        assert result["status"] == "ok"
        assert result["data"] is None
        assert result["error"] is None


# ============================================================================
# Integration Tests
# ============================================================================

class TestAgentIntegration:
    """Integration tests for complete agent workflows."""

    @pytest.mark.asyncio
    async def test_full_agent_workflow(self):
        """Test complete agent initialization and use."""

        class WorkflowTestAgent(AgentCore):
            async def process(self, input_data: dict) -> dict:
                self.validate_input(input_data, ["input"])
                result = {"processed": input_data["input"].upper()}
                return self._wrap_result(data=result)

        config = AgentConfig(name="workflow-test")
        agent = WorkflowTestAgent(config)

        # Check describe
        desc = agent.describe()
        assert desc["name"] == "workflow-test"

        # Check health
        health = await agent.health()
        assert health["status"] == "ok"

        # Check process
        result = await agent.process({"input": "hello"})
        assert result["status"] == "ok"
        assert result["data"]["processed"] == "HELLO"

    @pytest.mark.asyncio
    async def test_agent_error_handling(self):
        """Test error handling in agent workflow."""

        class ErrorTestAgent(AgentCore):
            async def process(self, input_data: dict) -> dict:
                try:
                    self.validate_input(input_data, ["required"])
                    return self._wrap_result(data={"ok": True})
                except ValueError as e:
                    return self._wrap_result(error=str(e))

        config = AgentConfig(name="error-test")
        agent = ErrorTestAgent(config)

        result = await agent.process({"wrong": "field"})
        assert result["status"] == "error"
        assert "Missing required fields" in result["error"]


# ============================================================================
# Edge Cases
# ============================================================================

class TestAgentEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_agent_config_with_none_name(self):
        """Test config with None name (should work as dataclass)."""
        config = AgentConfig(name=None, version="0.1.0")
        assert config.name is None

    @pytest.mark.asyncio
    async def test_process_with_empty_input(self):
        """Test processing with empty input dict."""

        class EmptyInputAgent(AgentCore):
            async def process(self, input_data: dict) -> dict:
                return self._wrap_result(data={"received": len(input_data)})

        config = AgentConfig(name="empty-test")
        agent = EmptyInputAgent(config)

        result = await agent.process({})
        assert result["status"] == "ok"
        assert result["data"]["received"] == 0

    def test_validate_input_with_none_values(self, agent):
        """Test validation with None values in input."""
        input_data = {"field1": None, "field2": "value"}
        # Should not raise - None is a valid value
        agent.validate_input(input_data, ["field1", "field2"])


# ============================================================================
# Async/Await Tests
# ============================================================================

class TestAgentAsyncBehavior:
    """Test async/await behavior."""

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test that multiple agents can operate concurrently."""

        class SlowAgent(AgentCore):
            async def process(self, input_data: dict) -> dict:
                await asyncio.sleep(0.1)  # Simulate work
                return self._wrap_result(data={"id": input_data.get("id")})

        agents = [
            SlowAgent(AgentConfig(name=f"agent-{i}"))
            for i in range(3)
        ]

        tasks = [
            agent.process({"id": i})
            for i, agent in enumerate(agents)
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == 3
        assert all(r["status"] == "ok" for r in results)


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with async support."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async (deselect with '-m \"not asyncio\"')"
    )


# ============================================================================
# Fleet-Standard Interface Tests — SCAFFOLD (adapt for each new agent)
# Added Nightkeeper 2026-04-23 after promoting pattern from smartscale,
# bioacoustic, and carbon-bridge.
#
# HOW TO USE:
#   1. Replace "YourAgentCore" with the agent's concrete class.
#   2. Replace "your-agent-name" with agent.yaml `name` field.
#   3. Replace "0.1.0" with the version from agent.yaml.
#   4. Adjust async marks: if health()/process() are sync, remove @pytest.mark.asyncio.
#   5. Fill in the `_VALID_OPERATIONS` list and add one valid-call test per op.
#   6. Check whether process() uses "action" or "operation" key (varies by agent).
#   7. If the agent's process() calls input_data.get() OUTSIDE a try/except,
#      document the non-dict gap in the class docstring and skip that test.
#
# INVARIANTS THIS CLASS PINS:
#   - health() → {status, agent, version, timestamp} (fleet-standard keys)
#   - describe() → {name, version, capabilities, inputs, outputs}
#   - describe().name == health().agent (config consistency)
#   - describe().capabilities is non-empty
#   - process() never raises on invalid/missing action (returns error dict)
#   - ValidationError path returns: {status, error_type, field, value, constraint,
#     message, timestamp}
# ============================================================================

# _VALID_OPERATIONS = ["op1", "op2"]  # fill in per-agent


# class TestFleetStandardInterface:
#     """Verify process()/health()/describe() contract — fleet-wide standard.
#
#     Adapt this scaffold by un-commenting, substituting YourAgentCore, and
#     filling in agent-specific operations. See bioacoustic-agent and
#     carbon-bridge-agent tests for real examples.
#     """
#
#     @pytest.fixture(autouse=True)
#     def setup_agent(self, agent_config):
#         self.agent = YourAgentCore(agent_config)
#
#     # --- health() -----------------------------------------------------------
#
#     @pytest.mark.asyncio
#     async def test_health_returns_dict(self):
#         assert isinstance(await self.agent.health(), dict)
#
#     @pytest.mark.asyncio
#     async def test_health_has_required_keys(self):
#         h = await self.agent.health()
#         for key in ("status", "agent", "version", "timestamp"):
#             assert key in h, f"health() missing fleet-standard key '{key}'"
#
#     @pytest.mark.asyncio
#     async def test_health_status_is_ok(self):
#         assert (await self.agent.health())["status"] == "ok"
#
#     @pytest.mark.asyncio
#     async def test_health_timestamp_is_iso8601(self):
#         datetime.fromisoformat((await self.agent.health())["timestamp"])
#
#     # --- describe() ---------------------------------------------------------
#
#     def test_describe_returns_dict(self):
#         assert isinstance(self.agent.describe(), dict)
#
#     def test_describe_has_required_keys(self):
#         d = self.agent.describe()
#         for key in ("name", "version", "capabilities", "inputs", "outputs"):
#             assert key in d, f"describe() missing fleet-standard key '{key}'"
#
#     def test_describe_capabilities_non_empty(self):
#         assert len(self.agent.describe()["capabilities"]) > 0
#
#     def test_describe_name_health_agent_consistent(self):
#         assert self.agent.describe()["name"] == self.agent.config.name
#
#     # --- process() ----------------------------------------------------------
#
#     @pytest.mark.asyncio
#     async def test_process_missing_action_returns_error(self):
#         """Empty payload → error (no raise)."""
#         result = await self.agent.process({})
#         assert isinstance(result, dict)  # never raises
#         # Adapt: check result.get("status") == "error" or "error" in result
#
#     @pytest.mark.asyncio
#     async def test_process_unknown_action_returns_error(self):
#         """Unknown action/operation → error dict (no raise)."""
#         result = await self.agent.process({"action": "__not_real__"})
#         assert isinstance(result, dict)
#
#     @pytest.mark.asyncio
#     async def test_process_validation_error_envelope_keys(self):
#         """ValidationError path must include structured envelope keys."""
#         # Provide a payload that triggers a ValidationError in your agent.
#         result = await self.agent.process({"action": "your_op", "bad_field": None})
#         if result.get("error_type") == "ValidationError":
#             for key in ("status", "error_type", "field", "value",
#                         "constraint", "message", "timestamp"):
#                 assert key in result, f"ValidationError envelope missing '{key}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
