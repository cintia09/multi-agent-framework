#!/usr/bin/env bash
set -euo pipefail
# Cron Scheduler - checks jobs.json and executes due tasks
# Usage: bash scripts/cron-scheduler.sh [--check] [--run]
# Designed to be called from external cron: */5 * * * * cd /path/to/project && bash scripts/cron-scheduler.sh --run

AGENTS_DIR=".agents"
JOBS_FILE="$AGENTS_DIR/jobs.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

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
    JOBS_FILE="$JOBS_FILE" python3 -c "
import json, os
with open(os.environ['JOBS_FILE']) as f:
    jobs = json.load(f)
for j in jobs['jobs']:
    status = '✅' if j.get('enabled', True) else '❌'
    print(f'  {status} {j[\"id\"]}: {j[\"schedule\"]} → {j[\"action\"]}')
    print(f'     {j.get(\"description\", \"\")}')
"
    ;;
  --run)
    # Execute due jobs (simplified - checks action type)
    JOBS_FILE="$JOBS_FILE" PROJECT_DIR="$PROJECT_DIR" python3 -c "
import json, subprocess, sys, os
jobs_file = os.environ['JOBS_FILE']
project_dir = os.environ['PROJECT_DIR']
with open(jobs_file) as f:
    jobs = json.load(f)
for j in jobs['jobs']:
    if not j.get('enabled', True):
        continue
    action = j['action']
    if action == 'check-staleness':
        subprocess.run(['bash', f'{project_dir}/hooks/agent-staleness-check.sh'], capture_output=True)
    elif action == 'index-memory':
        subprocess.run(['bash', f'{project_dir}/scripts/memory-index.sh'], capture_output=True)
    elif action == 'generate-report':
        import pathlib
        tb_path = pathlib.Path(project_dir) / '.agents' / 'task-board.json'
        if tb_path.exists():
            board = json.load(open(tb_path))
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
