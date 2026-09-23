#!/usr/bin/env python3
"""Exact-image, copied-state rollout for the authorized static Security migration.

Run prepare, copy and verify backups off-host, then rehearse, then promote.
No paid request, message, subscription, or customer record is created.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request

BASE = "sha256:86d33ab91da753ff117619119846043aca30be96a4b79f48df1bb6f72427643e"
LIVE = "viridis-fleet-gateway-1"
ROOT = Path("/root/viridis-candidates/maxwell-origin-20260913")
SOURCE = Path("/root/viridis-fleet")
ROLLBACK = "viridis-stable:rollback-maxwell-origin-20260913"
CANDIDATE = "viridis-stable:maxwell-origin-20260913"
REHEARSAL = "viridis-maxwell-origin-rehearsal-20260913"
PUBLIC = "https://mcp.viridisconservation.com"
LOCAL = "http://127.0.0.1:18407"
WATCH_PATH = "/security-preflight/watch"
INPUTS = {"agent_id": "release-rehearsal-only", "manifest": {
    "endpoint": "https://example.invalid/mcp", "auth": "bearer", "tools": [{
        "name": "read_status", "input_schema": {"type": "object", "properties": {},
                                                  "additionalProperties": False}}]},
    "policy": {"allowed_tools": ["read_status"]}, "sample_inputs": ["ordinary fixture"]}


def run(*args, timeout=180, stdin=None):
    result = subprocess.run(args, input=stdin, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        # Environment and output can contain secrets. Keep diagnostics private.
        (ROOT / "last-command-error.log").write_text(result.stdout + result.stderr)
        raise RuntimeError(f"command failed: {args[0]} {args[1] if len(args)>1 else ''}")
    return result.stdout.strip()


def save(name, data):
    (ROOT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def inspect(container=LIVE):
    return json.loads(run("docker", "inspect", container))[0]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_base():
    info = inspect()
    assert info["Image"] == BASE
    assert info["State"]["Health"]["Status"] == "healthy"
    assert run("docker", "image", "inspect", "--format", "{{.Id}}", "viridis-stable:latest") == BASE
    return info


def database_evidence(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok"
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        counts = {name: db.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                  for name in tables}
    return {"integrity": integrity, "tables": counts, "sha256": sha(path)}


def prepare():
    assert not (ROOT / "prepared.json").exists(), "prepare already completed"
    info = expected_base()
    manifest = json.loads((ROOT / "payload-manifest.json").read_text())
    for item in manifest["files"]:
        rel = item["path"]
        assert not Path(rel).is_absolute() and ".." not in Path(rel).parts
        assert sha(ROOT / "overlay" / rel) == item["sha256"]
    for rel, digest in manifest["base_sources"].items():
        actual = run("docker", "exec", LIVE, "sha256sum", "/fleet/" + rel).split()[0]
        assert actual == digest, rel
    data = next(Path(m["Source"]) for m in info["Mounts"] if m["Destination"] == "/data")
    backup = ROOT / "backups"
    backup.mkdir(mode=0o700)
    records = {}
    for name in ["viridis_state.db", "security_preflight_receipts.sqlite3"]:
        src, dst = data / name, backup / name
        with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as a, sqlite3.connect(dst) as b:
            a.backup(b)
        records[name] = database_evidence(dst)
    save("backups/manifest.json", {"classification": "pre-promotion-consistent-sqlite-backups",
                                  "base_image": BASE, "databases": records})
    run("docker", "tag", BASE, ROLLBACK)
    (ROOT / "Dockerfile").write_text("FROM " + ROLLBACK + "\nCOPY overlay/ /fleet/\nENV MAXWELL_FLEET_ENABLED=1\n")
    (ROOT / ".dockerignore").write_text("*\n!Dockerfile\n!overlay\n!overlay/**\n")
    build = run("docker", "build", "--pull=false", "-f", str(ROOT / "Dockerfile"),
                "-t", CANDIDATE, str(ROOT), timeout=300)
    (ROOT / "build.log").write_text(build)
    image = run("docker", "image", "inspect", "--format", "{{.Id}}", CANDIDATE)
    paths = ["/fleet/" + item["path"] for item in manifest["files"]]
    hashes = run("docker", "run", "--rm", "--network", "none", "--read-only", "--entrypoint",
                 "sha256sum", CANDIDATE, *paths)
    actual = {line.split(None, 1)[1]: line.split()[0] for line in hashes.splitlines()}
    assert all(actual["/fleet/" + i["path"]] == i["sha256"] for i in manifest["files"])
    save("prepared.json", {"status": "PREPARED", "base_image": BASE, "candidate_image": image,
                           "files": manifest["files"], "backup_manifest_sha256": sha(backup / "manifest.json")})


def restage():
    """Rebuild a revised pre-promotion payload; force a fresh rehearsal."""
    expected_base()
    assert not (ROOT / 'promoted.json').exists()
    prepared = json.loads((ROOT / 'prepared.json').read_text())
    manifest = json.loads((ROOT / 'payload-manifest.json').read_text())
    assert prepared['backup_manifest_sha256'] == sha(ROOT / 'backups/manifest.json')
    for item in manifest['files']:
        rel = item['path']
        assert not Path(rel).is_absolute() and '..' not in Path(rel).parts
        assert sha(ROOT / 'overlay' / rel) == item['sha256']
    for rel, digest in manifest['base_sources'].items():
        assert run('docker', 'exec', LIVE, 'sha256sum', '/fleet/' + rel).split()[0] == digest
    (ROOT / 'rehearsed.json').unlink(missing_ok=True)
    run('docker', 'build', '--pull=false', '-f', str(ROOT / 'Dockerfile'), '-t', CANDIDATE, str(ROOT), timeout=300)
    image = run('docker', 'image', 'inspect', '--format', '{{.Id}}', CANDIDATE)
    for item in manifest['files']:
        actual = run('docker', 'run', '--rm', '--network', 'none', '--read-only', '--entrypoint',
                     'sha256sum', CANDIDATE, '/fleet/' + item['path']).split()[0]
        assert actual == item['sha256']
    prepared.update(candidate_image=image, files=manifest['files'])
    save('prepared.json', prepared)


def wait_healthy(container, image):
    for _ in range(60):
        info = inspect(container)
        if info["Image"] == image and info["State"].get("Health", {}).get("Status") == "healthy":
            return
        time.sleep(2)
    raise RuntimeError("container did not reach expected healthy image")


def request(base, path, payload=None, extra_headers=None):
    req = urllib.request.Request(base + path, headers={"accept": "application/json, text/event-stream",
        "content-type": "application/json", "user-agent": "viridis-release-verification/1.0",
        "x-viridis-acquisition-source": "internal", **(extra_headers or {})},
        data=json.dumps(payload).encode() if payload is not None else None)
    try:
        response = urllib.request.urlopen(req, timeout=25)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw.decode()
        return response.code, dict(response.headers), body


def verify_surface(base, label):
    status, _, health = request(base, "/healthz")
    assert status == 200 and health["status"] == "ok" and not health["mount_errors"], health.get("mount_errors")
    assert len(health["agents"]) == 29 and all(a["status"] == "ok" for a in health["agents"].values())
    assert health["agents"]["maxwell-defense"]["version"] == "0.1.0"
    route = "/x402/maxwell-defense/rehearse_defense"
    inputs = {"client_hashes_per_second":100000,"client_p95_budget_ms":250,"backend_cost_ms":2000,"peak_requests_per_second":100}
    status, headers, body = request(base, route, inputs)
    assert status == 402, (status,body)
    encoded = next(v for k,v in headers.items() if k.lower() == "payment-required")
    terms = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded)%4)))
    assert terms["x402Version"] == 2
    accepted = terms["accepts"][0]
    assert accepted["amount"] == "1000000" and accepted["network"] == "eip155:8453"
    assert accepted["payTo"].lower() == "0xfef2e570b645eb720ee6c589d27450810982f329"
    alias_status, alias_headers, _ = request(base, route, inputs, {"x-viridis-security-origin":"https://mcp.viridis-security.com"})
    assert alias_status == 402
    enc = next(v for k,v in alias_headers.items() if k.lower()=="payment-required")
    alias_terms = json.loads(base64.urlsafe_b64decode(enc+"="*(-len(enc)%4)))
    assert alias_terms["resource"]["url"] == "https://mcp.viridis-security.com"+route
    assert alias_terms["accepts"][0]["amount"] == "1000000"
    status, _, invalid = request(base, route, {**inputs,"client_hashes_per_second":0})
    assert status == 400
    status, _, catalog = request(base, "/x402/catalog")
    assert status == 200 and len(catalog["routes"]) == 11
    assert any(r["agent"] == "maxwell-defense" for r in catalog["routes"])
    for path in ["/openapi.json", "/.well-known/agent-card.json", "/llms.txt", "/agents"]:
        status, _, body = request(base,path)
        assert status == 200 and "maxwell-defense" in (body if isinstance(body,str) else json.dumps(body)), path
    status, _, listing = request(base,"/maxwell-defense/mcp",{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
    assert status == 200 and {"rehearse_defense","describe_agent"} == {t["name"] for t in listing["result"]["tools"]}
    status, _, selection = request(base,"/adopt",{"objective":"Maxwell defense rehearsal","inputs":inputs,"max_price_minor":100})
    assert status == 200 and selection["tool_executed"] is False and selection["money_moved"] is False
    assert selection["route_decision"]["selected"]["route"] == "maxwell-defense/rehearse_defense", selection
    save("verification-"+label+".json",{"status":"ok","agent_count":29,"route_count":11,"quote_terms":terms,
        "mcp_tools":listing,"adoption":selection,"payment_attempted":False,"runtime_protection_enabled":False})


def verify_baseline(base, receipt_id):
    payload = {"inputs": INPUTS, "baseline_receipt_id": receipt_id}
    status, _, result = request(base, WATCH_PATH, payload)
    assert status == 200 and result["decision"] == "UNCHANGED"
    assert result["quote_request"] is None
    changed = json.loads(json.dumps(payload))
    changed["inputs"]["sample_inputs"] = ["a changed fixture of the same count"]
    status, _, result = request(base, WATCH_PATH, changed)
    assert status == 200 and result["decision"] == "RECHECK_REQUIRED"
    status, _, public = request(base, "/security-preflight/receipts/" + receipt_id)
    assert status == 200 and public["receipt"]["receipt_id"] == receipt_id
    assert "feedback_token" not in json.dumps(public)


def rehearse():
    expected_base()
    prepared = json.loads((ROOT / "prepared.json").read_text())
    scratch = ROOT / "rehearsal-state"
    if scratch.exists():
        shutil.rmtree(scratch)  # Only this release's disposable rehearsal copy.
    scratch.mkdir(mode=0o700)
    records = json.loads((ROOT / "backups/manifest.json").read_text())["databases"]
    for name, record in records.items():
        shutil.copy2(ROOT / "backups" / name, scratch / name)
        assert database_evidence(scratch / name) == record
    env = dict(e.split("=", 1) for e in inspect()["Config"]["Env"])
    env.update({"PUBLIC_BASE": LOCAL, "HIVE_MARKET_LIFECYCLE_ENABLED": "0", "MAXWELL_FLEET_ENABLED": "1"})
    assert all("\n" not in v for v in env.values())
    env_path = ROOT / "rehearsal.env"
    env_path.write_text("\n".join(k + "=" + v for k, v in env.items()) + "\n")
    env_path.chmod(0o600)
    args = ["docker", "run", "-d", "--name", REHEARSAL, "--network", "viridis-fleet_default",
            "--env-file", str(env_path), "-p", "127.0.0.1:18407:8402", "-v", str(scratch) + ":/data"]
    for mount in inspect()["Mounts"]:
        if mount["Type"] == "bind":
            assert mount["RW"] is False
            args += ["-v", mount["Source"] + ":" + mount["Destination"] + ":ro"]
    try:
        run(*args, CANDIDATE)
        wait_healthy(REHEARSAL, prepared["candidate_image"])
        verify_surface(LOCAL, "rehearsal-first-boot")
        # Direct local fixture only in the isolated candidate; no payment API.
        code = """import sys,asyncio,json
