#!/usr/bin/env bats
# M4.U2 — orchestrator-tick FULL state-machine algorithm (impl-v6 §3.3).
#
# All M4-mode tasks set state.plugin=<id>; the M1 tests use the legacy
# stub schema (no state.plugin) which the tick keeps supporting for
# backward compatibility — that path is exercised by m1-orchestrator-tick.

load helpers/load
load helpers/assertions

TICK_SH="$CORE_ROOT/skills/builtin/orchestrator-tick/tick.sh"

# ── Workspace seeding helpers ───────────────────────────────────────────
mk_ws_with_plugin() {
  local ws; ws="$(make_scratch)"
  mkdir -p "$ws/.codenook/tasks" "$ws/.codenook/queue" \
           "$ws/.codenook/hitl-queue" "$ws/.codenook/history" \
           "$ws/.codenook/memory/_pending" "$ws/.codenook/plugins"
  cp -R "$FIXTURES_ROOT/m4/plugins/generic" "$ws/.codenook/plugins/generic"
  echo "$ws"
}

# Replace one phase's spec by piping a YAML mutation through python+yaml.
patch_phases() {
  local ws="$1" payload="$2"
  python3 - "$ws/.codenook/plugins/generic/phases.yaml" "$payload" <<'PY'
import sys, yaml
path, payload = sys.argv[1], sys.argv[2]
with open(path) as f: doc = yaml.safe_load(f)
overlay = yaml.safe_load(payload)
doc["phases"] = overlay["phases"]
with open(path, "w") as f: yaml.safe_dump(doc, f, sort_keys=False)
PY
}

mk_state() {
  local ws="$1" tid="$2" extra="${3:-}"
  local tdir="$ws/.codenook/tasks/$tid"
  mkdir -p "$tdir/outputs"
  python3 - "$tdir/state.json" "$tid" "$extra" <<'PY'
import json, sys
out, tid, extra = sys.argv[1], sys.argv[2], sys.argv[3]
state = {
  "schema_version": 1,
  "task_id": tid,
  "plugin": "generic",
  "phase": None,
  "iteration": 0,
  "max_iterations": 3,
  "dual_mode": "serial",
  "status": "in_progress",
  "config_overrides": {},
  "history": [],
}
if extra:
    state.update(json.loads(extra))
with open(out, "w") as f: json.dump(state, f, indent=2)
PY
}

# Write expected_output for a phase with a verdict frontmatter.
write_output() {
  local ws="$1" tid="$2" relpath="$3" verdict="$4"
  local out="$ws/.codenook/tasks/$tid/$relpath"
  mkdir -p "$(dirname "$out")"
  cat >"$out" <<EOF
---
verdict: $verdict
---
test output for $tid
EOF
}

# ── Tests ───────────────────────────────────────────────────────────────
@test "phase=null first dispatch: phase advances to first, in_flight set, dispatch.jsonl appended" {
  ws="$(mk_ws_with_plugin)"; mk_state "$ws" "T-101"
  run_with_stderr "\"$TICK_SH\" --task T-101 --workspace \"$ws\""
  [ "$status" -eq 0 ]
  jq -e '.phase=="clarify"' "$ws/.codenook/tasks/T-101/state.json" >/dev/null
  jq -e '.in_flight_agent.role=="clarifier"' "$ws/.codenook/tasks/T-101/state.json" >/dev/null
  jq -e '.in_flight_agent.expected_output=="outputs/phase-1-clarifier.md"' \
        "$ws/.codenook/tasks/T-101/state.json" >/dev/null
  [ -f "$ws/.codenook/history/dispatch.jsonl" ]
  [ "$(wc -l <"$ws/.codenook/history/dispatch.jsonl" | tr -d ' ')" -ge 1 ]
}

@test "in_flight present + output not ready → status=waiting (no state mutation)" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-102" '{"phase":"clarify","in_flight_agent":{"agent_id":"ag_x","role":"clarifier","dispatched_at":"2026-01-01T00:00:00Z","expected_output":"outputs/phase-1-clarifier.md"}}'
  before=$(cat "$ws/.codenook/tasks/T-102/state.json")
  run bash -c "\"$TICK_SH\" --task T-102 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.status=="waiting"' >/dev/null
  after=$(cat "$ws/.codenook/tasks/T-102/state.json")
  [ "$before" = "$after" ]
}

