"""Atomic JSON write helper, shared by builtin skills that mutate
state.json (orchestrator-tick, task-config-set, …).

Why:
  A naive open(path, 'w') + json.dump truncates the destination first;
  if the process is interrupted between truncate and the final write
  (signal, OOM, container kill) the workspace is left with an empty or
  half-written state.json — fatal for a state-machine driver.

Strategy:
  Write to a sibling tempfile in the same directory (so os.replace is a
  same-filesystem rename, which is atomic on POSIX), fsync, then
  os.replace the temp over the destination. On failure the temp is
  unlinked.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any


def atomic_write_json(path: str, data: Any) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
