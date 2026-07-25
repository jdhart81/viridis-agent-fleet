#!/usr/bin/env bash
set -euo pipefail

publisher="${1:?usage: publish_mcp_registry_idempotent.sh PUBLISHER MANIFEST}"
manifest="${2:?usage: publish_mcp_registry_idempotent.sh PUBLISHER MANIFEST}"

if [[ ! -x "$publisher" ]]; then
  echo "MCP publisher is not executable: $publisher" >&2
  exit 2
fi

if [[ ! -f "$manifest" ]]; then
  echo "MCP manifest does not exist: $manifest" >&2
  exit 2
fi

status=0
output="$("$publisher" publish "$manifest" 2>&1)" || status=$?
printf '%s\n' "$output"

if [[ "$status" -eq 0 ]]; then
  echo "registry_publish_outcome=published"
  exit 0
fi

if [[ "$output" == *"invalid version: cannot publish duplicate version"* ]]; then
  echo "::notice title=MCP Registry::The exact server version is already published; no registry change was needed."
  echo "registry_publish_outcome=already_published"
  exit 0
fi

exit "$status"
