#!/usr/bin/env bash
# codenook — workspace CLI wrapper (v0.11.4, E2E-001 / E2E-008 / E2E-P-002,P-005,P-008).
#
# Installed by `bash install.sh` into <workspace>/.codenook/bin/codenook.
# Resolves the kernel via `kernel_dir` recorded in <workspace>/.codenook/state.json
# so the wrapper works from any cwd inside (or outside, with --workspace) the
# workspace.
#
# Subcommands:
#   codenook task new --title "…" [--summary "…"] [--plugin <id>] [--target-dir <p>]
#                     [--dual-mode serial|parallel] [--max-iterations N] [--parent T-X]
#                     [--priority P0|P1|P2|P3] [--accept-defaults]
#   codenook task set --task T-NNN --field <field> --value <val>
#                     # writable fields: dual_mode, target_dir, priority,
#                     # max_iterations, summary, title
#   codenook router   --task T-NNN --user-turn "…"
#   codenook tick     --task T-NNN [--json]
#   codenook decide   --task T-NNN --phase <id> --decision approve|reject|needs_changes [--comment "…"]
#   codenook status   [--task T-NNN]
#   codenook chain    link --child T-X --parent T-Y [--force]
#   codenook chain    show <task>
#   codenook chain    detach <task>
#
# Exit codes: 0 ok | 1 runtime error | 2 entry-question / usage | 3 already attached / not modified.

set -euo pipefail

# --- ensure `python3` is callable -------------------------------------------
# On Windows the .cmd shim prepends a Python install dir to PATH, but the
# executable there is usually `python.exe` (not `python3.exe`). We synthesize
# a tiny `python3` shim in a temp dir and front-load it onto PATH so every
# downstream call (this script, spawn.sh, tick.sh, host_driver.py) finds it
# without code changes.
if ! command -v python3 >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    _CN_SHIM_DIR="${TMPDIR:-/tmp}/codenook-pyshim-$$"
    mkdir -p "$_CN_SHIM_DIR"
    cat > "$_CN_SHIM_DIR/python3" <<'PYSHIM'
#!/usr/bin/env bash
exec python "$@"
PYSHIM
    chmod +x "$_CN_SHIM_DIR/python3"
    PATH="$_CN_SHIM_DIR:$PATH"
    export PATH
    trap 'rm -rf "$_CN_SHIM_DIR"' EXIT
  else
    echo "codenook: neither python3 nor python found on PATH" >&2
    echo "          install Python 3 (https://www.python.org/downloads/) and re-run" >&2
    exit 1
  fi
fi

# --- locate workspace + kernel ------------------------------------------------
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DEFAULT="$(cd "$HERE/../.." && pwd)"

CODENOOK_WORKSPACE="${CODENOOK_WORKSPACE:-$WORKSPACE_DEFAULT}"

# Allow --workspace override; consume it if first arg.
if [ "${1:-}" = "--workspace" ]; then
  CODENOOK_WORKSPACE="$(cd "$2" && pwd)"; shift 2
fi

STATE_JSON="$CODENOOK_WORKSPACE/.codenook/state.json"
if [ ! -f "$STATE_JSON" ]; then
  echo "codenook: no .codenook/state.json under $CODENOOK_WORKSPACE" >&2
  echo "          run: bash install.sh \"$CODENOOK_WORKSPACE\"" >&2
  exit 1
fi

