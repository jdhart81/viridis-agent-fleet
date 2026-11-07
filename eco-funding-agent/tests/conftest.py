from __future__ import annotations

import copy
import json
import random
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "examples" / "data"
if str(ROOT / "src") not in sys.path:  # fleet runner: tests run without an installed package
    sys.path.insert(0, str(ROOT / "src"))


def load_json(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture
def woodland_site() -> dict[str, Any]:
    return load_json("woodland_site.json")


@pytest.fixture
def synthetic_record() -> dict[str, Any]:
    return load_json("vergecommon_public_coop_SYNTHETIC.json")


@pytest.fixture
def example_pool() -> dict[str, Any]:
    return load_json("woodland_pool.json")


def _round(rng: random.Random, low: float, high: float, digits: int = 3) -> float:
    return round(rng.uniform(low, high), digits)


def random_site(rng: random.Random, *, thermo: bool = True, soil: bool | None = None,
                channel: bool | None = None, max_patches: int = 7) -> dict[str, Any]:
    """A random but valid vef-site/0.1 document (seeded, so tests are reproducible)."""
    n = rng.randint(1, max_patches)
    patches = [{
        "id": f"p{i}",
        "area_ha": _round(rng, 0.05, 60, 2),
        "verified": rng.random() < 0.8,
        "condition": _round(rng, 0.0, 1.0, 2),
    } for i in range(n)]
    links = []
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < 0.45:
                mode = rng.choice(["probability", "distance_m", "hdfm_linked"])
                link: dict[str, Any] = {"from": f"p{i}", "to": f"p{j}"}
                if mode == "probability":
                    link["probability"] = _round(rng, 0.01, 1.0, 3)
                elif mode == "distance_m":
                    link["distance_m"] = _round(rng, 0, 3000, 1)
                else:
                    link["hdfm_linked"] = True
                links.append(link)
    taxonomic: dict[str, Any]
    if rng.random() < 0.5:
        observations = rng.randint(50, 200_000)
        taxonomic = {"species_observed": rng.randint(1, max(1, observations // 2)),
                     "observations": observations}
    else:
        taxonomic = {"value": _round(rng, 0, 1), "sigma": _round(rng, 0, 0.2)}
    site: dict[str, Any] = {
        "site_id": f"site-{rng.randint(0, 10**6)}",
        "biodiversity": {
            "taxonomic": taxonomic,
            "productivity": {"value": _round(rng, 0, 1)},
            "functional": {"value": _round(rng, 0, 1), "sigma": _round(rng, 0, 0.2)},
            "spectral": {"value": _round(rng, 0, 1), "sigma": _round(rng, 0, 0.2)},
        },
        "habitat": {"patches": patches, "links": links},
    }
    if soil if soil is not None else rng.random() < 0.6:
        site["soil"] = {"soc_g_per_kg": _round(rng, 0, 120, 1), "ph": _round(rng, 3, 10, 2)}
        if rng.random() < 0.5:
            site["weights"] = {"soil": _round(rng, 0, 0.9, 2)}
    if thermo:
        site["thermodynamics"] = {
            "npp_gC_per_m2_yr": _round(rng, 0, 2500, 1),
            "mean_temperature_K": _round(rng, 200, 320, 2),
        }
        if channel if channel is not None else rng.random() < 0.3:
            site["thermodynamics"]["observation_channel"] = {
                "rho": _round(rng, 0, 1),
                "entropy_rate_bits_per_s": float(f"{rng.uniform(1, 9):.3f}e{rng.randint(0, 30)}"),
            }
    return site


@pytest.fixture
def rng() -> random.Random:
    return random.Random(20261107)


def clone(obj: Any) -> Any:
    return copy.deepcopy(obj)


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _guarded(real):
    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else None
        if self.family != getattr(socket, "AF_UNIX", object()) and host not in _LOOPBACK:
            raise AssertionError(f"Invariant 6 guard: outbound connection to {address!r} during tests")
        return real(self, address)
    return connect


@pytest.fixture(autouse=True)
def block_outbound_network(request, monkeypatch):
    """Invariant 6, runtime layer: no test may open a non-loopback connection unless it is
    explicitly marked ``network`` (live, opt-in). Any code path that tries to reach a
    service during the suite fails loudly."""
    if request.node.get_closest_marker("network"):
        yield
        return
    # Drop proxy settings so traffic cannot tunnel out through a loopback proxy.
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket.socket, "connect", _guarded(_real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded(_real_connect_ex))
    yield


def has_mcp_v2() -> bool:
    """The standalone vef-mcp server targets mcp 2.x; the fleet adapter supports 1.x too."""
    try:
        import mcp.server.mcpserver  # noqa: F401
        return True
    except ImportError:
        return False


requires_mcp_v2 = pytest.mark.skipif(not has_mcp_v2(), reason="standalone vef-mcp server needs mcp 2.x")
