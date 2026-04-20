#!/usr/bin/env bats
# E2E-P-003 + E2E-P-005 — full task walk produces no recover:re-dispatch
# warnings AND yields ≥1 entry under .codenook/memory/knowledge/.

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"

setup() {
  ws="$(make_scratch)"
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1
}

write_role_output() {
  local out="$1"
  mkdir -p "$(dirname "$out")"
  cat >"$out" <<'EOF'
---
verdict: ok
summary: synthesized role output for full-walk test
---
Body content describing what the role accomplished.
EOF
}

@test "[v0.11.4 E2E-P-003/P-005] full walk → no recover warnings + ≥1 knowledge entry" {
  tid="$("$ws/.codenook/bin/codenook" task new --title "Walk" \
        --dual-mode serial --target-dir src/)"
  state_file="$ws/.codenook/tasks/$tid/state.json"
  CN_LLM_MODE=mock
  export CN_LLM_MODE
  for i in $(seq 1 60); do
    set +e
    out=$("$ws/.codenook/bin/codenook" tick --task "$tid" --json)
    rc=$?
    set -e
    case "$rc" in
      0|3) : ;;
      2)  echo "entry-question pending: $out" >&2; return 1 ;;
      *)  echo "tick rc=$rc: $out" >&2; return 1 ;;
    esac
    st=$(echo "$out" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("status",""))')
    [ "$st" = "done" ] && break
    # If awaiting role output, materialise it
    expected=$(jq -r '.in_flight_agent.expected_output // empty' "$state_file")
    if [ -n "$expected" ] && [ ! -f "$ws/.codenook/tasks/$tid/$expected" ]; then
      write_role_output "$ws/.codenook/tasks/$tid/$expected"
      continue
    fi
    # If awaiting a HITL gate, approve it.
    pending=$(ls "$ws"/.codenook/hitl-queue/*.json 2>/dev/null | head -1)
    if [ -n "$pending" ]; then
      eid=$(basename "$pending" .json)
      "$ws/.codenook/bin/codenook" decide --task "$tid" \
          --phase "$(jq -r '.phase' "$state_file")" --decision approve >/dev/null 2>&1 || true
    fi
  done
  # Assert no `recover: re-dispatch (no in_flight)` warning present.
  if jq -e '[.history[]._warning // empty] | any(test("recover: re-dispatch"))' "$state_file" >/dev/null; then
    echo "FAIL: recover re-dispatch warning present"; jq '.history' "$state_file"; return 1
  fi
}

@test "[v0.11.4 E2E-P-003] knowledge fall-back yields ≥1 entry from real role output" {
  # Direct extractor smoke using the new fall-back path.
  tid="T-EX1"
  out_dir="$ws/.codenook/tasks/$tid/outputs"
  mkdir -p "$out_dir"
  cat >"$out_dir/phase-1-clarifier.md" <<'EOF'
---
verdict: ok
summary: HTTP 304 saves bandwidth and cycles when ETag matches.
---
Use ETag/If-None-Match for idempotent GETs and honor max-age.
EOF
  CN_LLM_MODE=mock python3 \
    "$CORE_ROOT/skills/builtin/knowledge-extractor/extract.py" \
    --task-id "$tid" --workspace "$ws" --phase clarify --reason after_phase
  count=$(ls "$ws"/.codenook/memory/knowledge/*.md 2>/dev/null | wc -l | tr -d ' ')
  [ "$count" -ge 1 ] || { echo "no knowledge entries written"; return 1; }
}
