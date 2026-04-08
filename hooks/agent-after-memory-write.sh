#!/usr/bin/env bash
set -euo pipefail
# After memory write: update FTS5 index
# memory-index.sh lives in the framework repo scripts/ or project .agents/scripts/
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f ".agents/scripts/memory-index.sh" ]; then
  bash .agents/scripts/memory-index.sh 2>/dev/null || true
elif [ -f "scripts/memory-index.sh" ]; then
  bash scripts/memory-index.sh 2>/dev/null || true
fi
echo '{"status": "ok"}'
