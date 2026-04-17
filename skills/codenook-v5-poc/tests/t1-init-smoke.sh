#!/usr/bin/env bash
# T1: init smoke test — verify init.sh produces expected tree
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

if [[ ! -x "$INIT_SH" ]]; then
  echo "FAIL: init.sh not executable at $INIT_SH"
  exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cd "$TMP"
bash "$INIT_SH" > /tmp/t1-output.log 2>&1

FAIL=0
check() {
  if [[ ! -e "$1" ]]; then
    echo "  ❌ MISSING: $1"
    FAIL=$((FAIL + 1))
  else
    echo "  ✅ $1"
  fi
}

echo "=== T1: Init Smoke Test ==="
echo ""
echo "Required files:"
check "CLAUDE.md"
check ".codenook/state.json"
check ".codenook/config.yaml"
check ".codenook/core/codenook-core.md"
check ".codenook/prompts-templates/clarifier.md"
check ".codenook/prompts-templates/implementer.md"
check ".codenook/prompts-templates/reviewer.md"
check ".codenook/prompts-templates/synthesizer.md"
check ".codenook/prompts-templates/validator.md"
check ".codenook/prompts-criteria/criteria-clarify.md"
check ".codenook/prompts-criteria/criteria-implement.md"
check ".codenook/prompts-criteria/criteria-review.md"
check ".codenook/agents/clarifier.agent.md"
check ".codenook/agents/implementer.agent.md"
check ".codenook/agents/reviewer.agent.md"
check ".codenook/agents/synthesizer.agent.md"
check ".codenook/agents/validator.agent.md"
check ".codenook/project/ENVIRONMENT.md"
check ".codenook/project/CONVENTIONS.md"
check ".codenook/project/ARCHITECTURE.md"
check ".codenook/history/latest.md"

echo ""
echo "Required directories (may be empty):"
check ".codenook/tasks"
check ".codenook/knowledge/by-role"
check ".codenook/knowledge/by-topic"
check ".codenook/hitl-queue/pending"

echo ""
echo "Anti-checks (should NOT exist):"
anti_check() {
  if [[ -e "$1" ]]; then
    echo "  ❌ UNEXPECTED: $1 (should not be created)"
    FAIL=$((FAIL + 1))
  else
    echo "  ✅ absent: $1"
  fi
}
anti_check ".github/copilot-instructions.md"
anti_check ".claude/codenook"
anti_check ".copilot/codenook"

echo ""
if [[ -s ".codenook/state.json" ]]; then
  if command -v jq >/dev/null 2>&1; then
    if jq -e '.version == "5.0-poc"' .codenook/state.json >/dev/null; then
      echo "  ✅ state.json has version 5.0-poc"
    else
      echo "  ❌ state.json missing version 5.0-poc"
      FAIL=$((FAIL + 1))
    fi
  fi
fi

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T1 PASSED ==="
  exit 0
else
  echo "=== T1 FAILED ($FAIL issues) ==="
  exit 1
fi