KERNEL_DIR="$(CN_STATE="$STATE_JSON" python3 -c "import json,os; d=json.load(open(os.environ['CN_STATE'])); print(d.get('kernel_dir') or '')" 2>/dev/null || true)"
# On Git-Bash / msys2, kernel_dir is stored in native Windows form (C:\..)
# but bash test/cd want msys POSIX form (/c/..). Normalize via cygpath when
# available; otherwise do a manual drive-letter rewrite.
if [ -n "$KERNEL_DIR" ] && [[ "$KERNEL_DIR" == *'\'* ]]; then
  if command -v cygpath >/dev/null 2>&1; then
    KERNEL_DIR="$(cygpath -u "$KERNEL_DIR")"
  elif [[ "$KERNEL_DIR" =~ ^([A-Za-z]):\\(.*)$ ]]; then
    _drv="$(printf '%s' "${BASH_REMATCH[1]}" | tr 'A-Z' 'a-z')"
    KERNEL_DIR="/${_drv}/${BASH_REMATCH[2]//\\//}"
  fi
fi
if [ -z "$KERNEL_DIR" ] || [ ! -d "$KERNEL_DIR" ]; then
  echo "codenook: kernel_dir missing/invalid in $STATE_JSON" >&2
  echo "          re-run: bash install.sh \"$CODENOOK_WORKSPACE\"" >&2
  exit 1
fi

LIB_DIR="$KERNEL_DIR/_lib"
TICK_SH="$KERNEL_DIR/orchestrator-tick/tick.sh"
ROUTER_SPAWN="$KERNEL_DIR/router-agent/spawn.sh"
ROUTER_DRIVER="$KERNEL_DIR/router-agent/host_driver.py"
HITL_SH="$KERNEL_DIR/hitl-adapter/terminal.sh"
TASK_CONFIG_SET="$KERNEL_DIR/task-config-set/set.sh"

export PYTHONPATH="$LIB_DIR${PYTHONPATH:+:$PYTHONPATH}"
export CODENOOK_WORKSPACE

usage() {
  sed -n '3,21p' "$0" | sed 's/^# \{0,1\}//'
}

# --- helpers ------------------------------------------------------------------
next_task_id() {
  # Find next free T-NNN under .codenook/tasks/
  local n=1
  while [ -d "$CODENOOK_WORKSPACE/.codenook/tasks/T-$(printf '%03d' "$n")" ]; do
    n=$((n+1))
  done
  printf 'T-%03d\n' "$n"
}

cmd_task() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    new) cmd_task_new "$@" ;;
    set) cmd_task_set "$@" ;;
    *) echo "codenook task: unknown subcommand: ${sub:-<none>}" >&2;
       echo "  use: new | set" >&2; exit 2 ;;
  esac
}

cmd_task_new() {
  local title="" summary="" plugin="" target_dir="" dual_mode=""
  local dual_mode_set="0" priority="P2" max_iter=3 parent="" task_id=""
  local accept_defaults="0"
  while [ $# -gt 0 ]; do
    case "$1" in
      --title) title="$2"; shift 2 ;;
      --summary) summary="$2"; shift 2 ;;
      --plugin) plugin="$2"; shift 2 ;;
      --target-dir) target_dir="$2"; shift 2 ;;
      --dual-mode) dual_mode="$2"; dual_mode_set="1"; shift 2 ;;
      --max-iterations) max_iter="$2"; shift 2 ;;
      --parent) parent="$2"; shift 2 ;;
      --priority) priority="$2"; shift 2 ;;
      --accept-defaults) accept_defaults="1"; shift ;;
      --id) task_id="$2"; shift 2 ;;
      *) echo "codenook task new: unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  if [ -z "$title" ]; then
    echo "codenook task new: --title is required" >&2; exit 2
  fi

  # E2E-P-008 — validate --priority enum.
  case "$priority" in
    P0|P1|P2|P3) : ;;
    *) echo "codenook task new: invalid --priority '$priority' (allowed: P0|P1|P2|P3)" >&2; exit 2 ;;
  esac

  # E2E-P-005 — default target_dir to src/ when not provided.
  if [ -z "$target_dir" ]; then
    target_dir="src/"
  fi

  if [ -z "$plugin" ]; then
    plugin="$(CN_STATE="$STATE_JSON" python3 -c "import json,os; d=json.load(open(os.environ['CN_STATE'])); ip=d.get('installed_plugins') or []; print((ip[0].get('id') if ip else '') or '')")"
  fi
  if [ -z "$plugin" ]; then
    echo "codenook task new: no installed plugin found in state.json" >&2; exit 1
  fi
  if [ -z "$task_id" ]; then task_id="$(next_task_id)"; fi

  local tdir="$CODENOOK_WORKSPACE/.codenook/tasks/$task_id"
  mkdir -p "$tdir/outputs" "$tdir/prompts" "$tdir/notes"

  CN_NEW_TID="$task_id" CN_NEW_TITLE="$title" CN_NEW_SUMMARY="$summary" \
  CN_NEW_PLUGIN="$plugin" CN_NEW_TARGET="$target_dir" CN_NEW_DUAL="$dual_mode" \
  CN_NEW_DUAL_SET="$dual_mode_set" CN_NEW_ACCEPT="$accept_defaults" \
  CN_NEW_MAX="$max_iter" CN_NEW_PARENT="$parent" CN_NEW_PRIORITY="$priority" \
  python3 - "$tdir/state.json" <<'PY'
