#!/usr/bin/env bash
set -euo pipefail
# Before context compaction: flush current session memories
AGENTS_DIR="${CWD:-.}/.agents"

AGENT=$(cat "$AGENTS_DIR/runtime/active-agent" 2>/dev/null || echo "unknown")
DATE=$(date +%Y-%m-%d)
DIARY_DIR="$AGENTS_DIR/memory/$AGENT/diary"

mkdir -p "$DIARY_DIR"

# Append compaction marker to diary
echo "" >> "$DIARY_DIR/$DATE.md"
echo "### [$(date +%H:%M)] Pre-compaction flush" >> "$DIARY_DIR/$DATE.md"
echo "Context compaction triggered. Key items should have been captured above." >> "$DIARY_DIR/$DATE.md"

echo '{"status": "flushed"}'
