#!/usr/bin/env python3
"""session-resume/_resume.py — session state summary logic"""
import json
import os
import sys
from pathlib import Path

def main():
    workspace = os.environ["CN_WORKSPACE"]
    json_out = os.environ.get("CN_JSON", "0") == "1"
    
    tasks_dir = os.path.join(workspace, ".codenook/tasks")
    hitl_queue = os.path.join(workspace, ".codenook/queues/hitl.jsonl")
    
    # Scan for tasks
    tasks = []
    if os.path.exists(tasks_dir):
        for task_dir in Path(tasks_dir).iterdir():
            if not task_dir.is_dir():
                continue
            
            state_file = task_dir / "state.json"
            if not state_file.exists():
                continue
            
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                
                # Skip terminal tasks
                if state.get("phase") == "done":
                    continue
                
                tasks.append(state)
            except Exception as e:
                print(f"resume.sh: warning: skipping corrupt {state_file}: {e}", file=sys.stderr)
    
    # Sort by updated_at (most recent first)
    tasks.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    
    # Check HITL queue
    hitl_pending = False
    if os.path.exists(hitl_queue):
        try:
            with open(hitl_queue, 'r') as f:
                for line in f:
                    entry = json.loads(line.strip())
                    if entry.get("status") == "pending":
                        hitl_pending = True
                        break
        except:
            pass
    
    # Build result
    if tasks:
        active = tasks[0]
        result = {
            "active_task": active.get("task_id"),
            "phase": active.get("phase"),
            "iteration": active.get("iteration", 0),
            "total_iterations": active.get("total_iterations", 0),
            "last_action_ts": active.get("updated_at", "unknown"),
            "hitl_pending": hitl_pending,
            "next_suggested_action": suggest_action(active, hitl_pending),
            "summary": build_summary(active, hitl_pending)
        }
    else:
        result = {
            "active_task": None,
            "phase": None,
            "iteration": 0,
            "total_iterations": 0,
            "last_action_ts": None,
            "hitl_pending": hitl_pending,
            "next_suggested_action": "create new task",
            "summary": "No active tasks"
        }
    
    # Output
    if json_out:
        output = json.dumps(result, ensure_ascii=False)
        # Ensure ≤1KB
        if len(output) > 1024:
            # Truncate summary field
            result["summary"] = result["summary"][:100] + "..."
            output = json.dumps(result, ensure_ascii=False)
        print(output)
    else:
        print(result["summary"])
    
    sys.exit(0)

def suggest_action(task, hitl_pending):
    """Suggest next action based on task state"""
    if hitl_pending:
        return "resolve HITL gate"
    
    phase = task.get("phase", "")
    iteration = task.get("iteration", 0)
    total = task.get("total_iterations", 0)
    
    if iteration >= total:
        return "increase iteration limit or mark done"
    
    return f"continue tick (phase: {phase})"

def build_summary(task, hitl_pending):
    """Build human-readable summary"""
    tid = task.get("task_id", "unknown")
    phase = task.get("phase", "unknown")
    iteration = task.get("iteration", 0)
    total = task.get("total_iterations", 0)
    
    parts = [f"Task {tid} at {phase} phase, iteration {iteration}/{total}"]
    
    if hitl_pending:
        parts.append("HITL gate pending")
    
    return "; ".join(parts)

if __name__ == "__main__":
    main()
