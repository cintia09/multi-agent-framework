#!/usr/bin/env bash
# T26: session-runner.sh CLI helper (manual §18 trigger)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== T26: session-runner.sh ==="
cd "$TMP" && bash "$INIT_SH" > /tmp/t26-init.log 2>&1
SR=.codenook/session-runner.sh

echo ""
echo "[1] Installed:"
[[ -x "$SR" ]] && pass "session-runner.sh +x" || { fail "missing"; exit 1; }

echo ""
echo "[2] list on empty workspace:"
out=$(bash "$SR" list 2>&1)
echo "$out" | grep -q 'no sessions yet' && pass "reports empty" || fail "missing empty msg"

echo ""
echo "[3] latest before any snapshot:"
rc=0; bash "$SR" latest >/dev/null 2>&1 || rc=$?
# Either rc=1 (no latest.md) or prints existing init-bootstrapped one.
if [[ -f .codenook/history/latest.md ]]; then
  [[ $rc -eq 0 ]] && pass "latest cat ok (init-bootstrapped)" || fail "rc=$rc but file exists"
else
  [[ $rc -eq 1 ]] && pass "rc=1 when no latest.md" || fail "rc=$rc"
fi

echo ""
echo "[4] tail with bad arg rejected:"
rc=0; bash "$SR" tail xyz >/dev/null 2>&1 || rc=$?
[[ $rc -eq 2 ]] && pass "rc=2 on non-numeric tail count" || fail "rc=$rc"

echo ""
echo "[5] prepare-snapshot writes manifest + dispatch line:"
out=$(bash "$SR" prepare-snapshot 2>&1)
mfile=$(echo "$out" | awk -F': ' '/^manifest:/ {print $2}')
[[ -f "$mfile" ]] && pass "manifest file written: $mfile" || fail "manifest not written"
echo "$out" | grep -q 'DISPATCH' && pass "prints DISPATCH line" || fail "no DISPATCH"
grep -q 'mode: snapshot' "$mfile" 2>/dev/null && pass "manifest contains mode: snapshot" || fail "no mode field"
grep -q 'session_distill\|session-distill\|session-distiller.md' "$mfile" 2>/dev/null && pass "manifest references distiller" || fail "no distiller ref"

echo ""
echo "[6] prepare-refresh writes refresh manifest:"
out=$(bash "$SR" prepare-refresh 2>&1)
mfile=$(echo "$out" | awk -F': ' '/^manifest:/ {print $2}')
[[ -f "$mfile" ]] && pass "refresh manifest written" || fail "refresh manifest missing"
grep -q 'mode: refresh' "$mfile" 2>/dev/null && pass "mode: refresh present" || fail "no mode field"

echo ""
echo "[7] Plant a session file -> list/tail show it:"
SF=.codenook/history/sessions/2025-01-15-session-1.md
echo "# Test session" > "$SF"
out=$(bash "$SR" list 2>&1)
echo "$out" | grep -q '2025-01-15-session-1.md' && pass "list shows planted file" || fail "list missing planted"
out=$(bash "$SR" tail 1 2>&1)
echo "$out" | grep -q 'Test session' && pass "tail prints content" || fail "tail missing content"

echo ""
echo "[8] Unknown command rejected:"
rc=0; bash "$SR" gibberish >/dev/null 2>&1 || rc=$?
[[ $rc -eq 2 ]] && pass "rc=2 on unknown" || fail "rc=$rc"

echo ""
if [[ $FAIL -eq 0 ]]; then echo "=== T26 PASSED ==="; exit 0; else echo "=== T26 FAILED ($FAIL) ==="; exit 1; fi
