#!/usr/bin/env bash
# CodeNook v5.0 — Subtask Runner
# Mechanical helper for the parent-of-subtasks coordination work that
# core §17 (Subtask Fan-out Protocol) describes. The orchestrator stays
# a pure router; this script does the deterministic file/JSON wrangling
# so no LLM tokens are wasted on it.
#
# Usage:
#   bash subtask-runner.sh seed       <T-XXX>          # create subtasks/ from decomposition/
#   bash subtask-runner.sh status     <T-XXX>          # show subtask statuses
#   bash subtask-runner.sh ready      <T-XXX>          # list pending subtasks whose deps are all done
#   bash subtask-runner.sh mark       <T-XXX.N> <status>  # update subtask status (pending|in_progress|done|blocked)
#   bash subtask-runner.sh integration-ready <T-XXX>   # exit 0 if all subtasks done
#   bash subtask-runner.sh deps       <T-XXX>          # print parsed dep graph (debug)
#
# Exit codes:
#   0 = ok / yes
#   1 = no (not ready, not done, etc.)
#   2 = usage / missing files

set -uo pipefail

WS=".codenook"
TASKS="$WS/tasks"

usage() { sed -n '2,16p' "$0" >&2; exit 2; }

[[ $# -ge 1 ]] || usage
CMD="$1"; shift

# ---------------------------------------------------------------- helpers

require_task() {
  local t="$1"
  [[ -d "$TASKS/$t" ]] || { echo "error: task $t not found at $TASKS/$t" >&2; exit 2; }
}

graph_path() { echo "$TASKS/$1/decomposition/dependency-graph.md"; }
plan_path()  { echo "$TASKS/$1/decomposition/plan.md"; }
state_path() { echo "$TASKS/$1/state.json"; }

# Parse dep graph → emit "<child>\t<parent>" lines (one parent per line; nodes
# with zero deps emit "<id>\t" so we know they exist).
parse_graph() {
  local gf="$1"
  [[ -f "$gf" ]] || { echo "error: graph not found: $gf" >&2; return 2; }
  python3 - "$gf" <<'PY'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1])
text = p.read_text().splitlines()
section = None
nodes, edges = [], []
for line in text:
    s = line.strip()
    if s.startswith("## "):
        h = s[3:].strip().lower()
        if h == "nodes": section = "nodes"
        elif h == "edges": section = "edges"
        else: section = None
        continue
    if not s.startswith("- "):
        continue
    body = s[2:]
    if section == "nodes":
        nid = body.split(":", 1)[0].strip()
        if nid:
            nodes.append(nid)
    elif section == "edges":
        m = re.match(r"^(\S+)\s+depends_on\s+(\S+)\s*$", body)
        if not m:
            print(f"__EDGE_PARSE_ERROR__\t{body}", file=sys.stderr)
            continue
        child, parent = m.group(1), m.group(2)
        edges.append((child, parent))
seen_with_parent = set()
for c, par in edges:
    print(f"{c}\t{par}")
    seen_with_parent.add(c)
for n in nodes:
    if n not in seen_with_parent:
        print(f"{n}\t")
PY
}

# Parse plan.md Subtask List table → emit "<id>\t<title>\t<scope>\t<outputs>"
parse_plan_subtasks() {
  local pf="$1"
  [[ -f "$pf" ]] || { echo "error: plan not found: $pf" >&2; return 2; }
  python3 - "$pf" <<'PY'
import sys, pathlib, re
p = pathlib.Path(sys.argv[1])
lines = p.read_text().splitlines()
in_section = False
header_seen = False
for line in lines:
    s = line.strip()
    if s.startswith("## ") or s.startswith("### "):
        in_section = "subtask list" in s.lower()
        header_seen = False
        continue
    if not in_section:
        continue
    if not s.startswith("|"):
        continue
    cells = [c.strip() for c in s.strip("|").split("|")]
    # Skip header row and the |---|---| separator
    if not header_seen:
        header_seen = True
        continue
    if all(set(c) <= set("-: ") for c in cells):
        continue
    # Need at least: id, title, scope, primary_outputs
    if len(cells) < 4:
        continue
    sid = cells[0]
    if not re.match(r"^T-\S+\.\d+$", sid):
        continue
    title    = cells[1]
    scope    = cells[2]
    outs     = cells[3]
    print(f"{sid}\t{title}\t{scope}\t{outs}")
PY
}

ensure_state_json() {
  local sf="$1" tid="$2" parent="$3" deps="$4"
  python3 - "$sf" "$tid" "$parent" "$deps" <<'PY'
import json, sys, pathlib
sf, tid, parent, deps = sys.argv[1:5]
p = pathlib.Path(sf)
dep_list = [d for d in deps.split(",") if d]
data = {
    "task_id": tid,
    "parent_id": parent,
    "status": "pending",
    "phase": "clarify",
    "depends_on": dep_list,
    "dual_mode": "inherit"
}
p.write_text(json.dumps(data, indent=2) + "\n")
PY
}

