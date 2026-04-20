#!/usr/bin/env bats
# E2E-P-001 — fresh install must stamp state.json.kernel_version equal to
# the root VERSION file. Round-2 fix-pack v0.11.4.

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
ROOT_VERSION="$(cat "$REPO_ROOT/VERSION" | tr -d '[:space:]')"

setup() {
  ws="$(make_scratch)"
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1 || {
    bash "$INSTALL_SH" --plugin development "$ws"
    return 1
  }
}

@test "[v0.11.4 E2E-P-001] state.json.kernel_version equals root VERSION post-install" {
  kv="$(python3 -c "import json; print(json.load(open('$ws/.codenook/state.json'))['kernel_version'])")"
  [ "$kv" = "$ROOT_VERSION" ] || { echo "got=$kv want=$ROOT_VERSION"; return 1; }
}

@test "[v0.11.4 E2E-P-001] inner skills/codenook-core/VERSION matches root VERSION" {
  inner="$(cat "$REPO_ROOT/skills/codenook-core/VERSION" | tr -d '[:space:]')"
  [ "$inner" = "$ROOT_VERSION" ] || { echo "inner=$inner root=$ROOT_VERSION"; return 1; }
}
