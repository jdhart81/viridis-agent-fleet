"""Offline tests for fleet_watch.py: invariants W1-W10 against fake gateways."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_watch as w  # noqa: E402

HEALTHY = {"status": "ok", "mount_errors": {},
           "agents": {"escrow": {"status": "ok"}},
           "persistence": {"available": True, "errors": {}},
           "subscriptions": {"status": "ok"},
           "payment_gate": {"x402": {"errors": {}}, "errors": {}},
           "hub_kernel": {"enabled": True, "errors": {}}}


def keys(fs, severity="alert"):
    return sorted(f["key"] for f in fs if f["severity"] == severity)


# W8
def test_probe_down_servers_are_separate_findings():
    probe = {"results": [{"name": "a", "up": True},
                         {"name": "b", "up": False, "error": "initialize: HTTP 404"},
                         {"name": "c", "up": True, "describe_ok": False}]}
    assert keys(w.check_probe(probe)) == ["server_down:b", "server_down:c"]


def test_empty_probe_alerts():
    assert keys(w.check_probe({"results": []})) == ["probe_empty:registry"]


# W7
def test_healthy_gateway_has_no_findings():
    assert w.check_healthz(200, json.dumps(HEALTHY)) == []


def test_unreachable_gateway_is_one_finding():
    assert keys(w.check_healthz(0, "URLError: refused")) == ["gateway_down:healthz"]
    assert keys(w.check_healthz(502, "<html>bad gateway</html>")) == ["gateway_down:healthz"]


def test_each_mount_error_and_degraded_agent_is_its_own_finding():
    h = dict(HEALTHY, status="degraded",
             mount_errors={"maxwell": "adapter_import_failed", "wu-wei": "x"},
             agents={"escrow": {"status": "ok"}, "ghg": {"status": "degraded", "message": "db"},
                     "maxwell": {"status": "degraded"}})
    assert keys(w.check_healthz(503, json.dumps(h))) == [
        "agent_degraded:ghg", "mount_error:maxwell", "mount_error:wu-wei"]


def test_degraded_without_detail_still_alerts():
    h = dict(HEALTHY, status="degraded")
    assert keys(w.check_healthz(503, json.dumps(h))) == ["gateway_degraded:healthz"]


# W5
def test_x402_settle_failure_alerts_malformed_header_is_info():
    h = json.loads(json.dumps(HEALTHY))
    h["payment_gate"]["x402"]["errors"] = {"ghg": "x402:settle:insufficient_funds",
                                           "radar": "malformed_x402_header",
                                           "takeoff": "x402_exception:TimeoutError"}
    fs = w.check_healthz(200, json.dumps(h))
    assert keys(fs) == ["x402_failed:ghg", "x402_failed:takeoff"]
    assert keys(fs, "info") == ["x402_bad_header:radar"]


def test_metering_and_persistence_failures_alert():
    h = json.loads(json.dumps(HEALTHY))
    h["payment_gate"]["errors"] = {"ghg": "metering: OSError: disk full"}
    h["persistence"] = {"available": False, "errors": {}}
    assert keys(w.check_healthz(503, json.dumps(h))) == [
        "metering_failed:ghg", "persistence:state_db"]


# W6
def test_stripe_webhook_states():
    assert w.check_stripe_webhook(400, "bad sig", True) == []
    assert keys(w.check_stripe_webhook(503, "", False), "info") == ["stripe_webhook:secret"]
    assert keys(w.check_stripe_webhook(503, "", True)) == ["stripe_webhook:secret"]
    assert keys(w.check_stripe_webhook(404, "", True)) == ["stripe_webhook:route"]
    assert keys(w.check_stripe_webhook(500, "boom", False)) == ["stripe_webhook:route"]


def test_x402_manifest():
    assert w.check_x402_manifest(200, '{"accepts": []}') == []
    assert keys(w.check_x402_manifest(502, "")) == ["x402_manifest:well-known"]


# W9
def test_tool_outcomes_threshold_ignores_payment_and_caller_errors():
    data = {"window_hours": 24, "tools": [
        {"mount": "ghg", "tool": "inventory", "ok": 90, "server_error": 10,
         "payment_required": 500, "caller_error": 300},
        {"mount": "radar", "tool": "scan", "ok": 99, "server_error": 1,
         "payment_required": 2000},
        {"mount": "rare", "tool": "x", "ok": 0, "server_error": 5}]}
    fs = w.check_tool_outcomes(200, json.dumps(data), 0.05, 20)
    assert keys(fs) == ["tool_failing:ghg/inventory"]
    assert w.check_tool_outcomes(404, "", 0.05, 20) == []


# W1, W2, W3, W10
def test_diff_notifies_only_on_change_and_reminds():
    f1 = [w._f("server_down", "a", "x")]
    d1 = w.diff({}, f1, set(), 1000.0, 6)
    assert d1["new"] == ["server_down:a"] and d1["notify"]
    prev = {"active": d1["active"], "last_notice": d1["last_notice"]}
    d2 = w.diff(prev, [w._f("server_down", "a", "x again")], set(), 1000.0 + 1800, 6)
    assert not d2["notify"] and d2["active"]["server_down:a"]["since"] == 1000.0
    prev2 = {"active": d2["active"], "last_notice": d2["last_notice"]}
    d3 = w.diff(prev2, f1, set(), 1000.0 + 6 * 3600, 6)
    assert d3["remind"] and d3["notify"]
    d4 = w.diff({"active": d3["active"], "last_notice": d3["last_notice"]},
                [], set(), 1000.0 + 7 * 3600, 6)
    assert d4["recovered"] == ["server_down:a"] and d4["notify"] and not d4["active"]


def test_ignore_list_suppresses_but_reports():
    fs = [w._f("server_down", "io.github.jdhart81/verdigraph-mcp", "401")]
    d = w.diff({}, fs, {"io.github.jdhart81/verdigraph-mcp"}, 0.0, 6)
    assert not d["active"] and not d["notify"]
    assert [f["key"] for f in d["ignored"]] == ["server_down:io.github.jdhart81/verdigraph-mcp"]


def test_info_findings_never_activate():
    d = w.diff({}, [w._f("stripe_webhook", "secret", "503", "info")], set(), 0.0, 6)
    assert not d["active"] and not d["notify"]


# W4 + end to end
class Fake(BaseHTTPRequestHandler):
    healthz = HEALTHY
    slack_posts: list = []

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, json.dumps(Fake.healthz))
        elif self.path == "/.well-known/x402.json":
            self._send(200, '{"accepts": []}')
        else:
            self._send(404, "{}")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/stripe/webhook":
            self._send(400, '{"error":"signature"}')
        elif self.path == "/slack":
            Fake.slack_posts.append(json.loads(body))
            self._send(200, "ok")
        else:
            self._send(404, "{}")


def test_end_to_end_sends_once_and_exit_codes(tmp_path, capsys):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    hook = base + "/slack"
    probe = tmp_path / "p.json"
    state = tmp_path / "s" / "state.json"
    probe.write_text(json.dumps({"results": [{"name": "a", "up": False, "error": "404"}]}))
    os.environ["FLEET_ALERT_SLACK_WEBHOOK"] = hook
    try:
        args = ["--probe", str(probe), "--state", str(state), "--gateway", base]
        assert w.main(args) == 1
        assert len(Fake.slack_posts) == 1
        assert w.main(args) == 1            # same fault: no second post
        assert len(Fake.slack_posts) == 1
        probe.write_text(json.dumps({"results": [{"name": "a", "up": True}]}))
        assert w.main(args) == 0            # recovery: one post
        assert len(Fake.slack_posts) == 2
        assert "Recovered" in Fake.slack_posts[-1]["text"]
        out = capsys.readouterr().out
        assert hook not in out              # W4: webhook URL never printed
    finally:
        os.environ.pop("FLEET_ALERT_SLACK_WEBHOOK", None)
        srv.shutdown()


def test_send_failure_does_not_change_exit(tmp_path):
    probe = tmp_path / "p.json"
    probe.write_text(json.dumps({"results": [{"name": "a", "up": True}]}))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["FLEET_ALERT_SLACK_WEBHOOK"] = "http://127.0.0.1:9/nothing"
    try:
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"active": {"server_down:a": {"since": 0, "detail": ""}},
                                     "last_notice": 0}))
        assert w.main(["--probe", str(probe), "--state", str(state),
                       "--gateway", f"http://127.0.0.1:{srv.server_port}"]) == 0
    finally:
        os.environ.pop("FLEET_ALERT_SLACK_WEBHOOK", None)
        srv.shutdown()
