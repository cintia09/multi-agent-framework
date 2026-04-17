#!/usr/bin/env bash
# T25: Workspace security — secret-scan + keyring-helper + auditor agent
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== T25: Workspace Security (scan + keyring + auditor) ==="
cd "$TMP" && bash "$INIT_SH" > /tmp/t25-init.log 2>&1

# ----------------------------------------------------------------------
# [1] Helpers + agent installed
# ----------------------------------------------------------------------
echo ""
echo "[1] Files installed:"
[[ -x .codenook/secret-scan.sh    ]] && pass "secret-scan.sh +x"     || fail "secret-scan missing"
[[ -x .codenook/keyring-helper.sh ]] && pass "keyring-helper.sh +x"  || fail "keyring-helper missing"
[[ -f .codenook/agents/security-auditor.agent.md ]] && pass "security-auditor.agent.md" || fail "auditor profile missing"
[[ -f .codenook/.secretignore     ]] && pass ".secretignore present" || fail ".secretignore missing"
[[ -d .codenook/history/security  ]] && pass "history/security/ dir" || fail "history/security missing"

# ----------------------------------------------------------------------
# [2] Clean workspace -> no findings
# ----------------------------------------------------------------------
echo ""
echo "[2] Clean workspace = 0 findings:"
rc=0; out=$(bash .codenook/secret-scan.sh 2>&1) || rc=$?
[[ $rc -eq 0 ]] && pass "rc=0 on clean workspace" || fail "rc=$rc on clean: $out"
echo "$out" | grep -q 'no findings' && pass "reports clean" || fail "missing clean message"

# ----------------------------------------------------------------------
# [3] Plant a fake OpenAI key in workspace -> warn (rc=1)
# ----------------------------------------------------------------------
echo ""
echo "[3] Detects sk- key:"
mkdir -p .codenook/tasks/T-fake/prompts
echo 'openai_api_key: sk-AAAAAAAAAAAAAAAAAAAAAAAA' > .codenook/tasks/T-fake/prompts/leak.md
rc=0; out=$(bash .codenook/secret-scan.sh 2>&1) || rc=$?
[[ $rc -eq 1 ]] && pass "rc=1 (warn) on finding" || fail "rc=$rc (expected 1)"
echo "$out" | grep -q 'openai' && pass "names openai pattern" || fail "openai not named"

# ----------------------------------------------------------------------
# [4] --strict turns rc=1 into rc=2
# ----------------------------------------------------------------------
echo ""
echo "[4] --strict escalates to rc=2:"
rc=0; bash .codenook/secret-scan.sh --strict >/dev/null 2>&1 || rc=$?
[[ $rc -eq 2 ]] && pass "strict rc=2" || fail "strict rc=$rc (expected 2)"

# ----------------------------------------------------------------------
# [5] --json output is valid JSON with count>0
# ----------------------------------------------------------------------
echo ""
echo "[5] --json output:"
out=$(bash .codenook/secret-scan.sh --json 2>/dev/null || true)
echo "$out" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['count']>=1; assert d['findings'][0]['pattern']" \
  && pass "valid JSON with finding" || fail "json invalid: $out"

# ----------------------------------------------------------------------
# [6] .secretignore suppresses
# ----------------------------------------------------------------------
echo ""
echo "[6] .secretignore suppression:"
echo 'leak.md' > .codenook/.secretignore
rc=0; out=$(bash .codenook/secret-scan.sh 2>&1) || rc=$?
[[ $rc -eq 0 ]] && pass "rc=0 after ignoring" || fail "rc=$rc (expected 0): $out"
# Restore so later checks use clean baseline.
: > .codenook/.secretignore
rm -rf .codenook/tasks/T-fake

# ----------------------------------------------------------------------
# [7] Keyring helper: check (skip-tolerant if package missing)
# ----------------------------------------------------------------------
echo ""
echo "[7] Keyring helper check:"
rc=0; out=$(bash .codenook/keyring-helper.sh check 2>&1) || rc=$?
case $rc in
  0) pass "keyring usable: $(echo "$out" | grep '^backend:' || echo unknown)" ;;
  3) pass "keyring not installed (rc=3, expected fall-through)"; KEYRING_AVAILABLE=0 ;;
  *) fail "unexpected rc=$rc: $out" ;;