sys.path.insert(0,'/fleet/maxwell-defense-agent')
from src.core import MaxwellDefenseCore
r=asyncio.run(MaxwellDefenseCore().process({'action':'rehearse_defense','client_hashes_per_second':100000,'client_p95_budget_ms':250,'backend_cost_ms':2000,'peak_requests_per_second':100}))
assert r['status']=='ok' and r['protection_activated'] is False
assert r['modeled_client']['p95_ms']<=250
print(json.dumps({'classification':'isolated_unpaid_fixture','result':r}))
"""
        fixture = json.loads(run("docker","exec",REHEARSAL,"python3","-c",code))
        save("rehearsal-result.json",fixture)
        run("docker", "restart", REHEARSAL)
        wait_healthy(REHEARSAL, prepared["candidate_image"])
        verify_surface(LOCAL, "rehearsal-restart")
        for name in records:
            database_evidence(scratch / name)
        save("rehearsed.json", {"status": "REHEARSAL_PASSED", "candidate_image": prepared["candidate_image"],
             "healthy_after_restart": True, "unpaid_fixture_only": True,
             "lifecycle_worker_disabled": True, "payment_attempted": False})
    finally:
        subprocess.run(["docker", "rm", "-f", REHEARSAL], capture_output=True)
        env_path.unlink(missing_ok=True)


def compose():
    return run("docker", "compose", "--project-directory", str(SOURCE / "deploy/droplet"),
               "--file", str(SOURCE / "deploy/droplet/docker-compose.yml"), "--project-name", "viridis-fleet",
               "--env-file", str(SOURCE / ".env"), "up", "-d", "--no-deps", "--force-recreate", "gateway")


def promote():
    expected_base()
    prepared = json.loads((ROOT / "prepared.json").read_text())
    # A server-only rehearsal can proceed while export permission is pending;
    # production promotion still requires independently restored off-host data.
    assert (ROOT / "offhost-backup-verified.json").is_file(), "off-host restore verification required"
    offhost = json.loads((ROOT / "offhost-backup-verified.json").read_text())
    assert offhost["backup_manifest_sha256"] == prepared["backup_manifest_sha256"]
    rehearsal = json.loads((ROOT / "rehearsed.json").read_text())
    image = prepared["candidate_image"]
    assert rehearsal["status"] == "REHEARSAL_PASSED" and rehearsal["candidate_image"] == image
    try:
        run("docker", "tag", image, "viridis-stable:latest")
        compose()
        wait_healthy(LIVE, image)
        verify_surface(PUBLIC, "production-first-boot")
        run("docker", "restart", LIVE)
        wait_healthy(LIVE, image)
        verify_surface(PUBLIC, "production-restart")
        data = next(Path(m["Source"]) for m in inspect()["Mounts"] if m["Destination"] == "/data")
        integrity = {name: database_evidence(data / name) for name in
                     ["viridis_state.db", "security_preflight_receipts.sqlite3"]}
        for item in prepared["files"]:
            target = SOURCE / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "overlay" / item["path"], target)
        save("promoted.json", {"status": "PROMOTED_RESTART_VERIFIED", "base_image": BASE,
             "candidate_image": image, "rollback_tag": ROLLBACK, "database_integrity": integrity,
             "payment_attempted": False, "new_customer_claimed": False})
    except BaseException:
        run("docker", "tag", BASE, "viridis-stable:latest")
        compose()
        wait_healthy(LIVE, BASE)
        save("rollback.json", {"status": "ROLLED_BACK", "image": BASE})
        raise


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "restage", "rehearse", "promote"])
    args = parser.parse_args()
    globals()[args.phase]()
    print(json.dumps({"phase": args.phase, "status": "ok", "release_dir": str(ROOT)}))
