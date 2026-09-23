import pytest

try:
    from deploy.droplet.production_smoke_guard import (
        CONFIRMATION,
        PRODUCTION_BASE,
        guarded_smoke_base,
    )
except ModuleNotFoundError:
    # run_fleet_tests.py executes this suite with deploy/droplet as its cwd.
    from production_smoke_guard import (
        CONFIRMATION,
        PRODUCTION_BASE,
        guarded_smoke_base,
    )


def test_smoke_defaults_to_local_candidate(monkeypatch):
    monkeypatch.delenv("VIRIDIS_SMOKE_BASE", raising=False)
    monkeypatch.delenv("VIRIDIS_PRODUCTION_SMOKE_WRITES", raising=False)
    assert guarded_smoke_base() == "http://127.0.0.1:8402"


def test_production_requires_explicit_write_confirmation(monkeypatch):
    monkeypatch.setenv("VIRIDIS_SMOKE_BASE", PRODUCTION_BASE)
    monkeypatch.delenv("VIRIDIS_PRODUCTION_SMOKE_WRITES", raising=False)
    with pytest.raises(RuntimeError, match="production-writing smoke blocked"):
        guarded_smoke_base()
    monkeypatch.setenv("VIRIDIS_PRODUCTION_SMOKE_WRITES", CONFIRMATION)
    assert guarded_smoke_base() == PRODUCTION_BASE
