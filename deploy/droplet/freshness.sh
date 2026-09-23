#!/usr/bin/env bash
# Weekly liveness heartbeat -> public repo. Keeps the GitHub repo's "last updated"
# recent (a real ranking signal on mcp.so / Glama / PulseMCP, which favour servers
# updated within the last month) AND records a genuine uptime check, so it's a
# meaningful commit, not noise. Runs on the droplet via cron; pushes with the
# repo_deploy SSH deploy key.
set -euo pipefail
REPO=/root/repo-fresh
BASE=https://mcp.viridisconservation.com
cd "$REPO"

git pull -q --rebase 2>/dev/null || true

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# real liveness check against the live gateway
HEALTH=$(curl -s --max-time 20 "$BASE/healthz" || echo '{}')
OK=$(printf '%s' "$HEALTH" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); a=d.get("agents",{})
    print(str(sum(1 for x in a.values() if x.get("status")=="ok"))+"/"+str(len(a)))
except Exception:
    print("0/0")')

mkdir -p .ops
cat > .ops/HEARTBEAT.md <<EOF
# Viridis Agent Fleet — liveness heartbeat

- Last verified (UTC): $NOW
- Endpoint: $BASE/healthz
- Agents healthy: $OK
- Discovery: $BASE/.well-known/ai-catalog.json
- Registry: https://registry.modelcontextprotocol.io (search \`io.github.jdhart81\`)

_Auto-generated weekly by the droplet freshness loop._
EOF

git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "chore(ops): weekly liveness heartbeat $NOW — agents $OK"
  git push -q origin main
  echo "pushed heartbeat $NOW ($OK)"
else
  echo "no change $NOW"
fi
