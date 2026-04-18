#!/usr/bin/env bash
# CodeNook v5.0 — Convenience wrapper for the session security audit.
#
# Runs preflight + secret-scan + keyring health check directly without
# requiring an LLM session. Use this if:
#   - you suspect the orchestrator skipped Step 0 of CLAUDE.md
#   - you want a quick CI / pre-commit check
#   - you want to manually re-run before a sensitive operation
#
# Output format (last line) matches what the security-auditor agent
# returns to the orchestrator.

set -u

# Auto-locate the workspace root: walk up from the script's directory
# looking for a `.codenook/` sibling. This makes the script robust to
# any cwd (including hook invocations from sub-agents whose cwd is the
# parent process's cwd, not the workspace).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# When installed by init.sh, the script lives at <workspace>/.codenook/security-audit.sh
# so the workspace root is the parent of SCRIPT_DIR.
if [[ -d "$SCRIPT_DIR/../.codenook" ]]; then
  WS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
elif [[ -d "$(pwd)/.codenook" ]]; then
  # Fallback: caller is in a workspace root.
  WS_ROOT="$(pwd)"
else
  echo "error: cannot locate CodeNook workspace (no .codenook/ at script location or cwd)" >&2
  exit 2
fi
cd "$WS_ROOT"

WS=".codenook"
[[ -d "$WS" ]] || { echo "error: not in a CodeNook workspace ($WS_ROOT/.codenook missing)" >&2; exit 2; }

DATE=$(date +%Y-%m-%d)
REPORT="$WS/history/security/${DATE}.md"
SUMMARY="$WS/history/security/${DATE}-summary.md"
mkdir -p "$WS/history/security"

# ---- preflight ------------------------------------------------------------
preflight_out=$(bash "$WS/preflight.sh" 2>&1) || true
preflight_rc=0
echo "$preflight_out" | grep -qE "errors:[[:space:]]+0" || preflight_rc=1

# ---- secret scan ----------------------------------------------------------
secrets_out=$(bash "$WS/secret-scan.sh" 2>&1) || true
secrets_count=$(echo "$secrets_out" | grep -cE "^[^:]+:[0-9]+:" || true)

# ---- keyring health -------------------------------------------------------
keyring_status="unknown"
if bash "$WS/keyring-helper.sh" check >/dev/null 2>&1; then
  keyring_status="ok"
else
  keyring_status="missing"
fi

# ---- verdict --------------------------------------------------------------
verdict="pass"
[[ $preflight_rc -ne 0 ]] && verdict="warn"
[[ $secrets_count -gt 0 ]] && verdict="fail"
[[ "$keyring_status" == "broken" ]] && verdict="fail"

# ---- write report ---------------------------------------------------------
{
  echo "# Security Audit — $DATE"
  echo
  echo "## Verdict: $verdict"
  echo
  echo "## Preflight (rc=$preflight_rc)"
  echo '```'; echo "$preflight_out"; echo '```'
  echo
  echo "## Secret Scan ($secrets_count findings)"
  echo '```'; echo "$secrets_out" | head -30; echo '```'
  echo
  echo "## Keyring: $keyring_status"
} > "$REPORT"

{
  echo "verdict=$verdict preflight_rc=$preflight_rc secrets=$secrets_count keyring=$keyring_status"
  echo "report: $REPORT"
} > "$SUMMARY"

cat "$SUMMARY"
[[ "$verdict" == "fail" ]] && exit 1 || exit 0
