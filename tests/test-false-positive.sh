#!/usr/bin/env bash
# Test: verify quoted strings in bash commands don't trigger false positive denials
set -euo pipefail

HOOK="./hooks/agent-pre-tool-use.sh"
PASS=0; FAIL=0; TOTAL=0
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

check() {
  local desc="$1" input="$2" expect="$3"
  TOTAL=$((TOTAL + 1))
  result=$(echo "$input" | bash "$HOOK" 2>/dev/null) || true
  if [ "$expect" = "allow" ]; then
    if [ -z "$result" ]; then PASS=$((PASS+1)); echo "  ✅ $desc → ALLOWED"
    else FAIL=$((FAIL+1)); echo "  ❌ $desc → DENIED (expected ALLOW): $result"; fi
  else
    if echo "$result" | grep -q '"deny"'; then PASS=$((PASS+1)); echo "  ✅ $desc → DENIED"
    else FAIL=$((FAIL+1)); echo "  ❌ $desc → ALLOWED (expected DENY)"; fi
  fi
}

cd "$PROJECT_ROOT"

echo "📋 False Positive Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━"

# --- Implementer tests ---
echo "implementer" > .agents/runtime/active-agent

echo "--- Implementer: quoted content should NOT trigger ---"
check "gh release with npm publish in --notes" \
  '{"toolName":"bash","toolArgs":{"command":"gh release create v1.0 --notes \"blocked npm publish and docker push\""},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

check "echo with npm publish in quoted string" \
  '{"toolName":"bash","toolArgs":{"command":"echo \"npm publish is blocked\" | cat"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

check "grep for npm publish pattern" \
  '{"toolName":"bash","toolArgs":{"command":"grep '"'"'npm publish'"'"' hooks/agent-pre-tool-use.sh"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

echo "--- Implementer: real dangerous commands still blocked ---"
check "direct npm publish" \
  '{"toolName":"bash","toolArgs":{"command":"npm publish"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "deny"

check "npm publish with flags" \
  '{"toolName":"bash","toolArgs":{"command":"npm publish --access public"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "deny"

check "docker push" \
  '{"toolName":"bash","toolArgs":{"command":"docker push myimage:latest"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "deny"

# --- Tester tests ---
echo ""
echo "tester" > .agents/runtime/active-agent

echo "--- Tester: quoted content should NOT trigger ---"
check "git log with commit in quoted grep" \
  '{"toolName":"bash","toolArgs":{"command":"git log --grep='"'"'git commit'"'"' --oneline"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

check "echo with redirect symbol in quotes" \
  '{"toolName":"bash","toolArgs":{"command":"echo '"'"'>> redirect text'"'"' | cat"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

echo "--- Tester: real dangerous commands still blocked ---"
check "git commit" \
  '{"toolName":"bash","toolArgs":{"command":"git commit -m fix"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "deny"

check "git push" \
  '{"toolName":"bash","toolArgs":{"command":"git push origin main"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "deny"

check "echo redirect to source file" \
  '{"toolName":"bash","toolArgs":{"command":"echo data >> install.sh"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "deny"

# --- Acceptor tests ---
echo ""
echo "acceptor" > .agents/runtime/active-agent

echo "--- Acceptor: quoted content should NOT trigger ---"
check "grep for rm pattern in file" \
  '{"toolName":"bash","toolArgs":{"command":"grep '"'"'rm -rf'"'"' README.md"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

check "echo with git push in double-quoted message" \
  '{"toolName":"bash","toolArgs":{"command":"echo \"run git push after review\" | cat"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

echo "--- Acceptor: real dangerous still blocked ---"
check "actual rm" \
  '{"toolName":"bash","toolArgs":{"command":"rm install.sh"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "deny"

check "actual git push" \
  '{"toolName":"bash","toolArgs":{"command":"git push origin main"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "deny"

echo "--- Acceptor: /dev/null redirects should NOT trigger ---"
check "cat with 2>/dev/null" \
  '{"toolName":"bash","toolArgs":{"command":"cat .agents/runtime/acceptor/inbox.json 2>/dev/null || echo no"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

check "ls with >/dev/null" \
  '{"toolName":"bash","toolArgs":{"command":"ls .agents/ >/dev/null"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

check "python with 2>/dev/null at end" \
  '{"toolName":"bash","toolArgs":{"command":"python3 -c \"print(1)\" 2>/dev/null || echo fail"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

check "command with &>/dev/null" \
  '{"toolName":"bash","toolArgs":{"command":"git status &>/dev/null && echo ok"},"cwd":"'"$PROJECT_ROOT"'"}' \
  "allow"

# --- Cleanup ---
echo ""
echo "implementer" > .agents/runtime/active-agent
echo "━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: $PASS/$TOTAL passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "✅ All false-positive tests passed!" || echo "❌ Some tests failed"
exit "$FAIL"