update_parent_subtasks() {
  # Rewrite parent state.json's `subtasks` array from current subtask state files.
  local parent="$1"
  local sf
  sf=$(state_path "$parent")
  [[ -f "$sf" ]] || { echo '{}' > "$sf"; }
  python3 - "$parent" "$sf" "$TASKS" <<'PY'
import json, sys, pathlib, glob, os
parent, sf, tasks_root = sys.argv[1:4]
sub_dir = os.path.join(tasks_root, parent, "subtasks")
subs = []
if os.path.isdir(sub_dir):
    for d in sorted(os.listdir(sub_dir)):
        ssf = os.path.join(sub_dir, d, "state.json")
        if not os.path.isfile(ssf):
            continue
        with open(ssf) as f:
            st = json.load(f)
        subs.append({
            "id": st.get("task_id", d),
            "status": st.get("status", "pending"),
            "depends_on": st.get("depends_on", []),
        })
data = {}
p = pathlib.Path(sf)
if p.exists() and p.stat().st_size > 0:
    try:
        data = json.loads(p.read_text())
    except Exception:
        data = {}
data.setdefault("task_id", parent)
data["subtasks"] = subs
data.setdefault("integration_phases", {"test": "pending", "accept": "pending"})
if subs and not data.get("phase","").startswith("subtasks"):
    data["phase"] = "subtasks_in_flight"
p.write_text(json.dumps(data, indent=2) + "\n")
PY
}

# ---------------------------------------------------------------- commands

cmd_seed() {
  local t="$1"
  require_task "$t"
  local pf gf base
  pf=$(plan_path "$t"); gf=$(graph_path "$t")
  base="$TASKS/$t"
  [[ -f "$pf" ]] || { echo "error: missing $pf — planner must run first" >&2; exit 2; }
  [[ -f "$gf" ]] || { echo "error: missing $gf — planner must run first" >&2; exit 2; }

  python3 - "$t" "$pf" "$gf" "$base" <<'PY'
import json, os, re, sys, pathlib

t, pf, gf, base = sys.argv[1:5]

# --- Parse graph (## Nodes / ## Edges) ---
nodes, edges = [], []
section = None
for line in pathlib.Path(gf).read_text().splitlines():
    s = line.strip()
    if s.startswith("## "):
        h = s[3:].strip().lower()
        section = "nodes" if h == "nodes" else ("edges" if h == "edges" else None)
        continue
    if not s.startswith("- "):
        continue
    body = s[2:]
    if section == "nodes":
        nid = body.split(":", 1)[0].strip()
        if nid: nodes.append(nid)
    elif section == "edges":
        m = re.match(r"^(\S+)\s+depends_on\s+(\S+)\s*$", body)
        if not m:
            print(f"  warn: unparsable edge: {body!r}", file=sys.stderr)
            continue
        edges.append((m.group(1), m.group(2)))

deps = {n: [] for n in nodes}
for child, parent in edges:
    deps.setdefault(child, [])
    deps.setdefault(parent, [])
    if parent not in deps[child]:
        deps[child].append(parent)

# --- Parse plan.md Subtask List table ---
in_section = False
header_seen = False
rows = []
for line in pathlib.Path(pf).read_text().splitlines():
    s = line.strip()
    if s.startswith("## ") or s.startswith("### "):
        in_section = "subtask list" in s.lower()
        header_seen = False
        continue
    if not in_section or not s.startswith("|"):
        continue
    cells = [c.strip() for c in s.strip("|").split("|")]
    if not header_seen:
        header_seen = True
        continue
    if all(set(c) <= set("-: ") for c in cells):
        continue
    if len(cells) < 4:
        continue
    sid = cells[0]
    if not re.match(r"^T-\S+\.\d+$", sid):
        continue
    rows.append((sid, cells[1], cells[2], cells[3]))

# --- Seed dirs ---
seeded = 0
plan_ids = set()
for sid, title, scope, outs in rows:
    plan_ids.add(sid)
    sub = os.path.join(base, "subtasks", sid)
    if os.path.isdir(sub):
        print(f"  skip {sid} (already seeded)")
        continue
    for d in ("prompts", "outputs", "iterations"):
        os.makedirs(os.path.join(sub, d), exist_ok=True)
    with open(os.path.join(sub, "task.md"), "w") as f:
        f.write(
            f"# {sid} — {title}\n\n"
            f"## Scope\n{scope}\n\n"
            f"## Primary Outputs\n{outs}\n\n"
            f"## Parent context\n"
            f"- Parent task: `{t}`\n"
            f"- Parent clarify: `@../../outputs/phase-1-clarify.md`\n"
            f"- Parent design:  `@../../outputs/phase-2-design.md`\n"
            f"- Parent decomp:  `@../../decomposition/plan.md`\n"
        )
    sub_deps = deps.get(sid, [])
    state = {
        "task_id": sid,
        "parent_id": t,
        "status": "pending",
        "phase": "clarify",
        "depends_on": sub_deps,
        "dual_mode": "inherit",
    }
    with open(os.path.join(sub, "state.json"), "w") as f:
        json.dump(state, f, indent=2); f.write("\n")
    seeded += 1
    print(f"  seeded {sid} (deps: {','.join(sub_deps) or 'none'})")

# Orphans
graph_ids = set(deps.keys())
for nid in graph_ids - plan_ids:
    if not os.path.isdir(os.path.join(base, "subtasks", nid)):
        print(f"  warn: {nid} in dependency-graph.md but not in plan.md", file=sys.stderr)
for sid in plan_ids - graph_ids:
    print(f"  warn: {sid} in plan.md but not in dependency-graph.md", file=sys.stderr)

print(f"seeded {seeded} subtask(s) under {base}/subtasks/")
PY

  update_parent_subtasks "$t"
}

