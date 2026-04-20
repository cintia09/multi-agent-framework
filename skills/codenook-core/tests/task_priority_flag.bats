#!/usr/bin/env bats
# E2E-P-008 — `codenook task new --priority` records priority on state.json.

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"

setup() {
  ws="$(make_scratch)"
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1
}

@test "[v0.11.4 E2E-P-008] task new --priority P1 stamps priority" {
  tid="$("$ws/.codenook/bin/codenook" task new --title "P" \
        --accept-defaults --priority P1)"
  v="$(python3 -c "import json; print(json.load(open('$ws/.codenook/tasks/$tid/state.json'))['priority'])")"
  [ "$v" = "P1" ]
}

@test "[v0.11.4 E2E-P-008] task new defaults priority to P2" {
  tid="$("$ws/.codenook/bin/codenook" task new --title "P" --accept-defaults)"
  v="$(python3 -c "import json; print(json.load(open('$ws/.codenook/tasks/$tid/state.json'))['priority'])")"
  [ "$v" = "P2" ]
}

@test "[v0.11.4 E2E-P-008] task new rejects invalid priority" {
  run "$ws/.codenook/bin/codenook" task new --title "P" --accept-defaults --priority X
  [ "$status" -eq 2 ]
}
