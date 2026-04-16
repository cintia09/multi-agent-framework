#!/usr/bin/env bash
set -euo pipefail

# CodeNook Skill Security Scanner
# Scans skill files for suspicious patterns before installation.
# Exit code 0 = clean, 1 = warnings found, 2 = blocked (critical risk)
#
# Usage:
#   ./skill-security-scan.sh <skill-directory>
#   ./skill-security-scan.sh skills/codenook-init

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

SCAN_DIR="${1:-.}"
WARNINGS=0
CRITICAL=0

warn()  { echo -e "  ${YELLOW}⚠ WARN${NC}  $1"; WARNINGS=$((WARNINGS + 1)); }
crit()  { echo -e "  ${RED}✗ CRIT${NC}  $1"; CRITICAL=$((CRITICAL + 1)); }
clean() { echo -e "  ${GREEN}✓${NC} $1"; }

echo -e "${CYAN}🔍 Scanning: ${SCAN_DIR}${NC}"
echo ""

# ── Rule 1: Network exfiltration commands ──
echo "Rule 1: Network exfiltration patterns"
EXFIL_PATTERNS='curl\s|wget\s|fetch\(|http\.get|requests\.(get|post)|urllib|nc\s+-|ncat\s|socat\s'
if files=$(grep -rlE "$EXFIL_PATTERNS" "$SCAN_DIR" --include="*.md" 2>/dev/null); then
  while IFS= read -r f; do
    matches=$(grep -nE "$EXFIL_PATTERNS" "$f" 2>/dev/null | head -3)
    # Skip if it's in a comment about what NOT to do, or in a code fence describing tools
    if echo "$matches" | grep -qiE '(do not|never|must not|禁止|不要|block|reject)'; then
      clean "$(basename "$f"): network commands in prohibition context (OK)"
    else
      crit "$(basename "$f"): network exfiltration commands found"
      echo "$matches" | sed 's/^/      /'
    fi
  done <<< "$files"
else
  clean "No network exfiltration commands"
fi
echo ""

# ── Rule 2: Credential/secret file access ──
echo "Rule 2: Credential file access patterns"
CRED_PATTERNS='read.*\.env\b|cat.*\.ssh/|\.aws/credentials|\.gnupg/|\.netrc|\.npmrc.*auth|/etc/passwd|/etc/shadow'
if files=$(grep -rlE "$CRED_PATTERNS" "$SCAN_DIR" --include="*.md" 2>/dev/null); then
  while IFS= read -r f; do
    matches=$(grep -nE "$CRED_PATTERNS" "$f" 2>/dev/null | head -3)
    if echo "$matches" | grep -qiE '(do not|never|must not|scan.*before|check.*for|禁止|remove)'; then
      clean "$(basename "$f"): credential refs in security-check context (OK)"
    else
      warn "$(basename "$f"): credential file access patterns"
      echo "$matches" | sed 's/^/      /'
    fi
  done <<< "$files"
else
  clean "No credential file access patterns"
fi
echo ""

# ── Rule 3: Base64/encoding (data hiding) ──
echo "Rule 3: Data encoding/obfuscation patterns"
ENCODE_PATTERNS='base64\s+(encode|decode|-d|-e)|btoa\(|atob\(|xxd\s|openssl\s+enc'
if files=$(grep -rlE "$ENCODE_PATTERNS" "$SCAN_DIR" --include="*.md" 2>/dev/null); then
  while IFS= read -r f; do
    warn "$(basename "$f"): data encoding commands"
    grep -nE "$ENCODE_PATTERNS" "$f" 2>/dev/null | head -3 | sed 's/^/      /'
  done <<< "$files"
else
  clean "No data encoding/obfuscation"
fi
echo ""

# ── Rule 4: External URLs (data exfiltration targets) ──
echo "Rule 4: External URL references"
# Exclude GitHub, common docs, localhost
URL_PATTERN='https?://[a-zA-Z0-9.-]+\.[a-z]{2,}'
SAFE_DOMAINS='github\.com|githubusercontent\.com|docs\.|localhost|127\.0\.0\.1|example\.com|npmjs\.com|pypi\.org|maven\.org|crates\.io|rubygems\.org|stackoverflow\.com|wikipedia\.org|mermaid\.ink|atlassian\.net'
if files=$(grep -rlE "$URL_PATTERN" "$SCAN_DIR" --include="*.md" 2>/dev/null); then
  while IFS= read -r f; do
    suspicious=$(grep -noE "$URL_PATTERN" "$f" 2>/dev/null | grep -vE "$SAFE_DOMAINS" | head -5)
    if [ -n "$suspicious" ]; then
      warn "$(basename "$f"): external URLs (verify intent)"
      echo "$suspicious" | sed 's/^/      /'
    fi
  done <<< "$files"
