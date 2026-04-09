#!/usr/bin/env bash
set -euo pipefail
# After memory write: update FTS5 index
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
AGENTS_DIR="$CWD/.agents"
if [ -f "$AGENTS_DIR/scripts/memory-index.sh" ]; then
  bash "$AGENTS_DIR/scripts/memory-index.sh" 2>/dev/null || true
elif [ -f "scripts/memory-index.sh" ]; then
  bash scripts/memory-index.sh 2>/dev/null || true
fi
echo '{"status": "ok"}'
