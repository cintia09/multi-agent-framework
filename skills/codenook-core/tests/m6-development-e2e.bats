#!/usr/bin/env bats
# M6 U10 — DoD: 8-phase E2E loop with mocked role outputs (impl-v6 §M6.4).
#
# Mirrors the spec's "install -> 50-tick loop -> done" line:
#   1. Install plugins/development/ into a fresh workspace.
#   2. Create T-001 with phase=null + plugin=development.
#   3. For up to 50 iterations: run tick.sh; whenever the orchestrator
#      blocks waiting for a role output, write a mocked verdict:ok
#      output; whenever it opens an HITL gate, run hitl-adapter decide
#      approve.
#   4. Assert state.json.status == "done" and history covers all 8 phases.
#
# The "diff against v5 baseline" half of the DoD line is documented as a
# known gap (see plugins/development/README.md "Known gaps").

load helpers/load
load helpers/assertions

PLUGIN_SRC="$CORE_ROOT/../../plugins/development"
INSTALL_SH="$CORE_ROOT/skills/builtin/install-orchestrator/orchestrator.sh"
TICK_SH="$CORE_ROOT/skills/builtin/orchestrator-tick/tick.sh"
HITL_SH="$CORE_ROOT/skills/builtin/hitl-adapter/terminal.sh"

setup_ws_with_plugin() {
  local ws; ws="$(make_scratch)"
  mkdir -p "$ws/.codenook"
  local dist; dist="$(make_scratch)/dist"
  mkdir -p "$dist"
  ( cd "$PLUGIN_SRC/.." && tar -czf "$dist/dev.tar.gz" development )
  "$INSTALL_SH" --src "$dist/dev.tar.gz" --workspace "$ws" --json >/dev/null
  echo "$ws"
}

create_task() {
  local ws="$1" tid="$2"
  local d="$ws/.codenook/tasks/$tid"
  mkdir -p "$d/outputs" "$d/prompts"
  cat >"$d/state.json" <<EOF
{
  "schema_version": 1,
  "task_id": "$tid",
  "title": "M6 DoD task",
  "plugin": "development",
  "phase": null,
  "iteration": 0,
  "max_iterations": 3,
  "dual_mode": "serial",
  "target_dir": "$ws/work",
  "status": "in_progress",
  "config_overrides": {},
  "history": []
}
EOF
  mkdir -p "$ws/work"
  cat >"$ws/.codenook/state.json" <<EOF
{"active_tasks":["$tid"],"current_focus":"$tid"}
EOF
}

write_role_output() {
  local ws="$1" tid="$2" expected="$3"
  local out="$ws/.codenook/tasks/$tid/$expected"
  mkdir -p "$(dirname "$out")"
  cat >"$out" <<'EOF'
---
verdict: ok
summary: mock verdict
---
mocked role body
EOF
}

@test "M6 DoD: install + 8-phase loop drives task to done within 50 ticks" {
  ws="$(setup_ws_with_plugin)"
  create_task "$ws" "T-001"

  local i=0 status_code finished=0
  for i in $(seq 1 50); do
    set +e
    out=$("$TICK_SH" --task T-001 --workspace "$ws" --json)
    status_code=$?
    set -e
    # E2E-P-009: contract is 0=advanced/done, 2=entry-q, 3=hitl, 1=error.
    case "$status_code" in
      0|3) : ;;
      *) echo "tick failed (i=$i, rc=$status_code): $out" >&2; return 1 ;;
    esac

    tick_status=$(echo "$out" | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')

    if [ "$tick_status" = "done" ]; then
      finished=1
      break
    fi

    if [ "$tick_status" = "blocked" ]; then
      echo "blocked at i=$i: $out" >&2
      return 1
    fi
    if [ "$tick_status" = "error" ]; then
      echo "error at i=$i: $out" >&2
      return 1
    fi

    # If the orchestrator is waiting for a role output, materialise it.
    expected=$(jq -r '.in_flight_agent.expected_output // empty' \
               "$ws/.codenook/tasks/T-001/state.json")
    if [ -n "$expected" ]; then
      out_file="$ws/.codenook/tasks/T-001/$expected"
      if [ ! -f "$out_file" ]; then
        write_role_output "$ws" "T-001" "$expected"
        continue
      fi
    fi

    # If the orchestrator is waiting for an HITL gate, approve it.
    if [ "$tick_status" = "waiting" ]; then
      cur_phase=$(jq -r '.phase' "$ws/.codenook/tasks/T-001/state.json")
      gate=$(python3 - "$ws" "$cur_phase" <<'PY'
import sys, yaml
ws, phase = sys.argv[1], sys.argv[2]
phases = yaml.safe_load(open(f"{ws}/.codenook/plugins/development/phases.yaml"))["phases"]
ph = next((p for p in phases if p["id"] == phase), None)
print(ph.get("gate", "") if ph else "")
PY
)
      if [ -n "$gate" ]; then
        eid="T-001-$gate"
        if [ -f "$ws/.codenook/hitl-queue/$eid.json" ]; then
          "$HITL_SH" decide --workspace "$ws" --id "$eid" \
            --decision approve --reviewer human \
            --comment "M6 e2e auto-approve" >/dev/null
        fi
      fi
    fi
  done

  [ "$finished" = "1" ] || {
    echo "did not finish within 50 ticks" >&2
    cat "$ws/.codenook/tasks/T-001/state.json" >&2
    return 1
  }

  jq -e '.status == "done"' "$ws/.codenook/tasks/T-001/state.json" >/dev/null

  # All 8 distinct phases must appear in history (ignoring HITL warnings).
  python3 - "$ws/.codenook/tasks/T-001/state.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1]))
phases_seen = {h["phase"] for h in state["history"]
               if h.get("verdict") == "ok"}
expected = {"clarify","design","plan","implement","test","accept","validate","ship"}
missing = expected - phases_seen
assert not missing, f"phases never observed verdict=ok: {missing}"
print("ok")
PY
}
