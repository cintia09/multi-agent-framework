#!/usr/bin/env bash
set -euo pipefail
# After memory write: update FTS5 index
bash scripts/memory-index.sh 2>/dev/null || true
echo '{"status": "ok"}'
