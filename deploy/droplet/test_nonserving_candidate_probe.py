import json

import pytest

from deploy.droplet import nonserving_candidate_probe as probe


def test_decode_sse_returns_result():
    raw = (
        b"event: message\r\n"
        b'data: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\r\n\r\n'
    )
    assert probe._decode_sse(raw) == {"tools": []}


@pytest.mark.parametrize("raw", [
    b"",
    b"event: message\n",
    b'data: {"jsonrpc":"2.0","id":1,"error":{"code":-1}}\n',
])
def test_decode_sse_fails_closed(raw):
    with pytest.raises(probe.ProbeFailure):
        probe._decode_sse(raw)


def test_health_gate_proves_release_isolation(monkeypatch):
    payload = {
        "status": "ok",
        "mount_errors": {},
        "persistence": {"available": True, "errors": {}},
        "agents": {
            **{f"agent-{index}": {"version": "x"} for index in range(24)},
            "hive": {"version": "0.1.4"},
            "wavefunction": {"version": "0.1.1"},
            "subscriptions-shadow": {"version": "x"},
        },
        "subscriptions": {"version": "0.1.0"},
    }
    monkeypatch.setattr(probe, "get_json", lambda base: payload)
    assert probe.health_gate("http://127.0.0.1:18402", "hive") == payload


def test_health_gate_rejects_cross_bundled_release(monkeypatch):
    payload = {
        "status": "ok",
        "mount_errors": {},
        "persistence": {"available": True, "errors": {}},
        "agents": {
            **{f"agent-{index}": {"version": "x"} for index in range(24)},
            "hive": {"version": "0.1.4"},
            "wavefunction": {"version": "0.2.0"},
            "subscriptions-shadow": {"version": "x"},
        },
        "subscriptions": {"version": "0.1.0"},
    }
    monkeypatch.setattr(probe, "get_json", lambda base: payload)
    with pytest.raises(probe.ProbeFailure, match="release isolation mismatch"):
        probe.health_gate("http://127.0.0.1:18402", "hive")


def test_non_loopback_base_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["probe", "--release", "hive", "--base", "https://example.com"],
    )
    assert probe.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
