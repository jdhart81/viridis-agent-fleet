#!/usr/bin/env bash
# Moves the Stripe key from env/ to the droplet's .env WITHOUT printing the key.
# Extracts only the sk_ token, streams it over SSH, echoes a status line only.
set -euo pipefail
KEYFILE="/Users/justinhart/Desktop/Cowork /Agents to deploy  copy/env/stripe live key .md"
DROPLET="root@192.34.62.16"
KEY_ID="/Users/justinhart/.ssh/id_ed25519"

# .md files may escape underscores (sk\_test\_...) — strip backslashes first.
# Match both standard secret keys (sk_) and restricted keys (rk_), test or live.
KEYVAL=$(tr -d '\\' < "$KEYFILE" | grep -oE '[sr]k_(live|test)_[A-Za-z0-9]+' | head -1 || true)
if [ -z "$KEYVAL" ]; then echo "NO_KEY_FOUND"; exit 1; fi

printf 'STRIPE_API_KEY=%s\n' "$KEYVAL" | \
  ssh -o StrictHostKeyChecking=accept-new -i "$KEY_ID" "$DROPLET" \
  'cat > /root/viridis-fleet/.env && chmod 600 /root/viridis-fleet/.env'

MODE=$(printf '%s' "$KEYVAL" | grep -oE '[sr]k_(live|test)')
echo "TRANSFERRED mode=${MODE} len=${#KEYVAL}"