cmd_status() {
  local t="$1"
  require_task "$t"
  local sf
  sf=$(state_path "$t")
  [[ -f "$sf" ]] || { echo "no state.json yet for $t"; exit 0; }
  python3 - "$sf" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    s = json.load(f)
subs = s.get("subtasks", [])
if not subs:
    print(f"{s.get('task_id','?')}: no subtasks")
    sys.exit(0)
print(f"{s.get('task_id','?')} (phase: {s.get('phase','?')})")
for sub in subs:
    deps = ",".join(sub.get("depends_on", [])) or "-"
    print(f"  {sub['id']:<14} {sub['status']:<14} deps={deps}")
ip = s.get("integration_phases", {})
if ip:
    print(f"integration: {ip}")
PY
}

cmd_ready() {
  local t="$1"
  require_task "$t"
  local sf
  sf=$(state_path "$t")
  [[ -f "$sf" ]] || { echo "no state.json yet" >&2; exit 1; }
  python3 - "$sf" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    s = json.load(f)
subs = s.get("subtasks", [])
done = {x["id"] for x in subs if x.get("status") == "done"}
ready = []
for sub in subs:
    if sub.get("status") != "pending":
        continue
    deps = sub.get("depends_on", [])
    if all(d in done for d in deps):
        ready.append(sub["id"])
for r in ready:
    print(r)
sys.exit(0 if ready else 1)
PY
}

cmd_mark() {
  local sid="$1" status="$2"
  case "$status" in pending|in_progress|done|blocked) ;; *)
    echo "error: status must be pending|in_progress|done|blocked" >&2; exit 2 ;;
  esac
  # Derive parent id from sid: T-003.1 → T-003
  local parent
  parent=$(echo "$sid" | awk -F'.' '{print $1}')
  local sub="$TASKS/$parent/subtasks/$sid"
  [[ -d "$sub" ]] || { echo "error: subtask not seeded: $sub" >&2; exit 2; }
  python3 - "$sub/state.json" "$status" <<'PY'
import json, sys
p = sys.argv[1]; new = sys.argv[2]
with open(p) as f: s = json.load(f)
s["status"] = new
with open(p, "w") as f: json.dump(s, f, indent=2); f.write("\n")
PY
  update_parent_subtasks "$parent"
  echo "$sid → $status"
}

cmd_integration_ready() {
  local t="$1"
  require_task "$t"
  local sf
  sf=$(state_path "$t")
  [[ -f "$sf" ]] || { echo "no state.json" >&2; exit 1; }
  python3 - "$sf" <<'PY'
import json, sys
with open(sys.argv[1]) as f: s = json.load(f)
subs = s.get("subtasks", [])
if not subs:
    print("no subtasks"); sys.exit(1)
not_done = [x["id"] for x in subs if x.get("status") != "done"]
if not_done:
    print("waiting on: " + ",".join(not_done))
    sys.exit(1)
print("all subtasks done — integration-ready")
sys.exit(0)
PY
}

cmd_deps() {
  local t="$1"
  require_task "$t"
  local gf
  gf=$(graph_path "$t")
  parse_graph "$gf"
}

case "$CMD" in
  seed)               [[ $# -eq 1 ]] || usage; cmd_seed "$1" ;;
  status)             [[ $# -eq 1 ]] || usage; cmd_status "$1" ;;
  ready)              [[ $# -eq 1 ]] || usage; cmd_ready "$1" ;;
  mark)               [[ $# -eq 2 ]] || usage; cmd_mark "$1" "$2" ;;
  integration-ready)  [[ $# -eq 1 ]] || usage; cmd_integration_ready "$1" ;;
  deps)               [[ $# -eq 1 ]] || usage; cmd_deps "$1" ;;
  *) usage ;;
esac
