#!/usr/bin/env python3
"""Fleet watch: turn the live probe plus gateway self-reports into alerts.

Runs after scripts/fleet_live_probe.py in the fleet-live-probe workflow. It
reads the probe's JSON, the gateway's public /healthz, the payment surfaces
and (when the gateway serves it) per-tool outcome counts, decides what is
broken, and sends a notice only when something changes: to a Slack incoming
webhook when one is configured, otherwise to one "Fleet alert" GitHub issue
in this repository (opened on a fault, commented on each change, closed on
recovery), which GitHub emails to the owner with no extra secret.

Stdlib only. Nothing here calls a paid tool or moves money.

Invariants (checked by scripts/test_fleet_watch.py):
  W1  every finding has a stable key "<kind>:<subject>", so the same fault on
      two runs is the same finding
  W2  a notice is sent only when the set of active findings changes (new or
      recovered), or as a reminder when findings stay active for
      --remind-hours since the last notice
  W3  subjects on the ignore list never alert, but are reported as ignored
  W4  the webhook URL comes only from the environment, is never printed, and
      a failed send never changes the exit code
  W5  x402 verify/settle failures alert; a malformed payment header from a
      caller is information only
  W6  the Stripe webhook check alerts on a missing route (404) or a server
      error; a 503 "secret not loaded" alerts only when the secret is expected
  W7  an unreachable or non-JSON /healthz is one gateway_down finding; when
      /healthz answers, every degraded agent and every mount error is its own
      finding
  W8  every probed server that is not up is its own finding
  W9  a tool alerts when its server-error rate over the window is above the
      threshold with at least --min-calls real calls; payment-required and
      caller-input errors never count as failures
  W10 exit code is 0 iff no non-ignored finding is active
  W11 with no Slack webhook, notices go to at most one open "Fleet alert"
      issue: opened when faults appear, commented on each later change and
      closed when all recover; finding text is fenced so it can't mention
      anyone, only FLEET_ALERT_MENTION is mentioned, and the token comes only
      from the environment and is never printed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

UA = "viridis-fleet-probe/1.0 (+synthetic health check; exclude from usage stats)"
GATEWAY = "https://mcp.viridisconservation.com"


def http(method: str, url: str, body: bytes | None = None,
         headers: dict | None = None, timeout: float = 20):
    """Return (status, text). status 0 means the request never got an answer."""
    h = {"User-Agent": UA, **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # DNS, TLS, timeout, refused
        return 0, f"{type(e).__name__}: {e}"


def _f(kind: str, subject: str, detail: str, severity: str = "alert") -> dict:
    return {"key": f"{kind}:{subject}", "kind": kind, "subject": subject,
            "detail": detail[:300], "severity": severity}


# ---------------------------------------------------------------- checks --

def check_probe(probe: dict) -> list:
    """W8: one finding per listed server that failed the MCP handshake."""
    out = []
    for r in probe.get("results", []):
        if not r.get("up") or r.get("describe_ok") is False:
            out.append(_f("server_down", r.get("name", "?"),
                          r.get("error") or "not up"))
    if not probe.get("results"):
        out.append(_f("probe_empty", "registry", "probe found no servers to check"))
    return out


def check_healthz(status: int, text: str) -> list:
    """W5/W7: gateway self-report, including the payment gate's last errors."""
    try:
        h = json.loads(text)
        assert isinstance(h, dict)
    except Exception:
        return [_f("gateway_down", "healthz",
                   f"HTTP {status}: {text[:160]}" if status else text)]
    out = []
    for mount, err in sorted((h.get("mount_errors") or {}).items()):
        out.append(_f("mount_error", mount, str(err)))
    for path, a in sorted((h.get("agents") or {}).items()):
        if isinstance(a, dict) and a.get("status") != "ok" and path not in (h.get("mount_errors") or {}):
            out.append(_f("agent_degraded", path,
                          a.get("message") or a.get("error_type") or str(a.get("status"))))
    p = h.get("persistence") or {}
    if p and (not p.get("available") or p.get("errors")):
        out.append(_f("persistence", "state_db", json.dumps(p.get("errors") or "unavailable")))
    subs = h.get("subscriptions") or {}
    if subs and subs.get("status") not in (None, "ok"):
        out.append(_f("agent_degraded", "subscriptions",
                      subs.get("message") or str(subs.get("status"))))
    gate = h.get("payment_gate") or {}
    for name, err in sorted(((gate.get("x402") or {}).get("errors") or {}).items()):
        err = str(err)
        if err.startswith("malformed"):
            out.append(_f("x402_bad_header", name, err, severity="info"))
        else:
            out.append(_f("x402_failed", name, err))
    for name, err in sorted((gate.get("errors") or {}).items()):
        out.append(_f("metering_failed", name, str(err)))
    hub = h.get("hub_kernel") or {}
    if hub.get("errors"):
        out.append(_f("hub_kernel", "errors", json.dumps(hub["errors"])))
    if h.get("status") != "ok" and not out:
        out.append(_f("gateway_degraded", "healthz", f"status={h.get('status')}"))
    return out


