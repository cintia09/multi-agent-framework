#!/usr/bin/env python3
"""orchestrator-tick/_tick.py — task state machine tick"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from atomic import atomic_write_json  # noqa: E402

PREFLIGHT_SH = None
DISPATCH_AUDIT_SH = None

def main():
    global PREFLIGHT_SH, DISPATCH_AUDIT_SH
    
    task = os.environ["CN_TASK"]
    state_file = os.environ["CN_STATE_FILE"]
    workspace = os.environ["CN_WORKSPACE"]
    dry_run = os.environ.get("CN_DRY_RUN", "0") == "1"
    dispatch_cmd = os.environ.get("CN_DISPATCH_CMD", "")
    
    # Find skills
    core_root = find_core_root()
    PREFLIGHT_SH = os.path.join(core_root, "skills/builtin/preflight/preflight.sh")
    DISPATCH_AUDIT_SH = os.path.join(core_root, "skills/builtin/dispatch-audit/emit.sh")
    
    # Load state
    with open(state_file, 'r') as f:
        state = json.load(f)
    
    phase = state.get("phase", "")
    iteration = state.get("iteration", 0)
    total_iterations = state.get("total_iterations", 0)
    
    # Check terminal phase
    if phase == "done":
        print("tick.sh: task at terminal phase 'done'", file=sys.stderr)
        sys.exit(3)
    
    # Check iteration limit
    if iteration >= total_iterations:
        print(f"tick.sh: iteration limit reached ({iteration}/{total_iterations})", file=sys.stderr)
        log_entry(state, "preflight", "blocked: iteration limit")
        if not dry_run:
            save_state(state_file, state)
        sys.exit(1)
    
    # Run preflight
    result = subprocess.run(
        [PREFLIGHT_SH, "--task", task, "--workspace", workspace, "--json"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        # Preflight failed
        reasons = []
        try:
            preflight_out = json.loads(result.stdout)
            reasons = preflight_out.get("reasons", [])
        except:
            pass
        
        log_entry(state, "preflight", f"blocked: {', '.join(reasons) if reasons else 'failed'}")
        if not dry_run:
            save_state(state_file, state)
        
        for line in result.stderr.strip().split('\n'):
            if line:
                print(line, file=sys.stderr)
        
        sys.exit(1)
    
    if dry_run:
        print("tick.sh: dry-run mode, not dispatching", file=sys.stderr)
        sys.exit(0)
    
    # Build dispatch payload (stub for now - real impl would include phase/task details)
    payload = build_dispatch_payload(state)
    
    # Call dispatch-audit
    if os.path.exists(DISPATCH_AUDIT_SH):
        subprocess.run(
            [DISPATCH_AUDIT_SH, "--role", "executor", "--payload", payload, "--workspace", workspace],
            check=False
        )
    
    # Invoke dispatch command
    success = dispatch(dispatch_cmd, payload, workspace)
    
    if not success:
        print("tick.sh: dispatch failed", file=sys.stderr)
        log_entry(state, "dispatch", "failed")
        save_state(state_file, state)
        sys.exit(1)
    
    # Update state on success
    state["iteration"] = iteration + 1
    log_entry(state, "dispatch", "success")
    save_state(state_file, state)
    
    sys.exit(0)

def find_core_root():
    """Find the core root directory"""
    # Walk up from this script's location
    current = os.path.dirname(os.path.abspath(__file__))
    while current != "/":
        if os.path.exists(os.path.join(current, "skills", "builtin", "preflight")):
            return current
        current = os.path.dirname(current)
    
    # Fallback: use environment or guess
    return os.environ.get("CORE_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(current))))

def build_dispatch_payload(state):
    """Build dispatch payload (≤500 chars)"""
    # Minimal payload for now
    payload = {
        "task": state["task_id"],
        "phase": state["phase"],
        "iteration": state["iteration"]
    }
    
    s = json.dumps(payload, ensure_ascii=False)
    if len(s) > 500:
        # Truncate if needed (shouldn't happen with this minimal payload)
        s = s[:497] + "..."
    
    return s

def dispatch(dispatch_cmd, payload, workspace):
    """Invoke dispatch command"""
    if not dispatch_cmd:
        # Use internal stub
        return dispatch_stub(payload)
    
    # Create temp file for summary
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        summary_file = f.name
    
    try:
        env = os.environ.copy()
        env["CODENOOK_DISPATCH_PAYLOAD"] = payload
        env["CODENOOK_DISPATCH_SUMMARY"] = summary_file
        
        result = subprocess.run(
            [dispatch_cmd],
            env=env,
            capture_output=True,
            text=True
        )
        
        return result.returncode == 0
    finally:
        if os.path.exists(summary_file):
            os.unlink(summary_file)

def dispatch_stub(payload):
    """Internal stub dispatch - always succeeds"""
    return True

def log_entry(state, action, result):
    """Append entry to tick_log"""
    if "tick_log" not in state:
        state["tick_log"] = []
    
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "action": action,
        "result": result
    }
    state["tick_log"].append(entry)

def save_state(state_file, state):
    """Write state back to file atomically (crash-safe; see _lib/atomic.py)."""
    atomic_write_json(state_file, state)

if __name__ == "__main__":
    main()
