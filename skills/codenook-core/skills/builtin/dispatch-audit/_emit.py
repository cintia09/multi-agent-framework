#!/usr/bin/env python3
"""dispatch-audit emitter.

Reads env:
  CN_ROLE       sub-agent role name
  CN_PAYLOAD    raw JSON string of the dispatch payload
  CN_WORKSPACE  workspace root (directory containing .codenook/)

Writes one redacted JSONL line to <ws>/.codenook/history/dispatch.jsonl:
  { ts, role, payload_size, payload_sha256, payload_preview }

Enforces payload_size <= 500 (hard limit per architecture §3.1.7 / v6 #T-3).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

PAYLOAD_LIMIT = 500
PREVIEW_LEN = 80


def main() -> int:
    role = os.environ["CN_ROLE"]
    payload = os.environ["CN_PAYLOAD"]
    ws = Path(os.environ["CN_WORKSPACE"])

    size = len(payload)
    if size > PAYLOAD_LIMIT:
        print(f"emit.sh: payload {size} chars exceeds 500 char limit", file=sys.stderr)
        return 1

    try:
        json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"emit.sh: payload is not valid JSON: {e}", file=sys.stderr)
        return 1

    history_dir = ws / ".codenook" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    log_path = history_dir / "dispatch.jsonl"

    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "role": role,
        "payload_size": size,
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "payload_preview": payload[:PREVIEW_LEN],
    }

    # Single-line append — atomic enough at M1 for typical `write()` sizes
    # well under PIPE_BUF. No locking needed for the 1-line case.
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
