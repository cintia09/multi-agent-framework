# queue-runner — Generic FIFO queue on .codenook/queues/<name>.jsonl

**Role**: Provides FIFO queue operations with file-based locking for concurrency.

**Exit codes**:
- 0: success
- 1: empty queue (dequeue/peek only)
- 2: usage error

**Subcommands**:
```bash
queue.sh enqueue --queue <name> --payload <json> [--workspace <dir>]
queue.sh dequeue --queue <name> [--workspace <dir>]
queue.sh peek --queue <name> [--workspace <dir>]
queue.sh list --queue <name> [--filter <jq-expr>] [--workspace <dir>]
queue.sh size --queue <name> [--workspace <dir>]
```

**Storage**: `.codenook/queues/<name>.jsonl`

**Concurrency**: Uses Python fcntl for file locking (macOS/Linux compatible).

**Behavior**:
- `enqueue`: Appends JSON object to queue file
- `dequeue`: Removes and returns head (FIFO)
- `peek`: Returns head without removing
- `list`: Emits all entries as JSONL (optionally filtered by jq expr)
- `size`: Returns integer count

→ Design basis: architecture-v6.md §3.2.6 (queue / hitl-queue)
