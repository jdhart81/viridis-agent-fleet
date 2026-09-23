#!/usr/bin/env bash
# Register the production Viridis receiving wallet as a PayanAgent seller.
set -Eeuo pipefail

EXPECTED_AUTH='register-payanagent-seller-viridis-agent-fleet'
ENV_FILE='/root/viridis-fleet/.env.payanagent'
API_URL='https://payanagent.com/api/v1/agents'
WALLET_ADDRESS='0xfEf2e570b645EB720Ee6c589d27450810982f329'

if [[ $# -ne 1 || $1 != "$EXPECTED_AUTH" ]]; then
  echo 'refusing: exact PayanAgent seller-registration authorization is required' >&2
  exit 64
fi

umask 077

if [[ -s $ENV_FILE ]] && grep -q '^PAYANAGENT_AGENT_ID=' "$ENV_FILE" \
  && grep -q '^PAYANAGENT_API_KEY=pk_' "$ENV_FILE"; then
  existing_agent_id="$(sed -n 's/^PAYANAGENT_AGENT_ID=//p' "$ENV_FILE")"
  printf 'already_registered agent_id=%s\n' "$existing_agent_id"
  exit 0
fi

response_file="$(mktemp /tmp/payanagent-registration.XXXXXX)"
payload_file="$(mktemp /tmp/payanagent-registration-payload.XXXXXX)"
trap 'rm -f "$response_file" "$payload_file"' EXIT

jq -n \
  --arg name 'Viridis Agent Fleet' \
  --arg description 'Autonomous climate-compliance, audit, and agent-security services with live x402 settlement on Base. Paid API responses include a machine-verifiable viridis-paid-delivery-v1 delivery receipt.' \
  --arg walletAddress "$WALLET_ADDRESS" \
  --arg agentUrl 'https://mcp.viridisconservation.com/.well-known/agent.json' \
  '{
    name: $name,
    description: $description,
    walletAddress: $walletAddress,
    chain: "base",
    providerType: "agent",
    tags: ["climate", "compliance", "security", "x402", "audit"],
    agentUrl: $agentUrl,
    discoverySource: "web_search",
    a2aCapabilities: {streaming: false, pushNotifications: false}
  }' > "$payload_file"

http_code="$(curl --silent --show-error --max-time 30 \
  --output "$response_file" --write-out '%{http_code}' \
  --request POST "$API_URL" \
  --header 'Content-Type: application/json' \
  --data-binary "@$payload_file")"

if [[ $http_code != 200 && $http_code != 201 ]]; then
  error="$(jq -r '.error // .message // "registration failed"' "$response_file" 2>/dev/null || true)"
  printf 'registration_failed http_code=%s error=%s\n' "$http_code" "$error" >&2
  exit 1
fi

agent_id="$(jq -er '.agentId | strings | select(length > 0)' "$response_file")"
api_key="$(jq -er '.apiKey | strings | select(startswith("pk_"))' "$response_file")"

temp_env="$(mktemp /root/viridis-fleet/.env.payanagent.XXXXXX)"
trap 'rm -f "$response_file" "$payload_file" "$temp_env"' EXIT
printf 'PAYANAGENT_AGENT_ID=%s\nPAYANAGENT_API_KEY=%s\nPAYANAGENT_WALLET_ADDRESS=%s\n' \
  "$agent_id" "$api_key" "$WALLET_ADDRESS" > "$temp_env"
chmod 600 "$temp_env"
mv "$temp_env" "$ENV_FILE"

printf 'registered agent_id=%s wallet=%s\n' "$agent_id" "$WALLET_ADDRESS"