import json, os, sys
state = {
  "schema_version": 1,
  "task_id":  os.environ["CN_NEW_TID"],
  "plugin":   os.environ["CN_NEW_PLUGIN"],
  "phase":    None,
  "iteration": 0,
  "max_iterations": int(os.environ.get("CN_NEW_MAX","3") or "3"),
  "status":   "in_progress",
  "history":  [],
  "priority": os.environ.get("CN_NEW_PRIORITY","P2") or "P2",
}
# E2E-P-002: only set dual_mode when explicitly provided OR when
# --accept-defaults was supplied. Otherwise leave it unset so the entry-
# question gate fires below.
if os.environ.get("CN_NEW_DUAL_SET") == "1":
    state["dual_mode"] = os.environ.get("CN_NEW_DUAL","serial") or "serial"
elif os.environ.get("CN_NEW_ACCEPT") == "1":
    state["dual_mode"] = "serial"
for src, dst in (("CN_NEW_TITLE","title"),
                 ("CN_NEW_SUMMARY","summary"),
                 ("CN_NEW_TARGET","target_dir")):
    v = os.environ.get(src) or ""
    if v:
        state[dst] = v
parent = os.environ.get("CN_NEW_PARENT") or ""
if parent:
    state["parent_id"] = parent
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
PY
  if [ -n "$parent" ]; then
    python3 -m task_chain --workspace "$CODENOOK_WORKSPACE" attach "$task_id" "$parent" || true
  fi

  # E2E-P-002 — surface entry-question for missing --dual-mode (exit 2).
  if [ "$dual_mode_set" = "0" ] && [ "$accept_defaults" = "0" ]; then
    cat <<EOF
{"action":"entry_question","task":"$task_id","field":"dual_mode","allowed_values":["serial","parallel"],"recovery":"codenook task set --task $task_id --field dual_mode --value <serial|parallel>"}
EOF
    exit 2
  fi

  echo "$task_id"
}

cmd_task_set() {
  if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    cat <<'HELP'
Usage: codenook task set --task T-NNN --field <field> --value <val>

Writable fields:
  dual_mode       serial | parallel
  target_dir      directory path (e.g. src/)
  priority        P0 | P1 | P2 | P3
  max_iterations  positive integer
  summary         free text
  title           free text
HELP
    exit 0
  fi
  local task="" field="" value="" value_set="0"
  while [ $# -gt 0 ]; do
    case "$1" in
      --task)  task="$2"; shift 2 ;;
      --field) field="$2"; shift 2 ;;
      --value) value="$2"; value_set="1"; shift 2 ;;
      *) echo "codenook task set: unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  [ -n "$task" ] && [ -n "$field" ] && [ "$value_set" = "1" ] || {
    echo "codenook task set: --task, --field, --value all required" >&2; exit 2; }
  local sf="$CODENOOK_WORKSPACE/.codenook/tasks/$task/state.json"
  [ -f "$sf" ] || { echo "codenook task set: no such task: $task" >&2; exit 1; }

  CN_SET_FILE="$sf" CN_SET_FIELD="$field" CN_SET_VALUE="$value" python3 - <<'PY'
import json, os, sys
sf = os.environ["CN_SET_FILE"]; field = os.environ["CN_SET_FIELD"]
value = os.environ["CN_SET_VALUE"]
ALLOWED = {"dual_mode": ("serial","parallel"),
           "priority":  ("P0","P1","P2","P3")}
INT_FIELDS = {"max_iterations"}
WRITABLE = {"dual_mode","target_dir","priority","max_iterations","summary","title"}
if field not in WRITABLE:
    print(f"codenook task set: field '{field}' is not writable (allowed: {sorted(WRITABLE)})", file=sys.stderr)
    sys.exit(2)
if field in ALLOWED and value not in ALLOWED[field]:
    print(f"codenook task set: invalid value '{value}' for {field} (allowed: {ALLOWED[field]})", file=sys.stderr)
    sys.exit(2)
