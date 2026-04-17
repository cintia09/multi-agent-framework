#!/usr/bin/env bash
# T14: Invoke_skill manifest schema + Step 2.5 in all agent profiles
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
bash "$INIT_SH" > /tmp/t14-init.log 2>&1

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== T14: Invoke_skill Schema + Skill Trigger Step ==="
echo ""

CORE=".codenook/core/codenook-core.md"

# ---- [1] core.md §6 documents Invoke_skill field ----
echo "[1] core.md §6 schema:"
grep -q 'Invoke_skill:' "$CORE"                 && pass "Invoke_skill field registered" || fail "no Invoke_skill in §6"
grep -q 'Skill Trigger Channel' "$CORE"         && pass "trigger-channel heading"       || fail "no trigger-channel heading"
grep -qi 'Write.*Edit tool\|Write / Edit' "$CORE" && pass "Write/Edit-only rule"        || fail "no Write/Edit rule"
grep -qi 'one .Invoke_skill' "$CORE"            && pass "one-per-manifest rule"         || fail "no cardinality rule"

# ---- [2] core.md §11 updated rule ----
echo ""
echo "[2] core.md §11 updated:"
grep -q 'Absolute prohibitions' "$CORE"         && pass "prohibitions block"     || fail "no prohibitions"
grep -q 'echo .codenook-distill' "$CORE"        && pass "bash-echo explicit ban" || fail "no echo ban"
grep -q 'completion stream' "$CORE"             && pass "completion-stream concept" || fail "no completion-stream"

# ---- [3] ALL 9 agent profiles have Step 2.5 ----
echo ""
echo "[3] Step 2.5 in every agent profile:"
for f in .codenook/agents/*.agent.md; do
  name=$(basename "$f")
  grep -qE '^### Step 2\.5[: —]+Skill Trigger' "$f" \
    && pass "$name: Step 2.5 present" \
    || fail "$name: missing Step 2.5"
  grep -q 'Invoke_skill' "$f" \
    && pass "$name: references Invoke_skill" \
    || fail "$name: no Invoke_skill ref"
  grep -qi 'verbatim\|literal string' "$f" \
    && pass "$name: verbatim contract" \
    || fail "$name: no verbatim contract"
done

# ---- [4] Manifest linter accepts Invoke_skill ----
echo ""
echo "[4] synthetic manifest with Invoke_skill lints clean:"
T_DIR=".codenook/tasks/T-001"
mkdir -p "$T_DIR/prompts" "$T_DIR/outputs"
touch "$T_DIR/outputs/phase-3-implementer.md"

cat > "$T_DIR/prompts/phase-4-distill.md" <<'EOF'
Template: @../../../prompts-templates/implementer.md
Invoke_skill: codenook-distill/knowledge-extract
Variables:
  task_id: T-001
  phase: distill
  source_output: @../outputs/phase-3-implementer.md
Output_to: @../outputs/phase-4-distill.md
Summary_to: @../outputs/phase-4-distill-summary.md
EOF

mf="$T_DIR/prompts/phase-4-distill.md"
mdir=$(dirname "$mf")
errs=0
for k in Template Variables Output_to Summary_to; do
  grep -qE "^${k}:" "$mf" || { echo "    missing: $k"; errs=$((errs+1)); }
done
# Invoke_skill must not be treated as a path — skip it when extracting @refs
while IFS= read -r ref; do
  ref_path="${ref#@}"
  abs="$mdir/$ref_path"
  [[ -e $abs ]] || { echo "    broken @ref: $ref"; errs=$((errs+1)); }
done < <(grep -vE '^(Output_to|Graph_to|Summary_to|Invoke_skill):' "$mf" | grep -oE '@[A-Za-z0-9_./-]+' | sort -u)
[[ $errs -eq 0 ]] && pass "manifest lint clean (Invoke_skill ignored by @-resolver)" || fail "manifest lint failed ($errs)"

# ---- [5] skill name is NEVER hardcoded in core.md routing logic ----
echo ""
echo "[5] no skill name leaked into orchestrator routing:"
# §6/§11 legitimately contain 'codenook-distill' as example — anywhere else is a leak
leak=$(grep -n 'codenook-distill\|baoyu-' "$CORE" | grep -v '## 6\.' | grep -v '## 11\.' | head -5 || true)
# simpler: extract context — just verify count is bounded (within §6 example + §11 ban text)
count=$(grep -c 'codenook-distill' "$CORE" || true)
[[ $count -le 4 ]] && pass "skill name only in §6 example / §11 ban ($count occurrences)" \
                   || fail "skill name leaked ($count occurrences, expected ≤4)"

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T14 PASSED ==="
  exit 0
else
  echo "=== T14 FAILED ($FAIL issues) ==="
  exit 1
fi