def check_stripe_webhook(status: int, text: str, secret_expected: bool) -> list:
    """W6: an unsigned POST must be refused with 400 once the secret is set."""
    if status == 400:
        return []
    if status == 503:
        return [_f("stripe_webhook", "secret",
                   "webhook route answers 503: signing secret not loaded",
                   severity="alert" if secret_expected else "info")]
    if status == 404:
        return [_f("stripe_webhook", "route",
                   "POST /stripe/webhook returns 404: route not deployed",
                   severity="alert" if secret_expected else "info")]
    return [_f("stripe_webhook", "route", f"unexpected HTTP {status}: {text[:120]}")]


def check_x402_manifest(status: int, text: str) -> list:
    """Agents discover prices here; if it breaks, paid discovery breaks."""
    try:
        ok = status == 200 and isinstance(json.loads(text), (dict, list))
    except Exception:
        ok = False
    return [] if ok else [_f("x402_manifest", "well-known",
                             f"HTTP {status}: manifest unreadable")]


def check_tool_outcomes(status: int, text: str, max_error_rate: float,
                        min_calls: int) -> list:
    """W9: tools whose own failures exceed the threshold."""
    if status == 404:
        return []  # gateway build without the tool-outcome recorder yet
    try:
        data = json.loads(text)
    except Exception:
        return [_f("tool_outcomes", "endpoint", f"HTTP {status}: unreadable")]
    out = []
    for t in data.get("tools", []):
        real = t.get("ok", 0) + t.get("server_error", 0)
        if real < min_calls:
            continue
        rate = t.get("server_error", 0) / real
        if rate > max_error_rate:
            out.append(_f("tool_failing", f"{t.get('mount')}/{t.get('tool')}",
                          f"{t.get('server_error')} of {real} calls failed "
                          f"({rate:.0%}) in the last {data.get('window_hours')}h"))
    return out


# ----------------------------------------------------------------- state --

def diff(prev: dict, findings: list, ignore: set, now: float,
         remind_hours: float) -> dict:
    """W2/W3/W10: compare with the previous run and decide whether to notify."""
    alerts = {f["key"]: f for f in findings
              if f["severity"] == "alert" and f["subject"] not in ignore}
    ignored = [f for f in findings if f["severity"] == "alert" and f["subject"] in ignore]
    before = prev.get("active", {})
    new = sorted(k for k in alerts if k not in before)
    recovered = sorted(k for k in before if k not in alerts)
    last = float(prev.get("last_notice", 0) or 0)
    remind = bool(alerts) and not new and not recovered and \
        (now - last) >= remind_hours * 3600
    active = {k: {"since": before.get(k, {}).get("since", now),
                  "detail": alerts[k]["detail"]} for k in alerts}
    notify = bool(new or recovered or remind)
    return {"active": active, "new": new, "recovered": recovered,
            "remind": remind, "notify": notify, "ignored": ignored,
            "info": [f for f in findings if f["severity"] == "info"],
            "last_notice": now if notify else last}


def message(d: dict, run_url: str = "") -> str:
    n = len(d["active"])
    head = (":red_circle: Viridis fleet: " + (f"{n} problem" + ("s" if n != 1 else ""))
            if n else ":large_green_circle: Viridis fleet: all clear")
    lines = [head]
    if d["new"]:
        lines.append("New:")
        lines += [f"  - {k}: {d['active'][k]['detail']}" for k in d["new"]]
    if d["recovered"]:
        lines.append("Recovered:")
        lines += [f"  - {k}" for k in d["recovered"]]
    if d["remind"]:
        lines.append("Still failing:")
        for k, v in sorted(d["active"].items()):
            hrs = (time.time() - v["since"]) / 3600
            lines.append(f"  - {k} (for {hrs:.1f}h): {v['detail']}")
    if run_url:
        lines.append(run_url)
    return "\n".join(lines)


def send_slack(text: str) -> bool:
    """W4: URL only from env; never printed; failure never raises."""
    url = os.environ.get("FLEET_ALERT_SLACK_WEBHOOK", "").strip()
    if not url:
        print("alert channel: none configured (set FLEET_ALERT_SLACK_WEBHOOK)")
        return False
    status, _ = http("POST", url, json.dumps({"text": text}).encode(),
                     {"Content-Type": "application/json"})
    print(f"alert channel: slack answered {status}")
    return 200 <= status < 300


ISSUE_TITLE = "Fleet alert"


def _gh(method: str, path: str, token: str, payload: dict | None = None):
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    body = json.dumps(payload).encode() if payload is not None else None
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28"}
    if body is not None:
        hdr["Content-Type"] = "application/json"
    status, text = http(method, api + path, body, hdr)
    try:
        return status, json.loads(text)
    except ValueError:
        return status, None


