#!/usr/bin/env bats
# M9.7 — plugin read-only enforcement.
# Spec: docs/v6/memory-and-extraction-v6.md §2.1, §9
# Cases: docs/v6/m9-test-cases.md TC-M9.7-01, TC-M9.7-02, TC-M9.7-03, TC-M9.7-07

load helpers/load
load helpers/assertions
load helpers/m9_memory

CHECKER="$CORE_ROOT/skills/builtin/_lib/plugin_readonly.py"
LIB_DIR="$CORE_ROOT/skills/builtin/_lib"
FIXTURES_DIR="$TESTS_ROOT/fixtures/m9-plugin-readonly"

@test "[m9.7] checker script is present and executable" {
  assert_file_exists "$CHECKER"
  assert_file_executable "$CHECKER"
}

@test "[m9.7] TC-M9.7-01 readonly scan clean (repo-wide)" {
  # Scan the actual repo; expect zero writes_to_plugins.
  run python3 "$CHECKER" --target "$CORE_ROOT/skills/builtin" --json
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  echo "$output" | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
assert d["scanned_files"] > 0, d
assert d["writes_to_plugins"] == [], d
'
}

@test "[m9.7] TC-M9.7-02 detects open w on plugins" {
  run_with_stderr "python3 '$CHECKER' --target '$FIXTURES_DIR' --json"
  [ "$status" -ne 0 ] || { echo "stdout: $output"; echo "stderr: $STDERR"; return 1; }
  assert_contains "$output" "bad_open_w.py"
  assert_contains "$output" "bad_path_write.py"
  assert_not_contains "$output" "clean.py"
}

@test "[m9.7] TC-M9.7-02 violation report includes line numbers" {
  run python3 "$CHECKER" --target "$FIXTURES_DIR" --json
  [ "$status" -ne 0 ]
  echo "$output" | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
hits = d["writes_to_plugins"]
assert len(hits) >= 2, hits
for h in hits:
    assert "line" in h and h["line"] > 0, h
    assert "file" in h, h
'
}

@test "[m9.7] TC-M9.7-03 runtime guard raises PluginReadOnlyViolation" {
  ws="$(make_scratch)"
  m9_init_memory "$ws" >/dev/null
  mkdir -p "$ws/plugins"
  run_with_stderr "PYTHONPATH='$LIB_DIR' WS='$ws' python3 -c '
import os, sys
import plugin_readonly as pr
ws = os.environ[\"WS\"]
try:
    pr.assert_writable_path(os.path.join(ws, \"plugins\", \"foo.txt\"), workspace_root=ws)
except pr.PluginReadOnlyViolation as e:
    print(\"BLOCKED:\" + str(e))
    sys.exit(0)
sys.exit(2)
'"
  [ "$status" -eq 0 ] || { echo "stdout: $output"; echo "stderr: $STDERR"; return 1; }
  assert_contains "$output" "BLOCKED:"
}

@test "[m9.7] TC-M9.7-03 PluginReadOnlyViolation is a PermissionError" {
  run python3 -c "
import sys; sys.path.insert(0, '$LIB_DIR')
import plugin_readonly as pr
assert issubclass(pr.PluginReadOnlyViolation, PermissionError)
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
}

@test "[m9.7] TC-M9.7-03 memory_layer write helpers reject plugins/ target" {
  ws="$(make_scratch)"
  m9_init_memory "$ws" >/dev/null
  mkdir -p "$ws/plugins"
  # Force _atomic_write_text to a plugins/ destination — must raise.
  run_with_stderr "PYTHONPATH='$LIB_DIR' WS='$ws' python3 -c '
import os, sys
import memory_layer as ml
import plugin_readonly as pr
target = os.path.join(os.environ[\"WS\"], \"plugins\", \"evil.md\")
from pathlib import Path
try:
    ml._atomic_write_text(Path(target), \"nope\")
except pr.PluginReadOnlyViolation:
    print(\"OK\"); sys.exit(0)
sys.exit(2)
'"
  [ "$status" -eq 0 ] || { echo "stdout: $output"; echo "stderr: $STDERR"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.7] TC-M9.7-03 violation emits audit record" {
  ws="$(make_scratch)"
  m9_init_memory "$ws" >/dev/null
  mkdir -p "$ws/plugins"
  run_with_stderr "PYTHONPATH='$LIB_DIR' WS='$ws' python3 -c '
import os, sys
import plugin_readonly as pr
ws = os.environ[\"WS\"]
try:
    pr.assert_writable_path(os.path.join(ws, \"plugins\", \"foo.txt\"), workspace_root=ws, asset_type=\"knowledge\")
except pr.PluginReadOnlyViolation:
    pass
'"
  [ "$status" -eq 0 ]
  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  [ -f "$log" ] || { echo "audit log missing"; ls "$ws/.codenook/memory/history/"; return 1; }
  assert_contains "$(cat "$log")" "plugin_readonly_violation"
  assert_contains "$(cat "$log")" "rejected"
}

@test "[m9.7] TC-M9.7-03 writes outside plugins/ are unaffected" {
  ws="$(make_scratch)"
  m9_init_memory "$ws" >/dev/null
  m9_write_knowledge "$ws" "alpha" "summary text" "tag1" "body content"
  [ -f "$ws/.codenook/memory/knowledge/alpha.md" ]
}

@test "[m9.7] TC-M9.7-07 secret scanner fail close" {
  # Build a private skill+lib copy with secret_scan.py removed; running
  # the knowledge extractor must exit non-zero with the canonical message.
  ws="$(make_scratch)"
  m9_init_memory "$ws" >/dev/null
  priv_root="$ws/private"
  mkdir -p "$priv_root/skills/builtin/_lib" "$priv_root/skills/builtin/knowledge-extractor"
  cp "$LIB_DIR"/*.py "$priv_root/skills/builtin/_lib/"
  rm "$priv_root/skills/builtin/_lib/secret_scan.py"
  cp "$CORE_ROOT/skills/builtin/knowledge-extractor"/*.py "$priv_root/skills/builtin/knowledge-extractor/" 2>/dev/null || true
  cp "$CORE_ROOT/skills/builtin/knowledge-extractor"/*.sh "$priv_root/skills/builtin/knowledge-extractor/" 2>/dev/null || true
  # Provide minimal task input file (extractor reads it but bails out before LLM).
  in="$ws/in.md"
  printf 'hello\n' > "$in"
  run_with_stderr "python3 '$priv_root/skills/builtin/knowledge-extractor/extract.py' --task-id T-001 --workspace '$ws' --phase done --reason test --input '$in'"
  [ "$status" -ne 0 ] || { echo "stdout: $output"; echo "stderr: $STDERR"; return 1; }
  assert_contains "$STDERR" "secret scanner unavailable; refusing to write"
}
