#!/usr/bin/env bats
# M3 review fixes — router-level invariants spanning multiple sub-skills.
#
# Fix #1: tier_strong invariant — bootstrap MUST fail (exit 1) if the
# config-resolve script is missing, returns non-zero, or yields neither
# models.router nor models.default. Decision #44.

load helpers/load
load helpers/assertions

BOOT_SH="$CORE_ROOT/skills/builtin/router/bootstrap.sh"
RESOLVER="$CORE_ROOT/skills/builtin/config-resolve/resolve.sh"
M3_FX="$FIXTURES_ROOT/m3"

stage_ws() {
  local src="$1" dst
  dst="$(make_scratch)/ws"
  cp -R "$src" "$dst"
  python3 - "$dst" "$FIXTURES_ROOT/catalog/full.json" <<'PY'
import json, sys, pathlib
ws, cat = sys.argv[1:]
sf = pathlib.Path(ws, ".codenook/state.json")
data = json.loads(sf.read_text())
data["model_catalog"] = json.loads(open(cat).read())
sf.write_text(json.dumps(data, indent=2))
PY
  echo "$dst"
}

@test "fix#1: missing config-resolve resolve.sh → bootstrap exit 1 with decision #44 message" {
  ws="$(stage_ws "$M3_FX/workspaces/empty")"
  backup="${RESOLVER}.bak.$$"
  # Restore even on test failure.
  trap 'mv -f "$backup" "$RESOLVER" 2>/dev/null || true' EXIT
  mv "$RESOLVER" "$backup"
  run_with_stderr "\"$BOOT_SH\" --user-input 'hi' --workspace \"$ws\" --json"
  mv -f "$backup" "$RESOLVER"
  trap - EXIT
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "router model unresolved (decision #44 violated)"
}
