#!/usr/bin/env python3
"""Public-repo guard (runs in CI): fail if hosted-service code or secrets land here.

G1 No file under a service path (deploy/, gateway/, runtime/, env/, secrets/, production-backups/).
G2 No hosted-service module filename (payment gate, x402 rails, gateway, state store, billing).
G3 No secret material (live Stripe keys, webhook secrets, private keys, cloud/GitHub/Slack tokens).
"""
import re
import subprocess
import sys
from pathlib import Path

SERVICE_DIRS = ("deploy/", "gateway/", "runtime/", "env/", "secrets/", "production-backups/", "backups/")
REGISTRY_MANIFEST_DIRS = ("deploy/mcp-publish/", "deploy/mcp-publish-github/")  # public registry listings
SERVICE_FILES = {"payment_gate.py", "stripe_payments.py", "state_store.py", "x402_http.py", "x402_v2.py",
                 "x402_rail.py", "viridis_mcp_gateway.py", "escrow_custody.py", "connect_rail.py",
                 "account_auth.py", "cliff_check.py", "growth_agent.py"}
SECRETS = [re.compile(p) for p in (
    r"(?:sk|rk)_live_[A-Za-z0-9]{20,}", r"whsec_[A-Za-z0-9]{20,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
    r"AKIA[0-9A-Z]{16}", r"gh[pousr]_[A-Za-z0-9]{36,}", r"xox[abpr]-[A-Za-z0-9-]{20,}")]


def tracked_files():
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def check(paths, read=lambda p: Path(p).read_text(errors="ignore")):
    bad = []
    for p in paths:
        registry_manifest = p.startswith(REGISTRY_MANIFEST_DIRS) and not p.endswith(".py")
        if (p.startswith(SERVICE_DIRS) and not registry_manifest) or "/secrets/" in f"/{p}":
            bad.append(("G1", p))
        if Path(p).name in SERVICE_FILES:
            bad.append(("G2", p))
        try:
            text = read(p)
        except OSError:
            continue
        if any(rx.search(text) for rx in SECRETS):
            bad.append(("G3", p))
    return bad


if __name__ == "__main__":
    violations = check(tracked_files())
    for rule, path in violations:
        print(f"{rule} {path}")
    sys.exit(1 if violations else 0)
