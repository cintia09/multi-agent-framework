#!/usr/bin/env bats
# E2E-P-004 — fresh install must produce a CLAUDE.md whose installer
# bootloader block passes the marker-only linter with zero errors.

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
LINTER="$CORE_ROOT/skills/builtin/_lib/claude_md_linter.py"

@test "[v0.11.4 E2E-P-004] fresh-install bootloader block passes claude_md_linter marker-only" {
  ws="$(make_scratch)"
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1
  [ -f "$ws/CLAUDE.md" ]
  run python3 "$LINTER" --marker-only --json "$ws/CLAUDE.md"
  [ "$status" -eq 0 ] || { echo "status=$status output=$output"; return 1; }
  echo "$output" | python3 -c "
import json, sys
d=json.loads(sys.stdin.read())
assert d['errors']==[], d
"
}
