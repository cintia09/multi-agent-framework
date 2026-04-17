#!/usr/bin/env bash
# CodeNook v5.0 — Session lifecycle helper (manual CLI counterpart to §18)
#
# §18 says only the session-distiller agent writes history/latest.md and
# history/sessions/*. This helper is the **manual-trigger** path the
# orchestrator uses when a user types `/end-session`, `wrap up`, etc.
# It writes a manifest and prints the dispatch line for the orchestrator
# to forward to the agent. It also has read-only commands (`list`,
# `latest`, `tail`) for inspecting persisted history without invoking
# the LLM.
#
# Usage:
#   session-runner.sh list                # list session files (newest first)
#   session-runner.sh latest              # cat latest.md
#   session-runner.sh tail [N]            # last N session files (default 3)
#   session-runner.sh prepare-snapshot    # write a snapshot manifest, print dispatch line
#   session-runner.sh prepare-refresh     # write a refresh manifest, print dispatch line
#
# The "prepare-*" commands DO NOT invoke any LLM. They emit the
# manifest path so the orchestrator can dispatch the session-distiller.
set -uo pipefail

WS=".codenook"
HIST="$WS/history"
SESSIONS="$HIST/sessions"
WORKSPACE_PROMPTS="$WS/tasks/_workspace/prompts"

[[ -d "$WS" ]] || { echo "error: $WS/ missing" >&2; exit 2; }

mkdir -p "$SESSIONS" "$WORKSPACE_PROMPTS"

cmd_list() {
  if [[ ! -d "$SESSIONS" ]]; then echo "(no sessions yet)"; return 0; fi
  local n=0
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    n=$((n+1))
    printf "  %s  %s\n" "$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$f" 2>/dev/null \
                          || stat -c '%y' "$f" 2>/dev/null | cut -d. -f1)" \
                       "$(basename "$f")"
  done < <(find "$SESSIONS" -maxdepth 1 -type f -name '*.md' 2>/dev/null | sort -r)
  [[ $n -eq 0 ]] && echo "(no sessions yet)"
}

cmd_latest() {
  if [[ -f "$HIST/latest.md" ]]; then
    cat "$HIST/latest.md"
  else
    echo "(latest.md not yet written)"
    return 1
  fi
}

cmd_tail() {
  local n="${1:-3}"
  case "$n" in *[!0-9]*|"") echo "error: tail count must be positive integer" >&2; exit 2 ;; esac
  local files
  files=$(find "$SESSIONS" -maxdepth 1 -type f -name '*.md' 2>/dev/null | sort -r | head -n "$n")
  if [[ -z "$files" ]]; then echo "(no sessions yet)"; return 0; fi
  while IFS= read -r f; do
    echo "════════ $(basename "$f") ════════"
    cat "$f"
    echo ""
  done <<< "$files"
}

_iso_date()  { date -u +%Y-%m-%d; }
_iso_stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

cmd_prepare_snapshot() {
  local stamp date counter manifest
  stamp=$(_iso_stamp)
  date=$(_iso_date)
  # Read session_counter from workspace state (or default 0).
  counter=0
  if [[ -f "$WS/state.json" ]]; then
    counter=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('session_counter',0))" "$WS/state.json" 2>/dev/null || echo 0)
  fi
  counter=$((counter + 1))
  manifest="$WORKSPACE_PROMPTS/session-distill-snapshot.md"
  cat > "$manifest" <<EOF
Template: @../../prompts-templates/session-distiller.md
Variables:
  mode: snapshot
  trigger: cli:session-runner.sh prepare-snapshot
  trigger_at: ${stamp}
  date: ${date}
  session_counter: ${counter}
  session_file_path: @${SESSIONS}/${date}-session-${counter}.md
  workspace_state: @${WS}/state.json
  latest_file: @${HIST}/latest.md
Output_to: @${SESSIONS}/${date}-session-${counter}.md
Summary_to: @${HIST}/latest.md
EOF
  echo "manifest: $manifest"
  echo ""
  echo "DISPATCH (orchestrator runs):"
  echo "  Execute session distillation. See $manifest"
}

cmd_prepare_refresh() {
  local stamp manifest
  stamp=$(_iso_stamp)
  manifest="$WORKSPACE_PROMPTS/session-distill-refresh.md"
  cat > "$manifest" <<EOF
Template: @../../prompts-templates/session-distiller.md
Variables:
  mode: refresh
  trigger: cli:session-runner.sh prepare-refresh
  trigger_at: ${stamp}
  workspace_state: @${WS}/state.json
  latest_file: @${HIST}/latest.md
Summary_to: @${HIST}/latest.md
EOF
  echo "manifest: $manifest"
  echo ""
  echo "DISPATCH (orchestrator runs):"
  echo "  Execute session distillation. See $manifest"
}

case "${1:-}" in
  list)              shift; cmd_list "$@" ;;
  latest)            shift; cmd_latest "$@" ;;
  tail)              shift; cmd_tail "$@" ;;
  prepare-snapshot)  shift; cmd_prepare_snapshot "$@" ;;
  prepare-refresh)   shift; cmd_prepare_refresh "$@" ;;
  -h|--help|"")      sed -n '2,21p' "$0" ;;
  *) echo "unknown command: $1" >&2; exit 2 ;;
esac
