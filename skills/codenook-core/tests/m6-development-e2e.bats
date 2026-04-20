#!/usr/bin/env bats
# m6-development-e2e.bats — v0.2.0 end-to-end smoke for the default
# (`feature`) profile.
#
# Drives a fresh workspace through install → 80 ticks, mocking each
# role output as `verdict: ok` and auto-approving every HITL gate.
# Asserts state.json.status == "done" and that every phase in the
# `feature` profile chain appears in history with verdict=ok.
#
# Other profiles are exercised in m2-profiles.bats (and m3-tick-profiles
# for tick's profile resolution unit-tests).

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
  "title": "M6 v0.2.0 DoD task",
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

# Mock role output. Clarifier outputs include `task_type: feature` so
# the orchestrator selects the `feature` profile.
write_role_output() {
  local ws="$1" tid="$2" expected="$3"
  local out="$ws/.codenook/tasks/$tid/$expected"
  mkdir -p "$(dirname "$out")"
  if [[ "$expected" == *clarifier* ]]; then
    cat >"$out" <<'EOF'
---
verdict: ok
task_type: feature
summary: mock clarifier
---
mocked clarifier body
EOF
  else
    cat >"$out" <<'EOF'
---
verdict: ok
summary: mock verdict
---
mocked role body
EOF
  fi
}

@test "M6 DoD v0.2.0: install + feature-profile loop drives task to done within 80 ticks" {
  ws="$(setup_ws_with_plugin)"
  create_task "$ws" "T-001"

  local i=0 status_code finished=0
  for i in $(seq 1 80); do
    out=""
    status_code=0
    if ! out=$("$TICK_SH" --task T-001 --workspace "$ws" --json 2>/dev/null); then
      status_code=$?
    fi
    if [ -z "$out" ]; then
      echo "tick produced no JSON (i=$i, rc=$status_code)" >&2; return 1
    fi
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

    expected=$(jq -r '.in_flight_agent.expected_output // empty' \
               "$ws/.codenook/tasks/T-001/state.json")
    if [ -n "$expected" ]; then
      out_file="$ws/.codenook/tasks/T-001/$expected"
      if [ ! -f "$out_file" ]; then
        write_role_output "$ws" "T-001" "$expected"
        continue
      fi
    fi

    if [ "$tick_status" = "waiting" ]; then
      cur_phase=$(jq -r '.phase' "$ws/.codenook/tasks/T-001/state.json")
      gate=$(python3 - "$ws" "$cur_phase" <<'PY'
import sys, yaml
ws, phase = sys.argv[1], sys.argv[2]
phases = yaml.safe_load(open(f"{ws}/.codenook/plugins/development/phases.yaml"))["phases"]
ph = phases.get(phase) if isinstance(phases, dict) else next((p for p in phases if p["id"] == phase), None)
print((ph or {}).get("gate", ""))
PY
)
      if [ -n "$gate" ]; then
        eid="T-001-$gate"
        if [ -f "$ws/.codenook/hitl-queue/$eid.json" ]; then
          "$HITL_SH" decide --workspace "$ws" --id "$eid" \
            --decision approve --reviewer human \
            --comment "M6 v0.2.0 e2e auto-approve" >/dev/null
        fi
      fi
    fi
  done

  [ "$finished" = "1" ] || {
    echo "did not finish within 80 ticks" >&2
    cat "$ws/.codenook/tasks/T-001/state.json" >&2
    return 1
  }

  jq -e '.status == "done"' "$ws/.codenook/tasks/T-001/state.json" >/dev/null || {
    cat "$ws/.codenook/tasks/T-001/state.json" >&2; return 1; }

  # Every phase in the `feature` chain must appear in history with
  # verdict=ok at least once.
  python3 - "$ws/.codenook/tasks/T-001/state.json" \
           "$ws/.codenook/plugins/development/phases.yaml" <<'PY'
import json, sys, yaml
state = json.load(open(sys.argv[1]))
profs = yaml.safe_load(open(sys.argv[2]))["profiles"]
chain = profs["feature"]["phases"] if isinstance(profs["feature"], dict) else profs["feature"]
phases_seen = {h["phase"] for h in state["history"] if h.get("verdict") == "ok"}
missing = set(chain) - phases_seen
assert not missing, f"phases never observed verdict=ok: {missing}"
assert state.get("profile") == "feature", state.get("profile")
print("ok")
PY
}
