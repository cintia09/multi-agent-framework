#!/usr/bin/env bats
# M2 Unit 6 — plugin-shebang-scan (G10)
#
# Contract:
#   shebang-scan.sh --src <dir> [--json]
#
# Allowlist (exact match on first line):
#   #!/bin/sh
#   #!/bin/bash
#   #!/usr/bin/env bash
#   #!/usr/bin/env python3
#
# Files are "executable" if their +x bit is set on any owner/group/other.
# Non-executable files are ignored (the path-normalize / size gates
# handle other content concerns).

load helpers/load
load helpers/assertions

GATE_SH="$CORE_ROOT/skills/builtin/plugin-shebang-scan/shebang-scan.sh"

mk_src() {
  local d
  d="$(make_scratch)/p"; mkdir -p "$d"
  printf 'id: foo\nversion: 0.1.0\n' >"$d/plugin.yaml"
  echo "$d"
}

write_exec() {
  local path="$1" content="$2"
  printf '%s\n' "$content" >"$path"
  chmod +x "$path"
}

@test "shebang-scan.sh exists and executable" {
  assert_file_exists "$GATE_SH"
  assert_file_executable "$GATE_SH"
}

@test "all allowlisted shebangs → exit 0" {
  d="$(mk_src)"
  write_exec "$d/a.sh" "#!/bin/sh"
  write_exec "$d/b.sh" "#!/bin/bash"
  write_exec "$d/c.sh" "#!/usr/bin/env bash"
  write_exec "$d/d.py" "#!/usr/bin/env python3"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "executable with perl shebang → exit 1" {
  d="$(mk_src)"
  write_exec "$d/script.pl" "#!/usr/bin/perl"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "perl"
}

@test "executable with python2 shebang → exit 1" {
  d="$(mk_src)"
  write_exec "$d/legacy.py" "#!/usr/bin/env python2"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "python2"
}

@test "executable with no shebang → exit 1" {
  d="$(mk_src)"
  write_exec "$d/noshebang" "echo hi"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "shebang"
}

@test "executable that looks like a raw binary → exit 1" {
  d="$(mk_src)"
  printf '\x7fELF\x02\x01\x00binary data' >"$d/bin"
  chmod +x "$d/bin"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
}

@test "non-executable file with bad shebang → ignored, exit 0" {
  d="$(mk_src)"
  printf '#!/usr/bin/perl\n' >"$d/notes.txt"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "extra whitespace after env bash still allowed" {
  d="$(mk_src)"
  write_exec "$d/a.sh" "#!/usr/bin/env bash"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "--json envelope on failure" {
  d="$(mk_src)"
  write_exec "$d/x" "#!/usr/bin/perl"
  run "$GATE_SH" --src "$d" --json
  [ "$status" -eq 1 ]
  echo "$output" | jq -e '.gate == "plugin-shebang-scan" and .ok == false and (.reasons | length) >= 1' >/dev/null
}
