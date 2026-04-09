#!/usr/bin/env bash
set -euo pipefail
# Before context compaction: flush current session memories
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
AGENTS_DIR="$CWD/.agents"

AGENT=$(cat "$AGENTS_DIR/runtime/active-agent" 2>/dev/null || echo "unknown")
if [ "$AGENT" = "unknown" ]; then
  echo '{"status": "skipped", "reason": "no active agent"}' && exit 0
fi
# Validate agent name against allowlist
if [[ ! "$AGENT" =~ ^[a-z_-]+$ ]]; then
  echo '{"status": "skipped", "reason": "invalid agent name"}' && exit 0
fi
DATE=$(date +%Y-%m-%d)
DIARY_DIR="$AGENTS_DIR/memory/$AGENT/diary"

mkdir -p "$DIARY_DIR"

# Append compaction marker to diary
echo "" >> "$DIARY_DIR/$DATE.md"
echo "### [$(date +%H:%M)] Pre-compaction flush" >> "$DIARY_DIR/$DATE.md"
echo "Context compaction triggered. Key items should have been captured above." >> "$DIARY_DIR/$DATE.md"

echo '{"status": "flushed"}'
