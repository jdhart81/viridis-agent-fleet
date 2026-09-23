#!/bin/sh
# Publish the exact Security Preflight buyer client to the public main branch.

set -eu

EXPECTED_AUTH='authorize GitHub publication: security preflight buyer path 20260806'
EXPECTED_ACCOUNT='jdhart81'
EXPECTED_REPOSITORY='jdhart81/viridis-agent-fleet'
EXPECTED_BASE='38de8e1d285f9f7a73acb3ed8e4c70d63c709baf'
EXPECTED_PATCH_SHA='df4d873597f4ff72606510787a755698ddb707cb0bfd26368b4245150737dfbd'
EXPECTED_CLIENT_SHA='eb71c466ad17c81d36e3f03c5ba308a4a0f8922337cef5116cc604deab87252d'
EXPECTED_QUICKSTART_SHA='5ba681eb5a1f325da514aa14bf1240e4edf57e6a7ca972a932596ea523dd82b4'
EXPECTED_TEST_SHA='97f7d57e539d83e94e340feb56929ed98b6d2c6625b7cf83e559e0bf17ff534e'

if [ "$#" -ne 1 ] || [ "$1" != "$EXPECTED_AUTH" ]; then
  echo 'refusing: exact GitHub-publication authorization required' >&2
  exit 64
fi

ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
PATCH="$ROOT/docs/deployment/patches/security-preflight-buyer-path-ee2b479.patch"
[ -f "$PATCH" ]
[ "$(shasum -a 256 "$PATCH" | awk '{print $1}')" = "$EXPECTED_PATCH_SHA" ]

# Repository doctrine requires this to be the first GitHub access check.
gh auth status
[ "$(gh api user --jq .login)" = "$EXPECTED_ACCOUNT" ]

RUN_DIR=$(mktemp -d /private/tmp/viridis-security-preflight-publish.XXXXXX)
cleanup() {
  rm -rf "$RUN_DIR"
}
trap cleanup EXIT INT TERM

gh repo clone "$EXPECTED_REPOSITORY" "$RUN_DIR/repo" -- --no-tags
[ -z "$(git -C "$RUN_DIR/repo" status --porcelain)" ]
[ "$(git -C "$RUN_DIR/repo" rev-parse HEAD)" = "$EXPECTED_BASE" ]
[ "$(git -C "$RUN_DIR/repo" rev-parse origin/main)" = "$EXPECTED_BASE" ]

git -C "$RUN_DIR/repo" am "$PATCH"
[ "$(git -C "$RUN_DIR/repo" rev-parse HEAD^)" = "$EXPECTED_BASE" ]
[ "$(shasum -a 256 "$RUN_DIR/repo/scripts/x402_demo_client.py" | awk '{print $1}')" = "$EXPECTED_CLIENT_SHA" ]
[ "$(shasum -a 256 "$RUN_DIR/repo/docs/QUICKSTART_FIRST_CALL.md" | awk '{print $1}')" = "$EXPECTED_QUICKSTART_SHA" ]
[ "$(shasum -a 256 "$RUN_DIR/repo/gateway/test_wave9_activation.py" | awk '{print $1}')" = "$EXPECTED_TEST_SHA" ]

(cd "$RUN_DIR/repo" && \
  python3 -m pytest -q gateway/test_wave9_activation.py -k demo_client)
git -C "$RUN_DIR/repo" push origin HEAD:main

PUBLISHED=$(git -C "$RUN_DIR/repo" ls-remote origin refs/heads/main | awk '{print $1}')
[ "$PUBLISHED" = "$(git -C "$RUN_DIR/repo" rev-parse HEAD)" ]

RAW="$RUN_DIR/published-x402-demo-client.py"
curl --retry 8 --retry-delay 2 --retry-all-errors -fsS \
  "https://raw.githubusercontent.com/$EXPECTED_REPOSITORY/main/scripts/x402_demo_client.py" \
  > "$RAW"
[ "$(shasum -a 256 "$RAW" | awk '{print $1}')" = "$EXPECTED_CLIENT_SHA" ]
echo "GitHub publication verified: $PUBLISHED"
