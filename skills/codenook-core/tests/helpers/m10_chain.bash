#!/usr/bin/env bash
# Helpers for M10.1 task-chain bats suite.
#
# All paths are absolute. Tests use $M10_LIB_DIR as PYTHONPATH so the
# in-repo _lib modules (task_chain, extract_audit, memory_layer, …)
# resolve without an install step.

M10_LIB_DIR="$CORE_ROOT/skills/builtin/_lib"
M10_AUDIT_LOG_REL=".codenook/memory/history/extraction-log.jsonl"

export M10_LIB_DIR M10_AUDIT_LOG_REL

# m10_py <python source> — run python with PYTHONPATH=$M10_LIB_DIR.
m10_py() {
  PYTHONPATH="$M10_LIB_DIR" python3 -c "$1"
}

# m10_seed_workspace — create a fresh workspace with .codenook/tasks/.
m10_seed_workspace() {
  local d
  d=$(make_scratch)
  mkdir -p "$d/.codenook/tasks"
  echo "$d"
}

# make_task <ws> <task_id>
# Writes a minimal valid state.json (no parent_id field — fresh task).
make_task() {
  local ws="$1" tid="$2"
  local dir="$ws/.codenook/tasks/$tid"
  mkdir -p "$dir/outputs"
  cat >"$dir/state.json" <<JSON
{
  "schema_version": 1,
  "task_id": "$tid",
  "plugin": "development",
  "phase": "design",
  "iteration": 0,
  "max_iterations": 5,
  "status": "in_progress",
  "history": []
}
JSON
}

# make_chain <ws> <root> <c1> [c2 …]
# Creates each task then attaches in order: c1.parent=root, c2.parent=c1, …
# Uses task_chain.set_parent so chain_root + audit are populated.
make_chain() {
  local ws="$1"; shift
  local prev="$1"; shift
  make_task "$ws" "$prev"
  local cur
  for cur in "$@"; do
    make_task "$ws" "$cur"
    PYTHONPATH="$M10_LIB_DIR" WS="$ws" CHILD="$cur" PARENT="$prev" python3 - <<'PY'
import os, task_chain as tc
tc.set_parent(os.environ["WS"], os.environ["CHILD"], os.environ["PARENT"])
PY
    prev="$cur"
  done
}

# tc_audit_count <ws> <outcome>
# Echoes the number of audit-log lines whose "outcome" equals <outcome>.
tc_audit_count() {
  local ws="$1" outcome="$2"
  local log="$ws/$M10_AUDIT_LOG_REL"
  if [ ! -f "$log" ]; then
    echo 0
    return 0
  fi
  jq -c --arg o "$outcome" 'select(.outcome==$o)' "$log" | wc -l | tr -d ' '
}

# assert_audit <ws> <outcome> — non-zero count for that outcome.
assert_audit() {
  local ws="$1" outcome="$2"
  local n
  n=$(tc_audit_count "$ws" "$outcome")
  [ "$n" -gt 0 ] || {
    echo "expected at least one audit line with outcome=$outcome" >&2
    [ -f "$ws/$M10_AUDIT_LOG_REL" ] && cat "$ws/$M10_AUDIT_LOG_REL" >&2
    return 1
  }
}

# tc_state_field <ws> <task_id> <jq-key>
tc_state_field() {
  local ws="$1" tid="$2" key="$3"
  jq -r ".${key}" "$ws/.codenook/tasks/$tid/state.json"
}

# make_task_with_brief <ws> <task_id> <title> <summary> [status]
# Like make_task but sets title + summary (the "brief" surface used by
# parent_suggester to build candidate token sets).
make_task_with_brief() {
  local ws="$1" tid="$2" title="$3" summary="$4" status="${5:-in_progress}"
  local dir="$ws/.codenook/tasks/$tid"
  mkdir -p "$dir/outputs"
  WS_DIR="$dir" TID="$tid" TITLE="$title" SUMMARY="$summary" STATUS="$status" \
    python3 - <<'PY'
import json, os
state = {
    "schema_version": 1,
    "task_id": os.environ["TID"],
    "title": os.environ["TITLE"],
    "summary": os.environ["SUMMARY"],
    "plugin": "development",
    "phase": "design",
    "iteration": 0,
    "max_iterations": 5,
    "status": os.environ["STATUS"],
    "history": [],
}
with open(os.path.join(os.environ["WS_DIR"], "state.json"), "w") as f:
    json.dump(state, f, indent=2)
PY
}

# seed_draft_config <ws> <tid> <plugin> <input> [parent_id]
# Writes a minimal-valid draft-config.yaml under the task dir. When
# parent_id is supplied (non-empty) it is rendered verbatim; pass the
# string "null" to seed the explicit-null UX (TC-M10.3-03).
seed_draft_config() {
  local ws="$1" tid="$2" plugin="$3" input="$4" parent="${5:-}"
  local dir="$ws/.codenook/tasks/$tid"
  mkdir -p "$dir"
  {
    echo "_draft: true"
    echo "plugin: \"$plugin\""
    echo "input: \"$input\""
    if [ -n "$parent" ]; then
      if [ "$parent" = "null" ]; then
        echo "parent_id: null"
      else
        echo "parent_id: \"$parent\""
      fi
    fi
  } >"$dir/draft-config.yaml"
}

# render_prompt_path <ws> <tid> — echo the path to the rendered prompt.
render_prompt_path() {
  echo "$1/.codenook/tasks/$2/.router-prompt.md"
}

# seed_mock_llm <mock_dir> <call_name> <text>
# Drops a deterministic mock fixture for _lib/llm_call.py to consume via
# CN_LLM_MOCK_DIR. Used by M10.4 chain_summarize bats.
seed_mock_llm() {
  local mock_dir="$1" call_name="$2" text="$3"
  mkdir -p "$mock_dir"
  printf '%s' "$text" >"$mock_dir/${call_name}.txt"
}

# make_ancestor_with_briefs <ws> <tid> <title> [phase] [status] [brief]
# Like make_task_with_brief but fills the richer surface chain_summarize
# reads: state.json (title/phase/status), draft-config.yaml (input=brief).
# Caller adds design.md/decisions.md/etc. and outputs/ files separately.
make_ancestor_with_briefs() {
  local ws="$1" tid="$2" title="$3" phase="${4:-implement}" status="${5:-done}" brief="${6:-}"
  local dir="$ws/.codenook/tasks/$tid"
  mkdir -p "$dir/outputs"
  WS_DIR="$dir" TID="$tid" TITLE="$title" PHASE="$phase" STATUS="$status" python3 - <<'PY'
import json, os
state = {
    "schema_version": 1,
    "task_id": os.environ["TID"],
    "title": os.environ["TITLE"],
    "plugin": "development",
    "phase": os.environ["PHASE"],
    "iteration": 0,
    "max_iterations": 5,
    "status": os.environ["STATUS"],
    "history": [],
}
with open(os.path.join(os.environ["WS_DIR"], "state.json"), "w") as f:
    json.dump(state, f, indent=2)
PY
  if [ -n "$brief" ]; then
    cat >"$dir/draft-config.yaml" <<YAML
_draft: true
plugin: "development"
input: "$brief"
YAML
  fi
}

# m10_router_render <task_id> <ws> [extra args...]
# Invoke render_prompt.py with PYTHONPATH=$M10_LIB_DIR.
m10_router_render() {
  local tid="$1"; shift
  local ws="$1"; shift
  PYTHONPATH="$M10_LIB_DIR" python3 \
    "$CORE_ROOT/skills/builtin/router-agent/render_prompt.py" \
    --task-id "$tid" --workspace "$ws" "$@"
}
