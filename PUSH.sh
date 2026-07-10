#!/usr/bin/env bash
# Push this MCP-surface staging folder to https://github.com/jdhart81/viridis-agent-fleet
# Run from inside this folder:  bash PUSH.sh
# Requires: git, and either `gh auth login` done OR a GitHub credential helper set.
set -euo pipefail

REMOTE="https://github.com/jdhart81/viridis-agent-fleet.git"

cd "$(dirname "${BASH_SOURCE[0]}")"
[ -d .git ] || git init -q
git add -A
git commit -q -m "MCP surface: 13-agent Viridis A2A economy — manifests, tool schemas, gateway, contracts" || echo "(nothing to commit)"
git branch -M main
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE"
echo "Pushing to $REMOTE …"
git push -u origin main
echo "✓ pushed. Confirm at https://github.com/jdhart81/viridis-agent-fleet"
