#!/usr/bin/env bash
set -euo pipefail
# Before context compaction: flush current session memories
# Ensures key decisions are preserved before summarization

AGENT=$(cat .agents/runtime/active-agent 2>/dev/null || echo "unknown")
DATE=$(date +%Y-%m-%d)
DIARY_DIR=".agents/memory/$AGENT/diary"

mkdir -p "$DIARY_DIR"

# Append compaction marker to diary
echo "" >> "$DIARY_DIR/$DATE.md"
echo "### [$(date +%H:%M)] Pre-compaction flush" >> "$DIARY_DIR/$DATE.md"
echo "Context compaction triggered. Key items should have been captured above." >> "$DIARY_DIR/$DATE.md"

echo '{"status": "flushed"}'
