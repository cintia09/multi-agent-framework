#!/usr/bin/env bash
# CodeNook v5.0 POC — HITL Terminal Adapter
#
# Commands:
#   terminal.sh list                       List all pending HITL items (FIFO order).
#   terminal.sh show [<id>]                Show current.md, or a specific pending item.
#   terminal.sh answer <id> <option-id> [note...]
#                                          Record a decision for <id>, archive to answered/,
#                                          promote next pending (if any) to current.md.
#   terminal.sh count                      Print pending count (machine-readable).
#
# <id> is the basename of the pending file without the .md extension.
# Decisions are written to the task's hitl/ dir:
#   .codenook/tasks/<task_id>/hitl/<phase>-decision-<timestamp>.md

set -euo pipefail

WS="${CODENOOK_WORKSPACE:-.codenook}"
Q="$WS/hitl-queue"
P="$Q/pending"
A="$Q/answered"
CUR="$Q/current.md"

if [[ ! -d "$Q" ]]; then
  echo "error: $Q not found. Run this inside a CodeNook workspace." >&2
  exit 2
fi
mkdir -p "$P" "$A"

cmd="${1:-help}"

iso_now() { date -u +"%Y%m%dT%H%M%SZ"; }

# ------------------------------------------------------------ validators
# Security: pending-item IDs, task_ids, and phases from YAML are all used to
# construct filesystem paths. Validate strictly.
_assert_pending_id() {
  [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "error: invalid pending id: '$1' (allowed: [A-Za-z0-9._-]+)" >&2
    exit 2
  }
}
_assert_task_id() {
  [[ "$1" =~ ^T-[A-Za-z0-9]+(\.[0-9]+)?$ ]] || {
    echo "error: invalid task_id in pending item: '$1'" >&2
    exit 2
  }
}
_assert_phase() {
  [[ "$1" =~ ^[a-z][a-z0-9_-]*$ ]] || {
    echo "error: invalid phase in pending item: '$1'" >&2
    exit 2
  }
}

yaml_get() {
  awk -v k="$2" '
    /^---$/{n++; next}
    n==1 && $0 ~ "^"k":"{sub("^"k":[ \t]*",""); print; exit}
  ' "$1"
}

list_pending() {
  find "$P" -maxdepth 1 -name '*.md' 2>/dev/null | sort
}

promote_next() {
  local next
  next="$(list_pending | head -n1 || true)"
  if [[ -n "$next" ]]; then
    cp "$next" "$CUR"
    echo "  → promoted $(basename "$next" .md) to current.md"
  else
    : > "$CUR"
    echo "  → queue empty; current.md cleared"
  fi
}

case "$cmd" in
  list)
    items=$(list_pending)
    if [[ -z "$items" ]]; then
      echo "(no pending HITL items)"
      exit 0
    fi
    echo "Pending HITL items (FIFO):"
    while IFS= read -r f; do
      id=$(basename "$f" .md)
      task=$(yaml_get "$f" task_id)
      phase=$(yaml_get "$f" phase)
      reason=$(yaml_get "$f" reason)
      printf "  - %s  (task=%s phase=%s reason=%s)\n" "$id" "$task" "$phase" "$reason"
    done <<< "$items"
    ;;

  show)
    target="${2:-}"
    if [[ -z "$target" ]]; then
      if [[ -s "$CUR" ]]; then
        cat "$CUR"
      else
        echo "(current.md is empty; use 'list' to see pending)"
      fi
    else
      f="$P/$target.md"
      [[ -f "$f" ]] || { echo "error: $f not found" >&2; exit 1; }
      cat "$f"
    fi
    ;;

  answer)
    id="${2:-}"
    opt="${3:-}"
    shift 2 || true
    shift || true
    note="${*:-}"
    [[ -n "$id" && -n "$opt" ]] || {
      echo "usage: terminal.sh answer <id> <option-id> [note...]" >&2
      exit 2
    }
    _assert_pending_id "$id"
    _assert_pending_id "$opt"
    f="$P/$id.md"
    [[ -f "$f" ]] || { echo "error: pending item $id not found" >&2; exit 1; }

    task=$(yaml_get "$f" task_id)
    phase=$(yaml_get "$f" phase)
    [[ -n "$task" && -n "$phase" ]] || {
      echo "error: pending item $id missing task_id or phase" >&2
      exit 1
    }
    _assert_task_id "$task"
    _assert_phase "$phase"

    hitl_dir="$WS/tasks/$task/hitl"
    mkdir -p "$hitl_dir"
    ts=$(iso_now)
    decision_file="$hitl_dir/$phase-decision-$ts.md"

    {
      echo "---"
      echo "task_id: $task"
      echo "phase: $phase"
      echo "pending_id: $id"
      echo "answered_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "option_id: $opt"
      echo "answered_via: terminal-adapter"
      echo "---"
      echo ""
      echo "# Decision"
      echo ""
      echo "Selected option: **$opt**"
      if [[ -n "$note" ]]; then
        echo ""
        echo "## Note"
        echo ""
        echo "$note"
      fi
    } > "$decision_file"

    mv "$f" "$A/$id.md"

    echo "✅ decision recorded: $decision_file"
    promote_next
    ;;

  count)
    list_pending | wc -l | tr -d ' '
    ;;

  help|-h|--help|"")
    cat <<EOF
CodeNook v5.0 POC — HITL Terminal Adapter

Commands:
  list                                  List pending HITL items (FIFO).
  show [<id>]                           Show current.md or a specific pending item.
  answer <id> <option-id> [note...]     Record decision + promote next pending.
  count                                 Print pending count (machine-readable).

Workspace: $WS
EOF
    ;;

  *)
    echo "error: unknown command '$cmd'. Try 'terminal.sh help'." >&2
    exit 2
    ;;
esac
