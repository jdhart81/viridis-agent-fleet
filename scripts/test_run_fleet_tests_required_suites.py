"""Pins the live commerce suites into the fleet/Nightkeeper release gate."""

import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "fleet_test_runner_contract", ROOT / "run_fleet_tests.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_hive_suite_cannot_silently_disappear_from_nightkeeper():
    runner = _load_runner()
    assert "agent-hive-orchestrator-agent" in runner.REQUIRED_AGENT_SUITES
    assert "agent-hive-orchestrator-agent" in runner.AGENTS
    assert len(runner.AGENTS) == len(set(runner.AGENTS))


def test_runner_root_is_absolute_for_relative_cli_invocation():
    runner = _load_runner()
    assert runner.FLEET_ROOT.is_absolute()
    for suite in (
        "deploy/payments",
        "deploy/glama",
        "deploy/gateway",
        "deploy/droplet",
        "scripts",
    ):
        assert (runner.FLEET_ROOT / suite).is_dir()


def test_deployment_safety_tests_are_part_of_the_authoritative_gate():
    runner = _load_runner()

    assert "deploy/droplet" in runner.AGENTS
    assert (
        runner.FLEET_ROOT
        / "deploy/droplet/test_regulatory_radar_wedge_probe.py"
    ).is_file()
    assert (
        runner.FLEET_ROOT
        / "deploy/droplet/test_regulatory_radar_wedge_public_probe.py"
    ).is_file()
    assert (
        runner.FLEET_ROOT
        / "deploy/droplet/test_promote_regulatory_radar_gateway_wedge.py"
    ).is_file()
    assert (
        runner.FLEET_ROOT
        / "deploy/droplet/test_regulatory_radar_promotion_backup_gate.py"
    ).is_file()
    assert (
        runner.FLEET_ROOT
        / "deploy/droplet/test_regulatory_radar_growth_runtime_probe.py"
    ).is_file()
    assert (
        runner.FLEET_ROOT / "deploy/droplet/test_growth_state_backup.py"
    ).is_file()
    assert (
        runner.FLEET_ROOT / "deploy/droplet/test_gateway_state_backup.py"
    ).is_file()


def test_infrastructure_suites_keep_fleet_root_on_pythonpath():
    runner = _load_runner()
    scripts_dir = runner.FLEET_ROOT / "scripts"
    entries = runner._pythonpath_for(scripts_dir).split(os.pathsep)
    assert str(runner.FLEET_ROOT) in entries
    assert str(scripts_dir) in entries
