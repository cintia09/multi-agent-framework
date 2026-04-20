#!/usr/bin/env bats
# E2E-P-005 — codenook task set --help exits 0.

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"

setup() {
  ws="$(make_scratch)"
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1
}

@test "[v0.11.4 E2E-P-005] codenook task set --help exits 0" {
  run "$ws/.codenook/bin/codenook" task set --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"--field"* ]]
  [[ "$output" == *"dual_mode"* ]]
  [[ "$output" == *"target_dir"* ]]
}

@test "[v0.11.4 E2E-P-005] task set --field dual_mode mutates state.json" {
  tid="$("$ws/.codenook/bin/codenook" task new --title "x" --accept-defaults)"
  run "$ws/.codenook/bin/codenook" task set --task "$tid" \
        --field dual_mode --value parallel
  [ "$status" -eq 0 ]
  v="$(python3 -c "import json; print(json.load(open('$ws/.codenook/tasks/$tid/state.json'))['dual_mode'])")"
  [ "$v" = "parallel" ]
}

@test "[v0.11.4 E2E-P-005] task set rejects invalid field" {
  tid="$("$ws/.codenook/bin/codenook" task new --title "x" --accept-defaults)"
  run "$ws/.codenook/bin/codenook" task set --task "$tid" \
        --field random_field --value oops
  [ "$status" -eq 2 ]
}