esac
KEYRING_AVAILABLE=${KEYRING_AVAILABLE:-1}

# ----------------------------------------------------------------------
# [8] Keyring helper: usage error on bad key name
# ----------------------------------------------------------------------
echo ""
echo "[8] Keyring helper rejects unsafe key:"
rc=0; bash .codenook/keyring-helper.sh get 'evil;rm -rf /' >/dev/null 2>&1 || rc=$?
[[ $rc -eq 2 ]] && pass "rc=2 on unsafe key" || fail "rc=$rc (expected 2)"

# ----------------------------------------------------------------------
# [9] Keyring resolve: substitutes ${keyring:codenook/X} (only if available)
# ----------------------------------------------------------------------
echo ""
echo "[9] Keyring resolve:"
if [[ $KEYRING_AVAILABLE -eq 1 ]]; then
  # We can't reliably set/get against a real keyring in CI; just verify
  # the resolve command runs and leaves unknown refs intact.
  echo 'config: ${keyring:codenook/T25_NONEXISTENT}' > /tmp/t25-resolve.yaml
  out=$(bash .codenook/keyring-helper.sh resolve /tmp/t25-resolve.yaml 2>/dev/null || true)
  echo "$out" | grep -q 'T25_NONEXISTENT' && pass "leaves unknown ref intact" || fail "resolve broke ref"
else
  pass "skipped (keyring backend unavailable)"
fi

# ----------------------------------------------------------------------
# [10] Preflight integrates check [9] secret-scan and [10] keyring
# ----------------------------------------------------------------------
echo ""
echo "[10] preflight.sh integration:"
out=$(bash .codenook/preflight.sh 2>&1 || true)
echo "$out" | grep -q '\[9\] Secret scan' && pass "preflight runs secret scan" || fail "no [9]"
echo "$out" | grep -q '\[10\] Keyring backend' && pass "preflight runs keyring check" || fail "no [10]"

# ----------------------------------------------------------------------
# [11] CLAUDE.md Step 2.5 dispatches security-auditor
# ----------------------------------------------------------------------
echo ""
echo "[11] CLAUDE.md security dispatch:"
grep -qE 'Step 0|Step 2.5' CLAUDE.md && pass "security audit step present" || fail "security audit step missing"
grep -q 'security-auditor' CLAUDE.md && pass "names auditor agent" || fail "agent not named"
grep -q 'verdict=' CLAUDE.md && pass "documents verdict line" || fail "verdict undocumented"

# ----------------------------------------------------------------------
# [12] core.md §23 documented
# ----------------------------------------------------------------------
echo ""
echo "[12] core.md §23 Workspace Security:"
C=.codenook/core/codenook-core.md
grep -q '^## 23. Workspace Security' "$C" && pass "§23 exists" || fail "§23 missing"
s23=$(awk '/^## 23\./{p=1; print; next} p; /^## 24\.|^---$/{if(p && /^## /) p=0}' "$C")
echo "$s23" | grep -qi 'keyring' && pass "§23 names keyring" || fail "keyring not named"
echo "$s23" | grep -qi 'secret-scan' && pass "§23 cites secret-scan" || fail "secret-scan not cited"
echo "$s23" | grep -qi 'security-auditor' && pass "§23 names auditor" || fail "auditor not named"
echo "$s23" | grep -qi '\.secretignore' && pass "§23 documents .secretignore" || fail ".secretignore not documented"

# ----------------------------------------------------------------------
# [13] security-auditor agent profile shape
# ----------------------------------------------------------------------
echo ""
echo "[13] security-auditor.agent.md shape:"
A=.codenook/agents/security-auditor.agent.md
grep -q '^## Invocation (Mode B)' "$A" && pass "Mode B Invocation block" || fail "no Mode B block"
grep -q 'Self-Bootstrap Protocol' "$A" && pass "self-bootstrap section" || fail "no bootstrap"
grep -q 'verdict=' "$A" && pass "specifies verdict line" || fail "verdict not specified"
grep -qi 'never paste' "$A" && pass "warns against pasting secrets" || fail "no anti-paste warning"

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T25 PASSED ==="
  exit 0
else
  echo "=== T25 FAILED ($FAIL) ==="
  exit 1
fi
