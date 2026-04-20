#!/usr/bin/env bats
# E2E-P-001 — re-install (idempotent path) must also stamp the correct
# kernel_version. v0.11.4 round-2.

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
ROOT_VERSION="$(cat "$REPO_ROOT/VERSION" | tr -d '[:space:]')"

@test "[v0.11.4 E2E-P-001] re-install keeps kernel_version aligned with VERSION" {
  ws="$(make_scratch)"
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1
  kv="$(python3 -c "import json; print(json.load(open('$ws/.codenook/state.json'))['kernel_version'])")"
  [ "$kv" = "$ROOT_VERSION" ] || { echo "got=$kv want=$ROOT_VERSION"; return 1; }
}