if field in INT_FIELDS:
    try: value = int(value)
    except ValueError:
        print(f"codenook task set: {field} must be an integer", file=sys.stderr); sys.exit(2)
with open(sf) as f: state = json.load(f)
state[field] = value
with open(sf, "w") as f: json.dump(state, f, indent=2)
print(json.dumps({"task": state.get("task_id"), "field": field, "value": value}))
PY
}

cmd_router() {
  local task="" user_turn=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --task) task="$2"; shift 2 ;;
      --user-turn) user_turn="$2"; shift 2 ;;
      *) echo "codenook router: unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  [ -n "$task" ] || { echo "codenook router: --task required" >&2; exit 2; }
  [ -n "$user_turn" ] || { echo "codenook router: --user-turn required" >&2; exit 2; }

  # Run router-agent. spawn.sh prints a single-line JSON envelope on stdout
  # describing the round-trip; the actual reply body lands in router-reply.md
  # AFTER the conductor (main LLM session) dispatches a sub-agent using
  # prompt_path as the system prompt (see CLAUDE.md §1).
  "$ROUTER_SPAWN" --task-id "$task" --workspace "$CODENOOK_WORKSPACE" --user-turn "$user_turn"

  # Optional headless / batch mode: if CN_ROUTER_DRIVE=1, run host_driver.py
  # to do the LLM round-trip in-process (uses _lib/llm_call.py — defaults to
  # mock unless CN_LLM_MODE=real). Off by default so the conductor LLM can
  # drive the dispatch via its own sub-agent facility (the v6 protocol).
  if [ "${CN_ROUTER_DRIVE:-0}" = "1" ]; then
    if [ -x "$ROUTER_DRIVER" ] || [ -f "$ROUTER_DRIVER" ]; then
      python3 "$ROUTER_DRIVER" --task-id "$task" --workspace "$CODENOOK_WORKSPACE" || true
    fi
    local _reply="$CODENOOK_WORKSPACE/.codenook/tasks/$task/router-reply.md"
    if [ -f "$_reply" ]; then
      echo
      echo "----- router-reply.md -----"
      cat "$_reply"
      echo "----- end router-reply -----"
    fi
  fi
}

cmd_tick() {
  local task="" json_flag=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --task) task="$2"; shift 2 ;;
      --json) json_flag="--json"; shift ;;
      *) echo "codenook tick: unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  [ -n "$task" ] || { echo "codenook tick: --task required" >&2; exit 2; }
  exec "$TICK_SH" --task "$task" --workspace "$CODENOOK_WORKSPACE" $json_flag
}

cmd_decide() {
  local task="" phase="" decision="" comment=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --task) task="$2"; shift 2 ;;
      --phase) phase="$2"; shift 2 ;;
      --decision) decision="$2"; shift 2 ;;
      --comment) comment="$2"; shift 2 ;;
      *) echo "codenook decide: unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  [ -n "$task" ] && [ -n "$phase" ] && [ -n "$decision" ] || {
    echo "codenook decide: --task, --phase, --decision required" >&2; exit 2; }
  if [ ! -x "$HITL_SH" ]; then
    echo "codenook decide: hitl-adapter not found at $HITL_SH" >&2; exit 1
  fi
  # Resolve hitl-queue entry id for (task, phase=gate). Phases.yaml maps
  # phase id → gate id; look up the matching pending entry by task+gate.
  local plugin
  plugin="$(CN_TS="$CODENOOK_WORKSPACE/.codenook/tasks/$task/state.json" python3 -c "import json,os; d=json.load(open(os.environ['CN_TS'])); print(d['plugin'])")"
  local gate
  gate="$(python3 - "$CODENOOK_WORKSPACE/.codenook/plugins/$plugin/phases.yaml" "$phase" <<'PY' 2>/dev/null
import sys, yaml
phases = yaml.safe_load(open(sys.argv[1])).get("phases", [])
phase_id = sys.argv[2]
for p in phases:
    if p.get("id") == phase_id:
        print(p.get("gate") or phase_id)
        break
else:
    print(phase_id)
PY
)"
  local entry_id
  entry_id="$(python3 - "$CODENOOK_WORKSPACE/.codenook/hitl-queue" "$task" "$gate" <<'PY'
