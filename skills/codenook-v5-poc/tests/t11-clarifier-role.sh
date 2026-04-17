#!/usr/bin/env bash
# T11: clarifier independent role static checks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
bash "$INIT_SH" > /tmp/t11-init.log 2>&1

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== T11: Clarifier Independent Role ==="
echo ""

# ---- [1] clarifier files exist ----
echo "[1] clarifier files present:"
CT=".codenook/prompts-templates/clarifier.md"
CC=".codenook/prompts-criteria/criteria-clarify.md"
CA=".codenook/agents/clarifier.agent.md"
[[ -f $CT ]] && pass "clarifier template"      || fail "clarifier template missing"
[[ -f $CC ]] && pass "clarifier criteria"      || fail "clarifier criteria missing"
[[ -f $CA ]] && pass "clarifier agent profile" || fail "clarifier agent profile missing"

# ---- [2] clarifier template required sections ----
echo ""
echo "[2] clarifier template content:"
if [[ -f $CT ]]; then
  for section in Goal Scope "Acceptance Criteria" Assumptions "Open Questions" "Risk Flags"; do
    grep -q "$section" "$CT" && pass "section: $section" || fail "section missing: $section"
  done
  grep -q 'clarity_verdict' "$CT"       && pass "clarity_verdict defined"         || fail "clarity_verdict missing"
  grep -q 'ready_to_implement' "$CT"    && pass "ready_to_implement verdict"      || fail "ready_to_implement missing"
  grep -q 'needs_user_input' "$CT"      && pass "needs_user_input verdict"        || fail "needs_user_input missing"
  grep -q 'fundamental_ambiguity' "$CT" && pass "fundamental_ambiguity verdict"   || fail "fundamental_ambiguity missing"
  grep -q 'NOT write code' "$CT" || grep -qi 'do NOT write code' "$CT" && pass "anti-scope: no code"  || fail "no anti-scope declaration"
fi

# ---- [3] clarifier agent profile ----
echo ""
echo "[3] clarifier agent profile:"
if [[ -f $CA ]]; then
  grep -q 'Self-Bootstrap Protocol' "$CA" && pass "self-bootstrap section"     || fail "no self-bootstrap"
  grep -q 'ENVIRONMENT.md' "$CA"          && pass "reads ENVIRONMENT.md"       || fail "doesn't read ENVIRONMENT.md"
  grep -q 'CONVENTIONS.md' "$CA"          && pass "reads CONVENTIONS.md"       || fail "doesn't read CONVENTIONS.md"
  grep -q 'ARCHITECTURE.md' "$CA"         && pass "reads ARCHITECTURE.md"      || fail "doesn't read ARCHITECTURE.md"
  grep -q 'too_large' "$CA"               && pass "too_large contract"         || fail "no too_large contract"
  grep -q 'NEVER.*code\|NEVER write code\|NEVER read source files' "$CA" && pass "absolute prohibitions declared" || fail "no absolute prohibitions"
fi

# ---- [4] config.yaml routing uses clarifier ----
echo ""
echo "[4] config.yaml routing phase 1:"
CFG=".codenook/config.yaml"
# clarify phase should now route to clarifier agent, not implementer
if grep -A2 '^    - name: clarify' "$CFG" | grep -q 'agent: clarifier'; then
  pass "clarify phase routes to clarifier agent"
else
  fail "clarify phase not routed to clarifier"
fi
if grep -A3 '^    - name: clarify' "$CFG" | grep -q 'template: prompts-templates/clarifier.md'; then
  pass "clarify phase uses clarifier.md template"
else
  fail "clarify phase not using clarifier template"
fi
if grep -A4 '^    - name: clarify' "$CFG" | grep -q 'criteria: prompts-criteria/criteria-clarify.md'; then
  pass "clarify phase has criteria-clarify.md"
else
  fail "clarify phase missing criteria-clarify"
fi
grep -qE '^  clarifier:' "$CFG" && pass "clarifier model entry" || fail "no clarifier model entry"

# ---- [5] core.md updated routing table and main loop ----
echo ""
echo "[5] core.md reflects independent clarifier:"
CORE=".codenook/core/codenook-core.md"
grep -q 'dispatch_clarifier' "$CORE"        && pass "main loop dispatches clarifier"        || fail "main loop still dispatches implementer for clarify"
grep -q 'mode=clarify' "$CORE"              && fail "main loop still has mode=clarify (stale)" || pass "no stale mode=clarify reference"
grep -q '| clarify .* clarifier' "$CORE" && pass "routing table has clarifier row" || fail "routing table not updated for clarifier"

# ---- [6] synthetic clarifier manifest lints clean ----
echo ""
echo "[6] synthetic phase-1 clarifier manifest:"
mkdir -p ".codenook/tasks/T-001/prompts"
mkdir -p ".codenook/tasks/T-001/outputs"
cat > ".codenook/tasks/T-001/task.md" <<EOF
Task description: build a minimal CLI tool that prints "hello" and exits.
EOF

cat > ".codenook/tasks/T-001/prompts/phase-1-clarifier.md" <<EOF
Template: @../../../prompts-templates/clarifier.md
Variables:
  task_id: T-001
  phase: clarify
  task_description: @../task.md
  project_env: @../../../project/ENVIRONMENT.md
  project_conv: @../../../project/CONVENTIONS.md
  project_arch: @../../../project/ARCHITECTURE.md
Output_to: @../outputs/phase-1-clarify.md
Summary_to: @../outputs/phase-1-clarify-summary.md
EOF

validate_manifest() {
  local mf="$1"
  local errs=0
  for k in Template Variables Output_to Summary_to; do
    grep -qE "^${k}:" "$mf" || { echo "❌ missing field: $k"; errs=$((errs+1)); }
  done
  local mdir
  mdir=$(dirname "$mf")
  while IFS= read -r ref; do
    ref_path="${ref#@}"
    abs="$mdir/$ref_path"
    [[ -e $abs ]] || { echo "❌ broken @ ref: $ref → $abs"; errs=$((errs+1)); }
  done < <(grep -vE '^(Output_to|Summary_to):' "$mf" | grep -oE '@[A-Za-z0-9_./-]+' | sort -u)
  local size
  size=$(wc -c < "$mf" | tr -d ' ')
  [[ $size -le 2000 ]] || { echo "❌ manifest too large: $size bytes"; errs=$((errs+1)); }
  return $errs
}

MANIFEST=".codenook/tasks/T-001/prompts/phase-1-clarifier.md"
output=$(validate_manifest "$MANIFEST" 2>&1 && echo "__OK__" || echo "__FAIL__")
if echo "$output" | grep -q '__OK__'; then
  pass "phase-1 clarifier manifest passes lint"
else
  fail "phase-1 clarifier manifest FAILED lint"
  echo "$output"
fi

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T11 PASSED ==="
  exit 0
else
  echo "=== T11 FAILED ($FAIL issues) ==="
  exit 1
fi
