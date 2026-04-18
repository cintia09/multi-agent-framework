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
import sys
import tempfile
from typing import Any

_SCHEMA_CACHE: dict[str, dict] = {}


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


def _load_schema(schema_path: str) -> dict:
    cached = _SCHEMA_CACHE.get(schema_path)
    if cached is not None:
        return cached
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    _SCHEMA_CACHE[schema_path] = schema
    return schema


def atomic_write_json_validated(path: str, data: Any, schema_path: str) -> None:
    """Validate `data` against the JSON-Schema at `schema_path` BEFORE writing.

    On schema violation: print "schema violation: <message>" to stderr
    and exit 1. On success: write atomically (no tempfile leaks).
    Schemas are cached in-process by path.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from jsonschema_lite import validate, ValidationError  # noqa: E402

    schema = _load_schema(schema_path)
    try:
        validate(data, schema)
    except ValidationError as e:
        print(f"schema violation: {e}", file=sys.stderr)
        sys.exit(1)
    atomic_write_json(path, data)
