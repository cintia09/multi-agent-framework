#!/usr/bin/env bash
# T16: Session Persistence — history/sessions + latest.md + session-distiller
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
bash "$INIT_SH" > /tmp/t16-init.log 2>&1

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== T16: Session Persistence ==="
echo ""

# ----------------------------------------------------------------------
# [1] init.sh creates the right layout
# ----------------------------------------------------------------------
echo "[1] Workspace layout:"
[[ -d .codenook/history ]]            && pass "history/ exists"           || fail "history/ missing"
[[ -d .codenook/history/sessions ]]   && pass "history/sessions/ exists"  || fail "history/sessions/ missing"
[[ -f .codenook/history/latest.md ]]  && pass "latest.md exists"          || fail "latest.md missing"

# ----------------------------------------------------------------------
# [2] latest.md matches the refresh skeleton (not the old placeholder)
# ----------------------------------------------------------------------
echo ""
echo "[2] latest.md skeleton:"
L=.codenook/history/latest.md
grep -q '^# Latest Session Summary' "$L"       && pass "has title"            || fail "no title"
grep -q '^_Last updated:' "$L"                 && pass "has timestamp slot"   || fail "no timestamp slot"
grep -q '^_Trigger:' "$L"                      && pass "has trigger slot"     || fail "no trigger slot"
grep -q '^## Workspace State' "$L"             && pass "has Workspace section" || fail "no workspace section"
grep -q '^## Current Task Snapshot' "$L"       && pass "has Task Snapshot"    || fail "no task snapshot section"
grep -q '^## Next Action for the Next Session' "$L" && pass "has Next Action" || fail "no next action"

# ----------------------------------------------------------------------
# [3] state.json has session_counter
# ----------------------------------------------------------------------
echo ""
echo "[3] state.json session fields:"
S=.codenook/state.json
grep -q '"session_counter"' "$S"  && pass "state.json has session_counter" || fail "missing session_counter"
grep -q '"last_session"'    "$S"  && pass "state.json has last_session"    || fail "missing last_session"

# ----------------------------------------------------------------------
# [4] session-distiller agent profile + template copied in
# ----------------------------------------------------------------------
echo ""
echo "[4] session-distiller artifacts:"
P=.codenook/prompts-templates/session-distiller.md
A=.codenook/agents/session-distiller.agent.md
[[ -f "$P" ]] && pass "template exists"      || fail "template missing"
[[ -f "$A" ]] && pass "agent profile exists" || fail "agent profile missing"

# Template declares both modes and the two output formats
grep -q '"refresh"'                    "$P" && pass "template: refresh mode declared"  || fail "template: no refresh mode"
grep -q '"snapshot"'                   "$P" && pass "template: snapshot mode declared" || fail "template: no snapshot mode"
grep -q 'Step 3a'                      "$P" && pass "template: Step 3a present"        || fail "template: no Step 3a"
grep -q 'Step 3b'                      "$P" && pass "template: Step 3b present"        || fail "template: no Step 3b"

# Agent profile has the required steps + Step 2.5 + skill-leak guard
grep -q '^### Step 2.5: Skill Trigger' "$A" && pass "agent: has Step 2.5"                       || fail "agent: no Step 2.5"
grep -q 'Do NOT include the skill name in your returned' "$A" && pass "agent: has leak guard"  || fail "agent: no leak guard"
grep -q 'session_distiller\|session-distiller' "$A" && pass "agent: references itself"          || fail "agent: no self-ref"

# Hard anti-patterns: no touching task state
grep -q 'Do not modify any task' "$A" && pass "agent: forbids task-state writes" || fail "agent: missing task-state guard"

# ----------------------------------------------------------------------
# [5] core.md §18 protocol present and consistent with §4/§5/§10
# ----------------------------------------------------------------------
echo ""
echo "[5] core.md integration:"
C=.codenook/core/codenook-core.md

grep -q '^## 18\. Session Lifecycle Protocol' "$C" && pass "§18 present"             || fail "§18 missing"

section18=$(awk '/^## 18\./,0' "$C")
echo "$section18" | grep -q 'mode: "refresh"'  && pass "§18 documents refresh mode"  || fail "§18 no refresh"
echo "$section18" | grep -q 'mode: "snapshot"' && pass "§18 documents snapshot mode" || fail "§18 no snapshot"
echo "$section18" | grep -q 'Trigger A'        && pass "§18 lists Trigger A"         || fail "§18 no Trigger A"
echo "$section18" | grep -q 'Trigger B'        && pass "§18 lists Trigger B"         || fail "§18 no Trigger B"
echo "$section18" | grep -q '_workspace'       && pass "§18 uses _workspace scope"   || fail "§18 no _workspace scope"
echo "$section18" | grep -q 'best-effort'      && pass "§18 refresh is best-effort"  || fail "§18 no best-effort"
echo "$section18" | grep -q 'mandatory'        && pass "§18 snapshot is mandatory"   || fail "§18 no mandatory"
echo "$section18" | grep -q 'session_counter'  && pass "§18 increments counter"      || fail "§18 no counter increment"

# §5 main loop calls post_phase_refresh
section5=$(awk '/^## 5\./,/^## 6\./' "$C")
echo "$section5" | grep -q 'post_phase_refresh' && pass "§5 calls post_phase_refresh" \
                                                || fail "§5 no post_phase_refresh hook"

# §10 context-check triggers snapshot at 80%
section10=$(awk '/^## 10\./,/^## 11\./' "$C")
echo "$section10" | grep -q 'snapshot'  && pass "§10 references snapshot at >80%"     || fail "§10 no snapshot trigger"
echo "$section10" | grep -q 'end-session\|end session' && pass "§10 lists user /end trigger" \
                                                       || fail "§10 no user /end trigger"

# §4 bootstrap optionally reads prior session
section4=$(awk '/^## 4\./,/^## 5\./' "$C")
echo "$section4" | grep -q 'last_session'    && pass "§4 reads state.last_session"    || fail "§4 ignores last_session"
echo "$section4" | grep -q 'sessions/'       && pass "§4 mentions sessions/ dir"       || fail "§4 no sessions/ ref"
echo "$section4" | grep -q 'Do NOT scan'     && pass "§4 forbids scanning all sessions" || fail "§4 no scan-prohibition"

# ----------------------------------------------------------------------
# [6] CLAUDE.md + core §12 have end-of-turn rule
# ----------------------------------------------------------------------
echo ""
echo "[6] End-of-turn ask-next rule:"
grep -q 'Interaction Rule' ./CLAUDE.md              && pass "CLAUDE.md has Interaction Rule section"    || fail "CLAUDE.md missing Interaction Rule"
grep -qi 'end of EVERY response' ./CLAUDE.md        && pass "CLAUDE.md enforces end-of-turn ask"        || fail "CLAUDE.md doesn't enforce end-of-turn"
section12=$(awk '/^## 12\./,/^## 13\./' "$C")
echo "$section12" | grep -q 'End-of-turn rule'      && pass "§12 has End-of-turn rule"                  || fail "§12 missing end-of-turn rule"
echo "$section12" | grep -qi 'must end with'        && pass "§12 mandates question at end"              || fail "§12 doesn't mandate question"

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T16 PASSED ==="
  exit 0
else
  echo "=== T16 FAILED ($FAIL issues) ==="
  exit 1
fi
