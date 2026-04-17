#!/usr/bin/env bash
# CodeNook v5.0 POC — Queue Runtime helper
#
# A read-side / bookkeeping companion to the orchestrator's scheduler (core §19).
# The orchestrator itself performs the tick loop inside its main session; this
# script lets humans and external tooling inspect and maintain queue state
# between turns, and it exposes a tiny dependency-graph parser.
#
# Commands:
#   status                   Print counts for pending/dispatching/completed
#   list <queue>             Print items in queue (pending|dispatching|completed)
#   sweep                    Move dispatching items whose expected output file
#                            exists into completed.json (FIFO-safe, idempotent)
#   ready <task_id>          Compute ready subtasks by parsing the task's
#                            dependency-graph.md against its state.json
#   deps <task_id>           Dump parsed (child, parent) edges
#   cycles <task_id>         Detect cycles in dependency graph (exit 2 if any)
#   lock <path> <agent_id>   Acquire a file-level lock (fails if held)
#   unlock <path>            Release a lock (no-op if missing)
#   help                     This message
#
# Exit codes:
#   0  success
#   1  usage / file error
#   2  semantic failure (cycle, lock held, missing file)
#
# Dependencies: bash 3.2+, awk, grep, sort, mktemp, date. No jq.
set -euo pipefail

WS="${CODENOOK_WORKSPACE:-.codenook}"
QDIR="$WS/queue"
LOCKS="$WS/locks"
TASKS="$WS/tasks"

# ------------------------------------------------------------ validators
# Security: all IDs, paths, and agent identifiers reaching this script may
# be LLM-generated. Validate before using them to construct filesystem paths
# or write metadata.
_re_task_id='^T-[A-Za-z0-9]+(\.[0-9]+)?$'
_re_safe_slug='^[A-Za-z0-9_.:@/-]+$'

_assert_task_id() {
  [[ "$1" =~ $_re_task_id ]] || {
    echo "error: invalid task_id: '$1' (must match $_re_task_id)" >&2
    exit 2
  }
}

