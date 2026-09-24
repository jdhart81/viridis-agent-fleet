# Claude Code Skill Template

This file serves as the SKILL.md for deploying this agent as a Claude Code Skill.

```yaml
---
name: My Agent Skill
description: |
  Brief description of what this agent does and why it's useful.

  This is a Claude Code Skill that wraps the core agent logic,
  making it available in the Claude Code environment with typed inputs/outputs.
commands:
  - name: process
    description: Process input through the agent and return results
    params:
      input_data:
        type: object
        required: true
        description: |
          Agent-specific input data. Structure depends on agent implementation.
          Example: {"text": "input to process", "config": {"option": "value"}}
---
```

## How to Use This Skill

### Installation

1. Create a new directory: `my-agent.skill/`
2. Copy this file as `my-agent.skill/SKILL.md`
3. Copy `src/core.py` into the same directory
4. Zip it: `my-agent.skill.zip`
5. Reference in Claude Code:
   ```
   /import path/to/my-agent.skill.zip
   ```

### Example Usage in Claude Code

```python
# Import the skill
from my_agent_skill import process

# Call the agent
result = await process({
    "input_field": "some value",
    "optional_field": "another value"
})

# Handle result
if result["status"] == "ok":
    data = result["data"]
else:
    error = result["error"]
```

## Implementation Details

When you use this skill in Claude Code, it:

1. Imports `src/core.py` which contains your `AgentCore` subclass
2. Instantiates the agent with configuration from environment/defaults
3. Calls `agent.process()` with your input data
4. Returns results in the standard format: `{status, data, error}`

## Customizing for Your Agent

### Step 1: Update the SKILL.md Header

Replace the frontmatter with your agent's actual metadata:

```yaml
---
name: "Your Agent Name"
description: "What your agent does"
commands:
  - name: process
    description: "Your processing description"
    params:
      your_input_field:
        type: "string|object|array"
        required: true
        description: "What this field does"
---
```

### Step 2: Implement Your AgentCore

In `src/core.py`, subclass `AgentCore`:

```python
from src.core import AgentCore, AgentConfig

class MyAgent(AgentCore):
    async def process(self, input_data: dict) -> dict:
        """
        Your business logic.

        Receives input_data from Claude Code.
        Returns standard dict: {status, data, error}
        """
        self.validate_input(input_data, required_fields=["field1", "field2"])

        # Do work
        result = await self._do_work(input_data)

        return self._wrap_result(data=result)

    def describe(self) -> dict:
        return {
            "name": self.config.name,
            "version": self.config.version,
            "capabilities": ["what_it_does"],
            "inputs": {
                "field1": "str",
                "field2": "str"
            },
            "outputs": {
                "status": "str",
                "result": "dict"
            }
        }
```

### Step 3: Package for Claude Code

```bash
# Create skill directory
mkdir my-agent.skill

# Copy files
cp adapters/claude_skill.md my-agent.skill/SKILL.md
cp src/core.py my-agent.skill/

# Create __init__.py so Python treats it as a module
touch my-agent.skill/__init__.py

# Zip it
zip -r my-agent.skill.zip my-agent.skill/

# Use in Claude Code
/import ./my-agent.skill.zip
```

## Standard Response Format

All agent skills return this standard format:

```python
{
    "status": "ok" | "error",
    "data": <result_data>,  # Present if status is "ok"
    "error": <error_message>  # Present if status is "error"
}
```

## Advanced: Using Multiple Skills Together

You can compose agents by calling one skill from another:

```python
from my_agent_skill import process as my_agent_process
from another_agent_skill import process as another_process

async def pipeline(input_data):
    # Step 1: First agent
    result1 = await my_agent_process(input_data)

    if result1["status"] != "ok":
        return result1

    # Step 2: Second agent (feeding output of first)
    result2 = await another_process({"input": result1["data"]})

    return result2
```

## Debugging in Claude Code

If something isn't working:

1. Check the skill imports:
   ```python
   from my_agent_skill import process
   print(await process.__doc__)  # See what the function does
   ```

2. Test with minimal input:
   ```python
   result = await process({"test": "value"})
   print(result)  # See the actual response
   ```

3. Check logs in the skill's core module for detailed error information.

## FAQ

**Q: Can I call this skill from other skills?**
A: Yes, import it and await its `process()` function.

**Q: Do I need to handle errors differently?**
A: The skill wraps errors in the standard format. Check `result["status"]` and `result["error"]`.

**Q: Can I use async/await in my skill?**
A: Yes, Claude Code supports async skills. Your `process()` method can be async.

**Q: How do I add dependencies (packages)?**
A: Add them to a `requirements.txt` file in the `.skill` directory, and Claude Code will install them.
