#!/usr/bin/env bash
# Security Scan Hook: Scans staged files for secrets before git commit/push.
# Independent of Multi-Agent system — works in ANY project.
# Can output {"permissionDecision":"deny","permissionDecisionReason":"..."} to block.

set -euo pipefail
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.toolName')
TOOL_ARGS=$(echo "$INPUT" | jq -r '.toolArgs')
CWD=$(echo "$INPUT" | jq -r '.cwd')

# Only intercept bash commands containing git commit/push
case "$TOOL_NAME" in
  bash)
    CMD=$(echo "$TOOL_ARGS" | jq -r '.command // empty' 2>/dev/null)
    if echo "$CMD" | grep -qE '(git\s+(commit|push)|git\s+.*\s+(commit|push))'; then
      STAGED_FILES=$(cd "$CWD" && git diff --cached --name-only 2>/dev/null)
      if [ -n "$STAGED_FILES" ]; then
        SECRETS_FOUND=""
        while IFS= read -r f; do
          [ -f "$CWD/$f" ] || continue

          # API keys (Google, OpenAI, GitHub, AWS, Stripe, Slack)
          if grep -qE '(AIza[0-9A-Za-z_-]{35}|sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|ghr_[a-zA-Z0-9]{36}|AKIA[0-9A-Z]{16}|sk_live_[a-zA-Z0-9]{20,}|xox[bpoas]-[a-zA-Z0-9-]+)' "$CWD/$f" 2>/dev/null; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: possible API key"
          fi

          # Passwords/secrets in key=value assignments
          if grep -qiE '(password|passwd|secret|token|api_key)\s*[:=]\s*["\x27][^\s"'\'']{8,}' "$CWD/$f" 2>/dev/null; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: possible password/secret"
          fi

          # Private keys (SSH, TLS)
          if grep -q 'BEGIN.*PRIVATE KEY' "$CWD/$f" 2>/dev/null; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: private key detected"
          fi

          # Database connection strings
          if grep -qE '(postgres|mysql|mongodb(\+srv)?|redis)://[^@]+@' "$CWD/$f" 2>/dev/null; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: database connection string with credentials"
          fi

          # JWT / Bearer tokens
          if grep -qE '(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}|Bearer\s+[a-zA-Z0-9._-]{20,})' "$CWD/$f" 2>/dev/null; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: possible JWT/Bearer token"
          fi

          # Webhook URLs (Slack, Discord)
          if grep -qE 'hooks\.(slack\.com|discord\.com)/services/' "$CWD/$f" 2>/dev/null; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: webhook URL detected"
          fi

          # .env files
          if echo "$f" | grep -qE '\.env(\..+)?$'; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: .env file should not be committed"
          fi
        done <<< "$STAGED_FILES"

        if [ -n "$SECRETS_FOUND" ]; then
          REASON="🔒 Pre-commit security scan found sensitive data:${SECRETS_FOUND}\nRemove secrets before committing. Use git reset HEAD <file> to unstage."
          echo "{\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$(echo -e "$REASON" | head -c 500)\"}"
          exit 0
        fi
      fi
    fi
    ;;
esac

# Allow by default
