"""Security-plane federation invariants.

Viridis Security stays on its own runtime and billing boundary while the fleet
publishes one coherent discovery surface. No API key is copied into the fleet.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from starlette.testclient import TestClient


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import viridis_mcp_gateway as gateway  # noqa: E402


def _security_member() -> dict:
    return next(
        member for member in gateway.EXTERNAL_MEMBERS
        if member["identifier"] ==
        "urn:air:viridis:security-injection-detector")


def test_sp1_security_provider_is_federated_without_credentials():
    member = _security_member()
    assert member["url"] == "https://mcp.viridis-security.com/mcp"
    assert member["capabilities"] == [
        "detect_injection", "detect_trace_tool_policy"]
    assert member["category"] == "security-plane"
    assert member["auth"] == "Bearer API key"
    assert member["signup"].startswith("https://mcp.viridis-security.com/")
    serialized = repr(member).lower()
    assert "private_key" not in serialized
    assert "api_key=" not in serialized
    assert "vulnerability-free guarantee" in member["metadata"]["claimBoundary"]


def test_sp2_directory_and_ard_publish_the_security_plane(tmp_path):
    old_state_db = os.environ.get("STATE_DB")
    os.environ["STATE_DB"] = str(tmp_path / "security-federation.sqlite3")
    try:
        with TestClient(gateway.build_app()) as client:
            directory_response = client.get("/")
            ard_response = client.get("/.well-known/ai-catalog.json")
    finally:
        if old_state_db is None:
            os.environ.pop("STATE_DB", None)
        else:
            os.environ["STATE_DB"] = old_state_db

    assert directory_response.status_code == 200
    directory = directory_response.json()
    member = next(
        item for item in directory["federated_members"]
        if item["name"] == "Viridis Security Injection Detector")
    assert member["role"] == "security-posture-provider"
    assert member["auth"] == "Bearer API key"

    assert ard_response.status_code == 200
    ard = ard_response.json()
    entry = next(
        item for item in ard["entries"]
        if item["identifier"] ==
        "urn:air:viridis:security-injection-detector")
    assert "mcp-security" in entry["tags"]
    assert entry["metadata"]["securityPlane"] is True
    assert entry["capabilities"] == [
        "detect_injection", "detect_trace_tool_policy"]
