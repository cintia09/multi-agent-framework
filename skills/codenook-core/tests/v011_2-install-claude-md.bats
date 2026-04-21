#!/usr/bin/env bats
# v0.11.2 — DR-002 / DR-006 integration tests for install.sh.
# Verifies: positional workspace path, idempotent CLAUDE.md augmentation.

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
SYNC_PY="$CORE_ROOT/skills/builtin/_lib/claude_md_sync.py"

@test "[v0.11.2] DR-002 install.sh accepts positional workspace path (--dry-run)" {
  scratch="$(make_scratch)"
  run bash "$INSTALL_SH" --dry-run "$scratch"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [[ "$output" == *"DRY-RUN"* ]]
}

@test "[v0.11.2] DR-002 install.sh --help prints usage" {
  run bash "$INSTALL_SH" --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"workspace_path"* ]]
}

@test "[v0.11.2] DR-002 install.sh rejects unknown option" {
  run bash "$INSTALL_SH" --no-such-flag
  [ "$status" -eq 2 ]
}

@test "[v0.11.2] DR-006 claude_md_sync creates CLAUDE.md when missing" {
  scratch="$(make_scratch)"
  run python3 "$SYNC_PY" --workspace "$scratch" --version 0.11.2 --plugin development
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ -f "$scratch/CLAUDE.md" ]
  grep -q "codenook:begin" "$scratch/CLAUDE.md"
  grep -q "codenook:end" "$scratch/CLAUDE.md"
  grep -q "v0.11.2" "$scratch/CLAUDE.md"
}

@test "[v0.11.2] DR-006 claude_md_sync appends block to existing CLAUDE.md" {
  scratch="$(make_scratch)"
  cat > "$scratch/CLAUDE.md" <<'MD'
# My Project

This is my own content. Do not touch.
MD
  run python3 "$SYNC_PY" --workspace "$scratch" --version 0.11.2 --plugin development
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  grep -q "My Project" "$scratch/CLAUDE.md"
  grep -q "Do not touch" "$scratch/CLAUDE.md"
  grep -q "codenook:begin" "$scratch/CLAUDE.md"
}

@test "[v0.11.2] DR-006 claude_md_sync is idempotent (second run = zero diff)" {
  scratch="$(make_scratch)"
  cat > "$scratch/CLAUDE.md" <<'MD'
# My Project

User content here.
MD
  python3 "$SYNC_PY" --workspace "$scratch" --version 0.11.2 --plugin development
  cp "$scratch/CLAUDE.md" "$scratch/CLAUDE.md.snap"
  python3 "$SYNC_PY" --workspace "$scratch" --version 0.11.2 --plugin development
  run diff "$scratch/CLAUDE.md.snap" "$scratch/CLAUDE.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
}

@test "[v0.11.2] DR-006 claude_md_sync replaces block on version bump" {
  scratch="$(make_scratch)"
  python3 "$SYNC_PY" --workspace "$scratch" --version 0.11.1 --plugin development
  python3 "$SYNC_PY" --workspace "$scratch" --version 0.99.0 --plugin development
  ! grep -q "v0.11.1" "$scratch/CLAUDE.md"
  grep -q "v0.99.0" "$scratch/CLAUDE.md"
}

@test "[v0.11.2] DR-006 claude_md_sync preserves user content outside markers" {
  scratch="$(make_scratch)"
  cat > "$scratch/CLAUDE.md" <<'MD'
# Top header

para 1
MD
  python3 "$SYNC_PY" --workspace "$scratch" --version 0.11.2 --plugin development
  # add user content AFTER the codenook block
  echo "" >> "$scratch/CLAUDE.md"
  echo "## My Section After" >> "$scratch/CLAUDE.md"
  echo "user trailing content" >> "$scratch/CLAUDE.md"
  python3 "$SYNC_PY" --workspace "$scratch" --version 0.11.2 --plugin development
  grep -q "Top header" "$scratch/CLAUDE.md"
  grep -q "My Section After" "$scratch/CLAUDE.md"
  grep -q "user trailing content" "$scratch/CLAUDE.md"
}

@test "[regress] DR-006 rendered block is free of stray escape bytes (\\b, \\t, \\f, \\v, \\a)" {
  scratch="$(make_scratch)"
  python3 "$SYNC_PY" --workspace "$scratch" --version 0.27.0 --plugin development
  # Each of these control bytes would indicate an escape sequence got
  # interpreted in the rendering f-string (e.g. \b -> 0x08).
  for code in 8 9 12 11 7; do
    run python3 -c "import sys; d=open(sys.argv[1],'rb').read(); sys.exit(0 if all(b!=int(sys.argv[2]) for b in d) else 1)" "$scratch/CLAUDE.md" "$code"
    [ "$status" -eq 0 ] || { echo "stray control byte $code present in rendered CLAUDE.md"; return 1; }
  done
  # Windows path must be intact (the original \b bug ate the 'b' in 'bin').
  grep -F "\\.codenook\\bin\\codenook.cmd" "$scratch/CLAUDE.md"
}

@test "[regress] DR-006 multi-line shell snippets keep their backslash continuations" {
  scratch="$(make_scratch)"
  python3 "$SYNC_PY" --workspace "$scratch" --version 0.27.0 --plugin development
  # task new should render across at least 4 continuation lines, not collapse to one
  run grep -c '^[[:space:]]*--' "$scratch/CLAUDE.md"
  [ "$status" -eq 0 ]
  [ "$output" -ge 4 ] || { echo "expected >=4 indented --flag lines, got $output"; return 1; }
}

@test "[regress] DR-006 plugin list reflects state.json when present" {
  scratch="$(make_scratch)"
  mkdir -p "$scratch/.codenook"
  cat > "$scratch/.codenook/state.json" <<'JSON'
{
  "schema_version": "v1",
  "kernel_version": "0.27.0",
  "installed_plugins": [
    {"id": "development", "version": "0.2.0"},
    {"id": "writing",     "version": "0.1.1"}
  ]
}
JSON
  python3 "$SYNC_PY" --workspace "$scratch" --version 0.27.0 --plugin writing
  grep -q "Workspace has plugins installed:" "$scratch/CLAUDE.md"
  grep -q "\\*\\*development\\*\\*" "$scratch/CLAUDE.md"
  grep -q "\\*\\*writing\\*\\*" "$scratch/CLAUDE.md"
}
