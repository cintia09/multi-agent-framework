#!/usr/bin/env bash
set -euo pipefail
# Cron Scheduler - checks jobs.json and executes due tasks
# Usage: bash scripts/cron-scheduler.sh [--check] [--run]
# Designed to be called from external cron: */5 * * * * cd /path/to/project && bash scripts/cron-scheduler.sh --run

AGENTS_DIR=".agents"
JOBS_FILE="$AGENTS_DIR/jobs.json"

if [ ! -f "$JOBS_FILE" ]; then
  echo "⚠️ No jobs.json found. Creating default..."
  cat > "$JOBS_FILE" << 'EOF'
{
  "jobs": [
    {
      "id": "staleness-check",
      "schedule": "*/30 * * * *",
      "action": "check-staleness",
      "enabled": true,
      "description": "Check stale tasks and auto-wake corresponding agent"
    },
    {
      "id": "daily-summary",
      "schedule": "0 9 * * *",
      "action": "generate-report",
      "enabled": true,
      "description": "Generate daily project progress summary"
    },
    {
      "id": "memory-index",
      "schedule": "0 */2 * * *",
      "action": "index-memory",
      "enabled": true,
      "description": "Rebuild memory FTS5 index every 2 hours"
    }
  ]
}
EOF
fi

case "${1:-}" in
  --check)
    echo "📋 Scheduled Jobs:"
    python3 -c "
import json
with open('$JOBS_FILE') as f:
    jobs = json.load(f)
for j in jobs['jobs']:
    status = '✅' if j.get('enabled', True) else '❌'
    print(f'  {status} {j[\"id\"]}: {j[\"schedule\"]} → {j[\"action\"]}')
    print(f'     {j.get(\"description\", \"\")}')
"
    ;;
  --run)
    # Execute due jobs (simplified - checks action type)
    python3 -c "
import json, subprocess, sys
with open('$JOBS_FILE') as f:
    jobs = json.load(f)
for j in jobs['jobs']:
    if not j.get('enabled', True):
        continue
    action = j['action']
    if action == 'check-staleness':
        subprocess.run(['bash', 'hooks/agent-staleness-check.sh'], capture_output=True)
    elif action == 'index-memory':
        subprocess.run(['bash', 'scripts/memory-index.sh'], capture_output=True)
    elif action == 'generate-report':
        # Generate simple report
        board = json.load(open('.agents/task-board.json'))
        total = len(board['tasks'])
        accepted = sum(1 for t in board['tasks'] if t['status'] == 'accepted')
        implementing = sum(1 for t in board['tasks'] if t['status'] == 'implementing')
        print(f'📊 Daily Report: {accepted}/{total} accepted, {implementing} in progress')
"
    ;;
  *)
    echo "Usage: $0 [--check|--run]"
    ;;
esac