def send_issue(d: dict, text: str, run_url: str = "") -> bool:
    """W11: one open "Fleet alert" issue per outage; W4 rules for the token."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        print("alert channel: none configured (no Slack webhook, no GITHUB_TOKEN)")
        return False
    st, issues = _gh("GET", f"/repos/{repo}/issues?state=open&per_page=50", token)
    if st != 200 or not isinstance(issues, list):
        print(f"alert channel: github issues answered {st}")
        return False
    mine = [i for i in issues if not i.get("pull_request")
            and str(i.get("title", "")).startswith(ISSUE_TITLE)
            and (i.get("user") or {}).get("login") == "github-actions[bot]"]
    who = os.environ.get("FLEET_ALERT_MENTION", "").strip().lstrip("@")
    ping = f"@{who} " if who and all(c.isalnum() or c == "-" for c in who) else ""
    fenced = text.replace("`", "'")          # W11: no way out of the fence
    body = f"{ping}\n```\n{fenced}\n```\n{run_url}".strip()
    n = len(d["active"])
    title = f"{ISSUE_TITLE}: {n} fleet problem" + ("s" if n != 1 else "")
    if mine:
        num = mine[0]["number"]
        st, _ = _gh("POST", f"/repos/{repo}/issues/{num}/comments", token, {"body": body})
        patch = {"title": title} if n else {"state": "closed", "state_reason": "completed"}
        st2, _ = _gh("PATCH", f"/repos/{repo}/issues/{num}", token, patch)
        print(f"alert channel: github issue #{num} updated ({st}/{st2})")
        return st == 201 and st2 == 200
    if not n:
        print("alert channel: all clear and no open alert issue; nothing to send")
        return True
    st, _ = _gh("POST", f"/repos/{repo}/issues", token, {"title": title, "body": body})
    print(f"alert channel: github issue opened ({st})")
    return st == 201


def send_notice(d: dict, text: str, run_url: str = "") -> bool:
    """Slack when a webhook is configured, otherwise the GitHub issue."""
    if os.environ.get("FLEET_ALERT_SLACK_WEBHOOK", "").strip():
        return send_slack(text)
    return send_issue(d, message(d), run_url)


# ------------------------------------------------------------------ main --

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probe", default="fleet_probe.json")
    ap.add_argument("--state", default=".fleet-watch/state.json")
    ap.add_argument("--gateway", default=os.environ.get("FLEET_GATEWAY", GATEWAY))
    ap.add_argument("--ignore", default=os.environ.get("FLEET_ALERT_IGNORE", ""),
                    help="comma-separated subjects never to alert on")
    ap.add_argument("--remind-hours", type=float, default=6.0)
    ap.add_argument("--max-error-rate", type=float, default=0.05)
    ap.add_argument("--min-calls", type=int, default=20)
    ap.add_argument("--window-hours", type=int, default=24)
    ap.add_argument("--summary", default="")
    a = ap.parse_args(argv)

    secret_expected = os.environ.get("STRIPE_WEBHOOK_EXPECTED", "0") == "1"
    try:
        probe = json.load(open(a.probe))
    except Exception as e:
        probe = {"results": [], "error": str(e)}
    findings = check_probe(probe)
    findings += check_healthz(*http("GET", a.gateway + "/healthz"))
    findings += check_x402_manifest(*http("GET", a.gateway + "/.well-known/x402.json"))
    findings += check_stripe_webhook(
        *http("POST", a.gateway + "/stripe/webhook", b"{}",
              {"Content-Type": "application/json"}), secret_expected)
    findings += check_tool_outcomes(
        *http("GET", f"{a.gateway}/stats/tool-outcomes?hours={a.window_hours}"),
        a.max_error_rate, a.min_calls)

    try:
        prev = json.load(open(a.state))
    except Exception:
        prev = {}
    ignore = {s.strip() for s in a.ignore.split(",") if s.strip()}
    d = diff(prev, findings, ignore, time.time(), a.remind_hours)
    os.makedirs(os.path.dirname(a.state) or ".", exist_ok=True)
    with open(a.state, "w") as f:
        json.dump({"active": d["active"], "last_notice": d["last_notice"]}, f, indent=1)

    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                   f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/"
                   f"{os.environ['GITHUB_RUN_ID']}")
    text = message(d, run_url)
    report = text + "\n"
    if d["ignored"]:
        report += "Ignored: " + ", ".join(f["key"] for f in d["ignored"]) + "\n"
    if d["info"]:
        report += "Info: " + "; ".join(f"{f['key']} ({f['detail']})" for f in d["info"]) + "\n"
    print(report)
    if a.summary:
        with open(a.summary, "a") as f:
            f.write("\n## Fleet watch\n\n```\n" + report + "```\n")
    if d["notify"]:
        try:
            send_notice(d, text, run_url)
        except Exception as e:  # W4: a failed send never changes the exit code
            print(f"alert channel: send failed ({type(e).__name__})")
    return 1 if d["active"] else 0


if __name__ == "__main__":
    sys.exit(main())
