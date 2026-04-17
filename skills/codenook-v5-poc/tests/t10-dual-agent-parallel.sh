#!/usr/bin/env bash
# T10: dual-agent parallel + synthesizer static checks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
bash "$INIT_SH" > /tmp/t10-init.log 2>&1

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== T10: Dual-Agent Parallel + Synthesizer Static Checks ==="
echo ""

# ---- [1] config.yaml parallel block ----
echo "[1] config.yaml parallel block:"
CFG=".codenook/config.yaml"
grep -qE 'default_mode:[[:space:]]*"(serial|parallel)"' "$CFG" && pass "default_mode supports serial/parallel" || fail "default_mode not matching"
grep -q 'parallel:' "$CFG"                    && pass "parallel: sub-block"             || fail "parallel: sub-block missing"
grep -q 'reviewer_a_focus:' "$CFG"            && pass "reviewer_a_focus set"            || fail "reviewer_a_focus missing"
grep -q 'reviewer_b_focus:' "$CFG"            && pass "reviewer_b_focus set"            || fail "reviewer_b_focus missing"
grep -q 'synthesizer_template:' "$CFG"        && pass "synthesizer_template set"        || fail "synthesizer_template missing"
grep -q 'min_agreement_ratio:' "$CFG"         && pass "min_agreement_ratio set"         || fail "min_agreement_ratio missing"

# ---- [2] synthesizer template ----
echo ""
echo "[2] synthesizer template:"
ST=".codenook/prompts-templates/synthesizer.md"
if [[ ! -f $ST ]]; then
  fail "synthesizer.md missing"
else
  pass "synthesizer.md present"
  for var in review_a review_b review_a_summary review_b_summary implementer_summary; do
    grep -q "$var" "$ST" && pass "var referenced: $var" || fail "var NOT referenced: $var"
  done
  grep -q 'agreement_ratio' "$ST"    && pass "agreement_ratio defined"   || fail "agreement_ratio missing"
  grep -q 'overall_verdict' "$ST"    && pass "overall_verdict defined"   || fail "overall_verdict missing"
  grep -q 'Disagreements' "$ST"      && pass "disagreements handled"     || fail "disagreements missing"
fi

# ---- [3] synthesizer agent profile ----
echo ""
echo "[3] synthesizer agent profile:"
SA=".codenook/agents/synthesizer.agent.md"
if [[ ! -f $SA ]]; then
  fail "synthesizer.agent.md missing"
else
  pass "synthesizer.agent.md present"
  grep -q 'Self-Bootstrap Protocol' "$SA" && pass "self-bootstrap section" || fail "no self-bootstrap"
  grep -q 'too_large' "$SA"               && pass "too_large contract"     || fail "no too_large contract"
  grep -q 'fundamental_problems' "$SA"    && pass "fundamental handling"   || fail "no fundamental handling"
fi

# ---- [4] core.md parallel section ----
echo ""
echo "[4] core.md parallel section:"
CORE=".codenook/core/codenook-core.md"
grep -q 'Parallel + Synthesizer Protocol' "$CORE" && pass "§16 Parallel + Synthesizer Protocol" || fail "no §16 Parallel + Synthesizer Protocol"
grep -q 'run_dual_agent_parallel_loop' "$CORE"    && pass "parallel loop referenced in main loop" || fail "parallel loop not wired in main loop"
grep -q 'review-synthesized' "$CORE"              && pass "review-synthesized path referenced"  || fail "review-synthesized path not referenced"
grep -q 'min_agreement_ratio' "$CORE"             && pass "min_agreement_ratio handled"         || fail "min_agreement_ratio not handled"

# ---- [5] routing table has review-a / review-b / synthesize ----
echo ""
echo "[5] routing table entries:"
grep -q 'review-a' "$CORE"   && pass "review-a row in routing table"   || fail "review-a not in routing"
grep -q 'review-b' "$CORE"   && pass "review-b row in routing table"   || fail "review-b not in routing"
grep -q 'synthesize' "$CORE" && pass "synthesize row in routing table" || fail "synthesize not in routing"

# ---- [6] synthetic iter-1 synthesizer manifest passes lint ----
echo ""
echo "[6] synthetic iter-1 synthesizer manifest lints clean:"
mkdir -p ".codenook/tasks/T-001/iterations/iter-1"
mkdir -p ".codenook/tasks/T-001/prompts"
touch ".codenook/tasks/T-001/iterations/iter-1/implement-summary.md"
touch ".codenook/tasks/T-001/iterations/iter-1/review-a.md"
touch ".codenook/tasks/T-001/iterations/iter-1/review-a-summary.md"
touch ".codenook/tasks/T-001/iterations/iter-1/review-b.md"
touch ".codenook/tasks/T-001/iterations/iter-1/review-b-summary.md"
touch ".codenook/tasks/T-001/task.md"

cat > .codenook/tasks/T-001/prompts/iter-1-synthesizer.md <<EOF
Template: @../../../prompts-templates/synthesizer.md
Variables:
  task_id: T-001
  iteration: 1
  review_a: @../iterations/iter-1/review-a.md
  review_a_summary: @../iterations/iter-1/review-a-summary.md
  review_b: @../iterations/iter-1/review-b.md
  review_b_summary: @../iterations/iter-1/review-b-summary.md
  implementer_summary: @../iterations/iter-1/implement-summary.md
Output_to: @../iterations/iter-1/review-synthesized.md
Summary_to: @../iterations/iter-1/review-synthesized-summary.md
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

MANIFEST=".codenook/tasks/T-001/prompts/iter-1-synthesizer.md"
output=$(validate_manifest "$MANIFEST" 2>&1 && echo "__OK__" || echo "__FAIL__")
if echo "$output" | grep -q '__OK__'; then
  pass "iter-1 synthesizer manifest passes lint"
else
  fail "iter-1 synthesizer manifest FAILED lint"
  echo "$output"
fi

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T10 PASSED ==="
  exit 0
else
  echo "=== T10 FAILED ($FAIL issues) ==="
  exit 1
fi
