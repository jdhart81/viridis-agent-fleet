#!/usr/bin/env bash
# Viridis Agent Fleet — Test Runner
# Runs tests per-agent with isolation to avoid module name collisions.
# Usage: ./run_fleet_tests.sh [agent-dir ...]
# If no args, runs all agents with tests/ directories.

set -euo pipefail

# Ensure local pip bin is on PATH
export PATH="$HOME/.local/bin:/sessions/brave-happy-maxwell/.local/bin:$PATH"

FLEET_ROOT="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0
SKIP=0
ERRORS=()

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Collect agent dirs
if [ $# -gt 0 ]; then
    AGENTS=("$@")
else
    AGENTS=()
    for dir in "$FLEET_ROOT"/*/tests/; do
        agent_dir="$(dirname "$dir")"
        agent_name="$(basename "$agent_dir")"
        # Skip non-agent directories
        [[ "$agent_name" == _* ]] && continue
        [[ "$agent_name" == fleet_utils ]] && continue
        [[ "$agent_name" == __pycache__ ]] && continue
        AGENTS+=("$agent_name")
    done
fi

echo "============================================"
echo "  Viridis Fleet Test Runner"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Agents to test: ${#AGENTS[@]}"
echo "============================================"
echo ""

for agent in "${AGENTS[@]}"; do
    agent_path="$FLEET_ROOT/$agent"
    if [ ! -d "$agent_path/tests" ]; then
        echo -e "${YELLOW}SKIP${NC}  $agent (no tests/)"
        SKIP=$((SKIP + 1))
        continue
    fi

    # Run pytest per-agent from fleet root, capturing output
    output=$(cd "$FLEET_ROOT" && python -m pytest "$agent/tests/" -q --tb=line 2>&1) || true

    # Parse results
    if echo "$output" | grep -q "passed"; then
        passed=$(echo "$output" | grep -oP '\d+ passed' | grep -oP '\d+' || echo 0)
        failed=$(echo "$output" | grep -oP '\d+ failed' | grep -oP '\d+' || echo 0)
        total=$((passed + failed))

        if [ "${failed:-0}" -gt 0 ]; then
            echo -e "${RED}FAIL${NC}  $agent  ($passed/$total passed)"
            ERRORS+=("$agent: $failed failures")
            FAIL=$((FAIL + 1))
        else
            echo -e "${GREEN}PASS${NC}  $agent  ($passed/$total)"
            PASS=$((PASS + 1))
        fi
    elif echo "$output" | grep -q "error"; then
        echo -e "${RED}ERR ${NC}  $agent  (collection error)"
        ERRORS+=("$agent: collection error")
        FAIL=$((FAIL + 1))
    else
        echo -e "${YELLOW}SKIP${NC}  $agent (no tests collected)"
        SKIP=$((SKIP + 1))
    fi
done

echo ""
echo "============================================"
echo "  Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$SKIP skipped${NC}"
if [ ${#ERRORS[@]} -gt 0 ]; then
    echo ""
    echo "  Failures:"
    for err in "${ERRORS[@]}"; do
        echo "    - $err"
    done
fi
echo "============================================"

# Exit with failure if any agents failed
[ "$FAIL" -eq 0 ]
