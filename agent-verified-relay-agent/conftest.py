"""Ensure the agent dir is importable so `from src.core import ...` resolves."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
