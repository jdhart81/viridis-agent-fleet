"""The hosted gateway admits a mounted agent only if its agent.yaml records
both revenue_model and thesis_connection (private admission invariant AA3).
A vendoring update dropped thesis_connection from wavefunction-search-agent,
which would have failed the next hosted pin advance.
"""
from pathlib import Path

import pytest
import yaml

FLEET = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("agent", ["wavefunction-search-agent"])
def test_mounted_agent_records_revenue_model_and_thesis(agent):
    record = yaml.safe_load((FLEET / agent / "agent.yaml").read_text())
    assert str(record.get("revenue_model") or "").strip(), agent
    assert str(record.get("thesis_connection") or "").strip(), agent
