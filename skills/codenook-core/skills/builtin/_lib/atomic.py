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


def atomic_write_text(path: str, text: str) -> None:
    """Atomic counterpart of ``atomic_write_json`` for arbitrary text.

    Used by callers that hand-roll markdown / YAML rewrites
    (memory_doctor, knowledge promotion, …) so an interrupted write
    cannot leave a half-truncated file behind. Writes to a sibling
    tempfile, fsyncs, then ``os.replace``s atomically on POSIX.
    """
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".text-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class SchemaViolation(RuntimeError):
    """Raised by ``atomic_write_json_validated`` on schema mismatch.

    Replaces the v0.29.5-and-earlier ``sys.exit(1)`` exit so the
    library never tears down a caller that holds task_lock; the caller
    can catch this, release locks, then propagate or recover.
    """


def atomic_write_json_validated(path: str, data: Any, schema_path: str) -> None:
    """Validate `data` against the JSON-Schema at `schema_path` BEFORE writing.

    On schema violation: raises :class:`SchemaViolation` so the calling
    process can release locks and recover, instead of the previous
    behaviour of calling ``sys.exit(1)`` from library code (which killed
    the caller mid-tick under task_lock with no cleanup chance).
    On success: writes atomically (no tempfile leaks).
    Schemas are cached in-process by path.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from jsonschema_lite import validate, ValidationError  # noqa: E402

    schema = _load_schema(schema_path)
    try:
        validate(data, schema)
    except ValidationError as e:
        # Print the user-facing message exactly as v0.29.5 did so the
        # operator-visible UX is unchanged, then RAISE instead of
        # sys.exit(1). With an exception, any task_lock / fcntl /
        # context-manager up the call stack runs __exit__ and releases
        # cleanly. The CLI's top-level handler still maps an unhandled
        # exception to exit code 1.
        print(f"schema violation: {e}", file=sys.stderr)
        raise SchemaViolation(f"schema violation: {e}") from e
    atomic_write_json(path, data)