@test "output ready + verdict=ok → advance to next phase, dispatch new role" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-103" '{"phase":"clarify","in_flight_agent":{"agent_id":"ag_x","role":"clarifier","dispatched_at":"2026-01-01T00:00:00Z","expected_output":"outputs/phase-1-clarifier.md"}}'
  write_output "$ws" "T-103" "outputs/phase-1-clarifier.md" "ok"

  run bash -c "\"$TICK_SH\" --task T-103 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  jq -e '.phase=="analyze"' "$ws/.codenook/tasks/T-103/state.json" >/dev/null
  jq -e '.in_flight_agent.role=="analyzer"' "$ws/.codenook/tasks/T-103/state.json" >/dev/null
  jq -e '.history|length==1 and .[0].verdict=="ok"' \
        "$ws/.codenook/tasks/T-103/state.json" >/dev/null
}

@test "post_validate hook missing → recorded as _warning and continue" {
  ws="$(mk_ws_with_plugin)"
  patch_phases "$ws" 'phases:
- {id: clarify, role: clarifier, produces: outputs/phase-1-clarifier.md, post_validate: missing-script.sh}
- {id: analyze, role: analyzer, produces: outputs/phase-2-analyzer.md}'
  mk_state "$ws" "T-104" '{"phase":"clarify","in_flight_agent":{"agent_id":"a","role":"clarifier","dispatched_at":"x","expected_output":"outputs/phase-1-clarifier.md"}}'
  write_output "$ws" "T-104" "outputs/phase-1-clarifier.md" "ok"

  run bash -c "\"$TICK_SH\" --task T-104 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  jq -e '.history[0]._warning|test("post_validate")' \
        "$ws/.codenook/tasks/T-104/state.json" >/dev/null
}

@test "HITL gate (phase.gate truthy) → writes hitl-queue entry + status=waiting" {
  ws="$(mk_ws_with_plugin)"
  patch_phases "$ws" 'phases:
- {id: clarify, role: clarifier, produces: outputs/phase-1-clarifier.md, gate: design_signoff}
- {id: analyze, role: analyzer, produces: outputs/phase-2-analyzer.md}'
  mk_state "$ws" "T-105" '{"phase":"clarify","in_flight_agent":{"agent_id":"a","role":"clarifier","dispatched_at":"x","expected_output":"outputs/phase-1-clarifier.md"}}'
  write_output "$ws" "T-105" "outputs/phase-1-clarifier.md" "ok"

  run bash -c "\"$TICK_SH\" --task T-105 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.status=="waiting"' >/dev/null
  [ -f "$ws/.codenook/hitl-queue/T-105-design_signoff.json" ]
  jq -e '.gate=="design_signoff" and .decision==null' \
        "$ws/.codenook/hitl-queue/T-105-design_signoff.json" >/dev/null
}

@test "transition next=='complete' → status=done + distiller pending marker" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-106" '{"phase":"analyze","in_flight_agent":{"agent_id":"a","role":"analyzer","dispatched_at":"x","expected_output":"outputs/phase-2-analyzer.md"}}'
  write_output "$ws" "T-106" "outputs/phase-2-analyzer.md" "ok"

  run bash -c "\"$TICK_SH\" --task T-106 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.status=="done"' >/dev/null
  jq -e '.status=="done"' "$ws/.codenook/tasks/T-106/state.json" >/dev/null
  [ -f "$ws/.codenook/memory/_pending/T-106.json" ]
}

@test "iteration self-loop on needs_revision; max_iterations exceeded → blocked" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-107" '{"phase":"clarify","iteration":3,"max_iterations":3,"in_flight_agent":{"agent_id":"a","role":"clarifier","dispatched_at":"x","expected_output":"outputs/phase-1-clarifier.md"}}'
  write_output "$ws" "T-107" "outputs/phase-1-clarifier.md" "needs_revision"

  run bash -c "\"$TICK_SH\" --task T-107 --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  jq -e '.status=="blocked"' "$ws/.codenook/tasks/T-107/state.json" >/dev/null
}

@test "entry-questions missing → blocked + message_for_user" {
  ws="$(mk_ws_with_plugin)"
  cat >"$ws/.codenook/plugins/generic/entry-questions.yaml" <<EOF
clarify:
  required:
    - target_dir
EOF
  mk_state "$ws" "T-108"
  run bash -c "\"$TICK_SH\" --task T-108 --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  echo "$output" | jq -e '.status=="blocked"' >/dev/null
  echo "$output" | jq -e '.message_for_user|test("target_dir")' >/dev/null
}

@test "fanout: phase.allows_fanout + state.decomposed=true → child tasks with proper IDs" {
  ws="$(mk_ws_with_plugin)"
  patch_phases "$ws" 'phases:
- {id: clarify, role: clarifier, produces: outputs/phase-1-clarifier.md, allows_fanout: true}
- {id: analyze, role: analyzer, produces: outputs/phase-2-analyzer.md}'
  mk_state "$ws" "T-109" '{"decomposed":true,"subtasks":["unit-a","unit-b"]}'
  run bash -c "\"$TICK_SH\" --task T-109 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  [ -d "$ws/.codenook/tasks/T-109-c1" ]
  [ -d "$ws/.codenook/tasks/T-109-c2" ]
  jq -e '.task_id=="T-109-c1"' "$ws/.codenook/tasks/T-109-c1/state.json" >/dev/null
  [ -f "$ws/.codenook/queue/T-109-c1.json" ]
}