import os, json, sys, glob
qdir, task, gate = sys.argv[1], sys.argv[2], sys.argv[3]
hits = []
for p in sorted(glob.glob(os.path.join(qdir, '*.json'))):
    try:
        e = json.load(open(p))
    except Exception:
        continue
    if e.get('task_id') == task and e.get('gate') == gate and not e.get('decision'):
        hits.append(e.get('id'))
print(hits[0] if hits else "")
PY
)"
  if [ -z "$entry_id" ]; then
    echo "codenook decide: no pending HITL entry for task=$task phase=$phase (gate=$gate)" >&2
    exit 1
  fi
  "$HITL_SH" decide --id "$entry_id" --decision "$decision" --reviewer "${USER:-cli}" \
    ${comment:+--comment "$comment"} --workspace "$CODENOOK_WORKSPACE" >/dev/null
  echo "{\"id\":\"$entry_id\",\"task\":\"$task\",\"phase\":\"$phase\",\"gate\":\"$gate\",\"decision\":\"$decision\"}"
}

cmd_status() {
  local task=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --task) task="$2"; shift 2 ;;
      *) echo "codenook status: unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  if [ -n "$task" ]; then
    local f="$CODENOOK_WORKSPACE/.codenook/tasks/$task/state.json"
    [ -f "$f" ] || { echo "codenook status: no such task: $task" >&2; exit 1; }
    cat "$f"
  else
    echo "Workspace: $CODENOOK_WORKSPACE"
    cat "$STATE_JSON"
    if [ -d "$CODENOOK_WORKSPACE/.codenook/tasks" ]; then
      echo "Tasks:"
      for d in "$CODENOOK_WORKSPACE"/.codenook/tasks/T-*/; do
        [ -d "$d" ] || continue
        local id; id="$(basename "$d")"
        local ph st
        ph="$(CN_TS="$d/state.json" python3 -c "import json,os; d=json.load(open(os.environ['CN_TS'])); print(d.get('phase') or '<none>')" 2>/dev/null || echo '?')"
        st="$(CN_TS="$d/state.json" python3 -c "import json,os; d=json.load(open(os.environ['CN_TS'])); print(d.get('status') or '?')" 2>/dev/null || echo '?')"
        echo "  $id phase=$ph status=$st"
      done
    fi
  fi
}

cmd_chain() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    link|attach)
      local child="" parent="" force=""
      while [ $# -gt 0 ]; do
        case "$1" in
          --child) child="$2"; shift 2 ;;
          --parent) parent="$2"; shift 2 ;;
          --force) force="--force"; shift ;;
          *) echo "codenook chain link: unknown arg: $1" >&2; exit 2 ;;
        esac
      done
      [ -n "$child" ] && [ -n "$parent" ] || {
        echo "codenook chain link: --child and --parent required" >&2; exit 2; }
      python3 -m task_chain --workspace "$CODENOOK_WORKSPACE" attach "$child" "$parent" $force
      # Echo the canonical fields for traceability.
      python3 - "$CODENOOK_WORKSPACE/.codenook/tasks/$child/state.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(json.dumps({"child": d.get("task_id"),
                  "parent_id": d.get("parent_id"),
                  "chain_root": d.get("chain_root")}))
PY
      ;;
    show)
      python3 -m task_chain --workspace "$CODENOOK_WORKSPACE" show "$@"
      ;;
    detach)
      python3 -m task_chain --workspace "$CODENOOK_WORKSPACE" detach "$@"
      ;;
    *)
      echo "codenook chain: unknown subcommand: ${sub:-<none>}" >&2
      echo "  use: link | show | detach" >&2
      exit 2
      ;;
  esac
}

# --- dispatch -----------------------------------------------------------------
case "${1:-}" in
  -h|--help|help|"") usage; exit 0 ;;
  --version) CN_STATE="$STATE_JSON" python3 -c "import json,os;print(json.load(open(os.environ['CN_STATE'])).get('kernel_version','?'))" ;;
  task)   shift; cmd_task   "$@" ;;
  router) shift; cmd_router "$@" ;;
  tick)   shift; cmd_tick   "$@" ;;
  decide) shift; cmd_decide "$@" ;;
  status) shift; cmd_status "$@" ;;
  chain)  shift; cmd_chain  "$@" ;;
  *) echo "codenook: unknown subcommand: $1" >&2; usage >&2; exit 2 ;;
esac