else
  clean "No external URLs"
fi
echo ""

# ── Rule 5: Shell injection / eval patterns ──
echo "Rule 5: Shell injection / eval patterns"
EVAL_PATTERNS='\beval\s+["\x27$]|exec\s+["\x27$]|\bos\.system\s*\(|child_process\.exec|spawn\(["\x27]sh|popen\(|xargs.*\bsh\b'
if files=$(grep -rlE "$EVAL_PATTERNS" "$SCAN_DIR" --include="*.md" 2>/dev/null); then
  while IFS= read -r f; do
    warn "$(basename "$f"): dynamic execution patterns"
    grep -nE "$EVAL_PATTERNS" "$f" 2>/dev/null | head -3 | sed 's/^/      /'
  done <<< "$files"
else
  clean "No shell injection / eval patterns"
fi
echo ""

# ── Rule 6: File system write to sensitive locations ──
echo "Rule 6: Sensitive path writes"
WRITE_PATTERNS='write.*(/etc/|/usr/|/root/|~\/\.|%APPDATA%|%USERPROFILE%)|>(>?)\s*/etc/|chmod\s+[0-7]*\s+/'
if files=$(grep -rlE "$WRITE_PATTERNS" "$SCAN_DIR" --include="*.md" 2>/dev/null); then
  while IFS= read -r f; do
    crit "$(basename "$f"): writes to sensitive system paths"
    grep -nE "$WRITE_PATTERNS" "$f" 2>/dev/null | head -3 | sed 's/^/      /'
  done <<< "$files"
else
  clean "No sensitive path writes"
fi
echo ""

# ── Rule 7: Prompt injection / instruction override ──
echo "Rule 7: Prompt injection patterns"
INJECT_PATTERNS='ignore.*previous|forget.*instructions|you are now|new instructions|system prompt|override.*rules|jailbreak'
if files=$(grep -rliE "$INJECT_PATTERNS" "$SCAN_DIR" --include="*.md" 2>/dev/null); then
  while IFS= read -r f; do
    crit "$(basename "$f"): prompt injection patterns detected"
    grep -niE "$INJECT_PATTERNS" "$f" 2>/dev/null | head -3 | sed 's/^/      /'
  done <<< "$files"
else
  clean "No prompt injection patterns"
fi
echo ""

# ── Rule 8: HITL adapter scripts (executable code) ──
echo "Rule 8: Executable script safety"
script_count=0
for script in "$SCAN_DIR"/**/*.sh "$SCAN_DIR"/**/*.py; do
  [ -f "$script" ] 2>/dev/null || continue
  script_count=$((script_count + 1))
  # Check for outbound network in scripts
  if grep -qE 'curl|wget|nc\s|ncat|socat|requests\.' "$script" 2>/dev/null; then
    # Confluence adapter legitimately uses curl for API calls
    if basename "$script" | grep -qE 'confluence|github-issue'; then
      clean "$(basename "$script"): network calls (expected for HITL adapter)"
    else
      warn "$(basename "$script"): network calls in executable script"
    fi
  fi
done
if [ "$script_count" -eq 0 ]; then
  clean "No executable scripts found"
else
  clean "Scanned $script_count executable scripts"
fi
echo ""

# ── Summary ──
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$CRITICAL" -gt 0 ]; then
  echo -e "${RED}✗ BLOCKED${NC}: $CRITICAL critical + $WARNINGS warnings"
  echo "  Critical findings MUST be resolved before installation."
  exit 2
elif [ "$WARNINGS" -gt 0 ]; then
  echo -e "${YELLOW}⚠ PASSED WITH WARNINGS${NC}: $WARNINGS warnings"
  echo "  Review warnings above. Proceed with caution."
  exit 1
else
  echo -e "${GREEN}✓ CLEAN${NC}: No security issues found"
  exit 0
fi