# Accept common filesystem path characters but reject control chars,
# backslashes, whitespace, and .. traversal segments. Absolute paths are
# also rejected — locks are workspace-scoped.
_assert_safe_path() {
  local p="$1"
  [[ "$p" != /* ]] || { echo "error: absolute path not allowed: '$p'" >&2; exit 2; }
  [[ "$p" == *..* ]] && { echo "error: path must not contain '..': '$p'" >&2; exit 2; }
  [[ "$p" =~ $_re_safe_slug ]] || {
    echo "error: unsafe path: '$p' (allowed: $_re_safe_slug)" >&2
    exit 2
  }
}

# Agent IDs are written verbatim into YAML-like lock files; forbid newlines
# and control chars to prevent log/format injection.
_assert_safe_agent_id() {
  [[ "$1" =~ ^[A-Za-z0-9_.@:-]+$ ]] || {
    echo "error: invalid agent_id: '$1' (allowed: [A-Za-z0-9_.@:-]+)" >&2
    exit 2
  }
}

iso_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# ---- small JSON helpers (schema: queue files are {"items":[...]}) ----
# We use awk-based counting / extraction rather than jq to keep zero-dep.
json_count() {
  # Count top-level objects in .items by counting '"agent_id"' occurrences.
  local f="$1"
  [[ -f "$f" ]] || { echo 0; return; }
  local c
  c=$(grep -c '"agent_id"' "$f" 2>/dev/null || true)
  echo "${c:-0}"
}

json_ids() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  grep -o '"agent_id"[[:space:]]*:[[:space:]]*"[^"]*"' "$f" \
    | sed -E 's/.*"agent_id"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/'
}

ensure_queue_files() {
  mkdir -p "$QDIR" "$LOCKS"
  for q in pending dispatching completed; do
    [[ -f "$QDIR/$q.json" ]] || printf '{"items":[]}\n' > "$QDIR/$q.json"
  done
}

# ---- dependency-graph parser ----
# Writes TSV to stdout: child<TAB>parent (one edge per line).
parse_edges() {
  local graph="$1"
  [[ -f "$graph" ]] || { echo "error: $graph not found" >&2; return 2; }
  awk '
    /^## Edges/   { in_edges=1; next }
    /^## /        { in_edges=0 }
    in_edges && /^- .* depends_on .*/ {
      line=$0; sub(/^- /,"",line)
      n=split(line,parts," depends_on ")
      if (n==2) { gsub(/^[[:space:]]+|[[:space:]]+$/,"",parts[1]);
                  gsub(/^[[:space:]]+|[[:space:]]+$/,"",parts[2]);
                  printf "%s\t%s\n", parts[1], parts[2] }
    }
  ' "$graph"
}

# Writes node ids to stdout (one per line).
parse_nodes() {
  local graph="$1"
  awk '
    /^## Nodes/   { in_nodes=1; next }
    /^## /        { in_nodes=0 }
    in_nodes && /^- [^ ]+:/ {
      line=$0; sub(/^- /,"",line); sub(/:.*$/,"",line); print line
    }
  ' "$graph"
}

# Detect cycles via topological sort (Kahn's algo, pure bash/awk).
# Returns 0 if acyclic, 2 if cycle found (prints offending node set).
detect_cycles() {
  local graph="$1"
  local tmp_nodes tmp_edges
  tmp_nodes=$(mktemp); tmp_edges=$(mktemp)
  parse_nodes "$graph" > "$tmp_nodes"
  parse_edges "$graph" > "$tmp_edges" || { rm -f "$tmp_nodes" "$tmp_edges"; return 2; }
  awk -v NODES_FILE="$tmp_nodes" -v EDGES_FILE="$tmp_edges" '
    BEGIN {
      while ((getline line < NODES_FILE) > 0) {
        if (line!="") { ind[line]=0; all[line]=1 }
      }
      close(NODES_FILE)
      while ((getline line < EDGES_FILE) > 0) {
        if (line=="") continue
        split(line,p,"\t")
        ind[p[1]]++
        children[p[2]] = (p[2] in children ? children[p[2]] "\n" p[1] : p[1])
      }
      close(EDGES_FILE)
      queue=""
      for (k in all) if (ind[k]==0) queue = queue " " k
      visited=0
      while (length(queue)>0) {
        sub(/^ /,"",queue)
        nq=split(queue, q, " ")
        head=q[1]
        newq=""
        for (i=2;i<=nq;i++) if (q[i]!="") newq = newq " " q[i]
        queue=newq
        visited++
        c=children[head]
        if (c=="") continue
        nc=split(c, cc, "\n")
        for (i=1;i<=nc;i++) if (cc[i]!="") {
          ind[cc[i]]--
          if (ind[cc[i]]==0) queue = queue " " cc[i]
        }
      }
      total=0; for (k in all) total++
      if (visited<total) {
        printf("CYCLE: only %d of %d nodes resolved\n", visited, total) > "/dev/stderr"
        for (k in all) if (ind[k]>0) printf("  unresolved: %s (indegree=%d)\n",k,ind[k]) > "/dev/stderr"
        exit 2
      }
    }
  '
  local rc=$?
  rm -f "$tmp_nodes" "$tmp_edges"
  return $rc
}

# ---- commands ----
cmd_status() {
  ensure_queue_files
  printf "pending:     %s\n" "$(json_count "$QDIR/pending.json")"
  printf "dispatching: %s\n" "$(json_count "$QDIR/dispatching.json")"
  printf "completed:   %s\n" "$(json_count "$QDIR/completed.json")"
}

cmd_list() {
  ensure_queue_files
  local q="${1:-}"
  [[ -z "$q" ]] && { echo "usage: queue-runner.sh list <pending|dispatching|completed>" >&2; return 1; }
  local f="$QDIR/$q.json"
  [[ -f "$f" ]] || { echo "no such queue: $q" >&2; return 1; }
  local n; n=$(json_count "$f")
  if [[ "$n" == "0" ]]; then echo "($q is empty)"; return; fi
  json_ids "$f"
}

cmd_sweep() {
  ensure_queue_files
  # For v5.0 POC: the queue item schema contains "expected_output" (a path).
  # If that file exists, the item is considered complete. We do a textual
  # rewrite of dispatching.json → completed.json for matching items.
  local disp="$QDIR/dispatching.json" comp="$QDIR/completed.json"
  [[ -f "$disp" ]] || { echo "nothing to sweep"; return; }
  if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 required for sweep (v5.0 POC limitation)" >&2
    return 1
  fi
  python3 - "$disp" "$comp" "$(iso_now)" <<'PY'
import json, sys, os
disp_path, comp_path, now = sys.argv[1], sys.argv[2], sys.argv[3]
disp = json.load(open(disp_path))
comp = json.load(open(comp_path)) if os.path.exists(comp_path) else {"items": []}
kept, moved = [], 0
for it in disp.get("items", []):
    out = it.get("expected_output")
    if out and os.path.exists(out):
        it["completed_at"] = now
        it["status"] = it.get("status") or "success"
        comp.setdefault("items", []).append(it)
        moved += 1
    else:
        kept.append(it)
disp["items"] = kept
json.dump(disp, open(disp_path, "w"), indent=2); open(disp_path, "a").write("\n")
json.dump(comp, open(comp_path, "w"), indent=2); open(comp_path, "a").write("\n")
print(f"swept {moved} item(s) dispatching \u2192 completed")
PY
}

cmd_ready() {
  local tid="${1:-}"
  [[ -z "$tid" ]] && { echo "usage: queue-runner.sh ready <task_id>" >&2; return 1; }
  _assert_task_id "$tid"
  local graph="$TASKS/$tid/decomposition/dependency-graph.md"
  local state="$TASKS/$tid/state.json"
  [[ -f "$graph" ]] || { echo "no dependency-graph.md for $tid" >&2; return 2; }
  [[ -f "$state" ]] || { echo "no state.json for $tid" >&2; return 2; }
  # Collect subtask status map from state.json.
  python3 - "$graph" "$state" <<'PY'
import json, re, sys
graph_path, state_path = sys.argv[1], sys.argv[2]
state = json.load(open(state_path))
status = {s["id"]: s.get("status","pending") for s in state.get("subtasks",[])}
nodes, edges = [], []
section = None
for line in open(graph_path):
    line = line.rstrip()
    if line.startswith("## Nodes"):    section="nodes";  continue
    if line.startswith("## Edges"):    section="edges";  continue
    if line.startswith("## "):         section=None;     continue
    if section=="nodes" and line.startswith("- "):
        nid = line[2:].split(":",1)[0].strip()
        if nid: nodes.append(nid)
    elif section=="edges" and line.startswith("- ") and " depends_on " in line:
        child, parent = line[2:].split(" depends_on ",1)
        edges.append((child.strip(), parent.strip()))
deps = {n: set() for n in nodes}
for c,p in edges: deps.setdefault(c,set()).add(p)
ready = []
for n in nodes:
    if status.get(n,"pending") != "pending": continue
    if all(status.get(p,"pending")=="done" for p in deps[n]):
        ready.append(n)
for n in ready: print(n)
PY
}

cmd_deps() {
  local tid="${1:-}"
  [[ -z "$tid" ]] && { echo "usage: queue-runner.sh deps <task_id>" >&2; return 1; }
  _assert_task_id "$tid"
  local graph="$TASKS/$tid/decomposition/dependency-graph.md"
  parse_edges "$graph"
}

cmd_cycles() {
  local tid="${1:-}"
  [[ -z "$tid" ]] && { echo "usage: queue-runner.sh cycles <task_id>" >&2; return 1; }
  _assert_task_id "$tid"
  local graph="$TASKS/$tid/decomposition/dependency-graph.md"
  if detect_cycles "$graph"; then echo "acyclic"; return 0; else return 2; fi
}

cmd_lock() {
  local path="${1:-}" agent="${2:-}"
  [[ -z "$path" || -z "$agent" ]] && { echo "usage: queue-runner.sh lock <path> <agent_id>" >&2; return 1; }
  _assert_safe_path "$path"
  _assert_safe_agent_id "$agent"
  mkdir -p "$LOCKS"
  local lockfile="$LOCKS/$(printf '%s' "$path" | tr '/' '-').lock"
  if [[ -f "$lockfile" ]]; then
    local holder; holder=$(grep -E '^holder:' "$lockfile" | sed 's/holder:[[:space:]]*//')
    echo "lock held by: $holder" >&2
    return 2
  fi
  cat > "$lockfile" <<EOF
holder: $agent
acquired_at: $(iso_now)
path: $path
EOF
  echo "locked: $path"
}

cmd_unlock() {
  local path="${1:-}"
  [[ -z "$path" ]] && { echo "usage: queue-runner.sh unlock <path>" >&2; return 1; }
  _assert_safe_path "$path"
  local lockfile="$LOCKS/$(printf '%s' "$path" | tr '/' '-').lock"
  [[ -f "$lockfile" ]] && rm -f "$lockfile" && echo "unlocked: $path" || echo "(no lock for $path)"
}

cmd_help() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
}

main() {
  local sub="${1:-help}"; shift || true
  case "$sub" in
    status)  cmd_status  "$@" ;;
    list)    cmd_list    "$@" ;;
    sweep)   cmd_sweep   "$@" ;;
    ready)   cmd_ready   "$@" ;;
    deps)    cmd_deps    "$@" ;;
    cycles)  cmd_cycles  "$@" ;;
    lock)    cmd_lock    "$@" ;;
    unlock)  cmd_unlock  "$@" ;;
    help|-h|--help) cmd_help ;;
    *) echo "unknown command: $sub" >&2; cmd_help >&2; exit 1 ;;
  esac
}
main "$@"
