#!/usr/bin/env bats
# E2E-P-007 — dispatch and HITL events are tee'd into per-task audit.jsonl
# in addition to the global history files.

load helpers/load
load helpers/assertions

EMIT_SH="$CORE_ROOT/skills/builtin/dispatch-audit/emit.sh"
HITL_SH="$CORE_ROOT/skills/builtin/hitl-adapter/terminal.sh"

setup() {
  ws="$(make_scratch)"
  mkdir -p "$ws/.codenook"
}

@test "[v0.11.4 E2E-P-007] dispatch-audit tees into per-task audit.jsonl" {
  payload='{"task":"T-AUD1","phase":"clarify","iteration":0}'
  run bash "$EMIT_SH" --role clarifier --payload "$payload" --workspace "$ws"
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/tasks/T-AUD1/audit.jsonl" ]
  [ -f "$ws/.codenook/history/dispatch.jsonl" ]
  grep -q '"role": "clarifier"' "$ws/.codenook/tasks/T-AUD1/audit.jsonl"
}

@test "[v0.11.4 E2E-P-007] hitl decide tees into per-task audit.jsonl" {
  mkdir -p "$ws/.codenook/hitl-queue"
  cat >"$ws/.codenook/hitl-queue/T-AUD2-design_signoff.json" <<'EOF'
{
  "id": "T-AUD2-design_signoff",
  "task_id": "T-AUD2",
  "plugin": "development",
  "gate": "design_signoff",
  "context_path": ".codenook/tasks/T-AUD2/state.json",
  "verdict_at_gate": "ok",
  "created_at": "2025-01-01T00:00:00Z",
  "decision": null,
  "decided_at": null,
  "reviewer": null,
  "comment": null
}
EOF
  mkdir -p "$ws/.codenook/tasks/T-AUD2"
  cp "$ws/.codenook/hitl-queue/T-AUD2-design_signoff.json" \
     "$ws/.codenook/tasks/T-AUD2/state.json"
  run bash "$HITL_SH" decide --id T-AUD2-design_signoff --decision approve \
       --reviewer alice --workspace "$ws"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ -f "$ws/.codenook/tasks/T-AUD2/audit.jsonl" ]
  grep -q '"decision":"approve"' "$ws/.codenook/tasks/T-AUD2/audit.jsonl"
}
