"""
Fleet-wide pytest configuration.

SETUP: Run tests with:
    pip install pytest pytest-asyncio
    python -m pytest   (from fleet root)

ASYNC MODE: pyproject.toml sets asyncio_mode = "auto" — pytest-asyncio
automatically handles all async test functions fleet-wide. No manual
asyncio marker is needed in individual test files or conftest.py hooks.

PREVIOUS CONFLICT (resolved): This file previously defined a
pytest_collection_modifyitems hook that added @pytest.mark.asyncio markers
manually. This conflicted with asyncio_mode = "auto" in pyproject.toml,
causing double-marking warnings and potential collection errors when
pytest-asyncio was not installed. The hook has been removed; asyncio_mode
= "auto" is the single authoritative source of async test configuration.

PATH SETUP: Each agent conftest.py (e.g. energyai-agent/conftest.py) runs
    sys.path.insert(0, str(Path(__file__).parent))
so agent-local tests can import from that agent's src/ directory. The root
conftest intentionally does NOT add any paths to avoid polluting the import
namespace across 30+ agent directories.
"""
