#!/usr/bin/env python3
"""queue-runner/_queue.py — FIFO queue operations with file locking"""
import fcntl
import json
import os
import subprocess
import sys

def main():
    subcmd = os.environ["CN_SUBCMD"]
    queue = os.environ["CN_QUEUE"]
    payload = os.environ.get("CN_PAYLOAD", "")
    filter_expr = os.environ.get("CN_FILTER", "")
    workspace = os.environ["CN_WORKSPACE"]
    
    queue_dir = os.path.join(workspace, ".codenook/queues")
    os.makedirs(queue_dir, exist_ok=True)
    
    queue_file = os.path.join(queue_dir, f"{queue}.jsonl")
    
    if subcmd == "enqueue":
        enqueue(queue_file, payload)
    elif subcmd == "dequeue":
        dequeue(queue_file)
    elif subcmd == "peek":
        peek(queue_file)
    elif subcmd == "list":
        list_queue(queue_file, filter_expr)
    elif subcmd == "size":
        size(queue_file)
    else:
        print(f"queue.sh: unknown subcommand: {subcmd}", file=sys.stderr)
        sys.exit(2)

def enqueue(queue_file, payload):
    """Append entry to queue"""
    # Validate JSON
    try:
        entry = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"queue.sh: invalid JSON payload: {e}", file=sys.stderr)
        sys.exit(2)
    
    # Lock and append
    with open(queue_file, 'a') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    sys.exit(0)

def dequeue(queue_file):
    """Remove and return head"""
    if not os.path.exists(queue_file):
        sys.exit(1)  # Empty
    
    with open(queue_file, 'r+') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            lines = f.readlines()
            if not lines:
                sys.exit(1)  # Empty
            
            head = lines[0]
            # Write back remaining lines
            f.seek(0)
            f.truncate()
            f.writelines(lines[1:])
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    # Parse and output
    entry = json.loads(head.strip())
    print(json.dumps(entry, ensure_ascii=False))
    sys.exit(0)

def peek(queue_file):
    """Return head without removing"""
    if not os.path.exists(queue_file):
        sys.exit(1)  # Empty
    
    with open(queue_file, 'r') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            line = f.readline()
            if not line:
                sys.exit(1)  # Empty
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    entry = json.loads(line.strip())
    print(json.dumps(entry, ensure_ascii=False))
    sys.exit(0)

def list_queue(queue_file, filter_expr):
    """List all entries (optionally filtered)"""
    if not os.path.exists(queue_file):
        sys.exit(0)  # Empty is ok for list
    
    with open(queue_file, 'r') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            lines = f.readlines()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Apply filter if provided
        if filter_expr:
            try:
                # Use jq to filter
                result = subprocess.run(
                    ['jq', '-e', filter_expr],
                    input=line,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    continue  # Doesn't match filter
            except:
                continue
        
        print(line)
    
    sys.exit(0)

def size(queue_file):
    """Return count of entries"""
    if not os.path.exists(queue_file):
        print("0")
        sys.exit(0)
    
    with open(queue_file, 'r') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            lines = [l for l in f.readlines() if l.strip()]
            count = len(lines)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    print(count)
    sys.exit(0)

if __name__ == "__main__":
    main()
