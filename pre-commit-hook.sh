#!/bin/bash
# Git pre-commit hook to prevent committing secrets
# Install: cp pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# List of secret patterns to check for
SECRET_PATTERNS=(
    'sk_live_'
    'sk_test_'
    'BEGIN RSA PRIVATE KEY'
    'BEGIN PRIVATE KEY'
    'password\s*='
    'api_key\s*='
    'api_secret\s*='
    'secret\s*='
    'token\s*='
    'STRIPE_SECRET'
    'AWS_SECRET'
    'GCP_KEY'
)

echo -e "${YELLOW}🔐 Checking for secrets in commit...${NC}"

# Check staged files
STAGED_FILES=$(git diff --cached --name-only)
FOUND_SECRETS=0

for file in $STAGED_FILES; do
    # Skip .env.example, documentation, and some safe files
    if [[ "$file" == *.env.example ]] || [[ "$file" == *.md ]] || [[ "$file" == *.txt ]] || [[ "$file" == *example* ]]; then
        continue
    fi

    # Check each pattern
    for pattern in "${SECRET_PATTERNS[@]}"; do
        if git show ":$file" | grep -qE "$pattern"; then
            echo -e "${RED}✗ BLOCKED: Secret pattern '$pattern' found in $file${NC}"
            FOUND_SECRETS=1
        fi
    done
done

if [ $FOUND_SECRETS -eq 1 ]; then
    echo ""
    echo -e "${RED}❌ Commit blocked due to detected secrets.${NC}"
    echo -e "${YELLOW}To fix:${NC}"
    echo "  1. Remove sensitive data from the file"
    echo "  2. Use environment variables instead (see SECRETS_QUICK_REFERENCE.md)"
    echo "  3. Add the file to .gitignore if appropriate"
    echo "  4. Stage the changes: git add <file>"
    echo "  5. Commit again"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ No secrets detected${NC}"
exit 0
