"""Fleet layout shim: the Viridis open-core split requires ``src/core.py`` in every
``*-agent`` directory. The real core is ``viridis_eco_funding.fleet``."""
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from viridis_eco_funding.fleet import EcoFundingAgentCore as AgentCore  # noqa: E402,F401
from viridis_eco_funding.fleet import build  # noqa: E402,F401