@test "dual_mode=parallel + dual_mode_compatible → in_flight_agent.agent_id is array of N" {
  ws="$(mk_ws_with_plugin)"
  patch_phases "$ws" 'phases:
- {id: clarify, role: clarifier, produces: outputs/phase-1-clarifier.md, dual_mode_compatible: true}
- {id: analyze, role: analyzer, produces: outputs/phase-2-analyzer.md}'
  mk_state "$ws" "T-110" '{"dual_mode":"parallel","config_overrides":{"dual_mode":"parallel","parallel_n":3}}'
  run bash -c "\"$TICK_SH\" --task T-110 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  jq -e '.in_flight_agent.agent_id|type=="array" and length==3' \
     "$ws/.codenook/tasks/T-110/state.json" >/dev/null
}

@test "recovery: phase set + no in_flight → re-dispatch with _warning in history" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-111" '{"phase":"clarify"}'
  run bash -c "\"$TICK_SH\" --task T-111 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  jq -e '.in_flight_agent.role=="clarifier"' "$ws/.codenook/tasks/T-111/state.json" >/dev/null
  jq -e '[.history[]._warning] | map(select(. != null)) | any(test("recover|re-dispatch"))' \
     "$ws/.codenook/tasks/T-111/state.json" >/dev/null
}

@test "terminal status (done/cancelled/error) → noop" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-112" '{"status":"done","phase":"analyze"}'
  before=$(cat "$ws/.codenook/tasks/T-112/state.json")
  run bash -c "\"$TICK_SH\" --task T-112 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.status=="done" and .next_action=="noop"' >/dev/null
  after=$(cat "$ws/.codenook/tasks/T-112/state.json")
  [ "$before" = "$after" ]
}

@test "summary output is valid JSON ≤500 bytes" {
  ws="$(mk_ws_with_plugin)"; mk_state "$ws" "T-113"
  run bash -c "\"$TICK_SH\" --task T-113 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq . >/dev/null
  [ "$(echo -n "$output" | wc -c)" -le 500 ]
}

# ── Fix #6: fanout requires non-empty subtasks ──────────────────────────
@test "fanout: decomposed=true + empty subtasks → blocked (no fabricated children)" {
  ws="$(mk_ws_with_plugin)"
  patch_phases "$ws" 'phases:
- {id: clarify, role: clarifier, produces: outputs/phase-1-clarifier.md, allows_fanout: true}
- {id: analyze, role: analyzer, produces: outputs/phase-2-analyzer.md}'
  mk_state "$ws" "T-114" '{"decomposed":true,"subtasks":[]}'
  run bash -c "\"$TICK_SH\" --task T-114 --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  echo "$output" | jq -e '.status=="blocked"' >/dev/null
  echo "$output" | jq -e '.next_action | test("subtasks")' >/dev/null
  # No fabricated children seeded:
  [ ! -d "$ws/.codenook/tasks/T-114-c1" ]
}

# ── Fix #7: emit_summary loop fits CJK message_for_user ─────────────────
@test "emit_summary loop: large CJK message_for_user fits ≤500 bytes valid JSON" {
  ws="$(mk_ws_with_plugin)"
  python3 -c "
import yaml
spec={'clarify':{'required':['这是一个非常非常非常非常非常长的中文键名用于测试字节预算的执行算法','另一个长键名用于扩展输出大小','还有一个长键名增加预算压力','再来一个测试键名用于扩展输出','最后一个长键名彻底压垮预算限制']}}
open('$ws/.codenook/plugins/generic/entry-questions.yaml','w').write(yaml.safe_dump(spec, allow_unicode=True))
"
  mk_state "$ws" "T-131"
  run bash -c "\"$TICK_SH\" --task T-131 --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  bytes=$(echo -n "$output" | wc -c | tr -d ' ')
  [ "$bytes" -le 500 ]
  # Result must be valid JSON (no broken UTF-8).
  echo "$output" | python3 -c "import json,sys; json.loads(sys.stdin.read())"
}

# ── Fix #8: schema validation on state.json writes ──────────────────────
@test "schema validation: state.json with extra unknown field → reject on persist" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-130"
  python3 -c "
import json,sys
p='$ws/.codenook/tasks/T-130/state.json'
d=json.load(open(p))
d['rogue_field']=42
json.dump(d, open(p,'w'))
"
  run_with_stderr "\"$TICK_SH\" --task T-130 --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "schema violation"
}
