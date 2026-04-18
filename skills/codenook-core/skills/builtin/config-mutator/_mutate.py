#!/usr/bin/env python3
"""config-mutator/_mutate.py — dispatched config writer.

Inputs (env, set by mutate.sh):
  CN_PLUGIN, CN_PATH, CN_VALUE, CN_REASON, CN_ACTOR,
  CN_WORKSPACE, CN_SCOPE (workspace|task), CN_TASK,
  CN_CORE_DIR (for invoking config-resolve to read effective value).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from atomic import atomic_write_json  # noqa: E402

try:
    import yaml
except ImportError:
    print("mutate.sh: PyYAML not installed", file=sys.stderr)
    sys.exit(2)


WHITELIST = {
    "models", "hitl", "knowledge", "concurrency", "skills", "memory",
    "router", "plugins", "defaults", "secrets",
}
ACTORS = {"distiller", "user", "hitl"}
ROUTER_SENTINEL = "__router__"


def die(msg: str, code: int = 1) -> None:
    print(f"mutate.sh: {msg}", file=sys.stderr)
    sys.exit(code)


def now_iso() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def deep_set(root: dict, parts: list[str], value) -> None:
    cur = root
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def deep_get(root, parts: list[str]):
    cur = root
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def atomic_write_yaml(path: Path, data: dict) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".cfg-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=True, default_flow_style=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_target_layer_value(scope: str, plugin: str, parts: list[str],
                            ws: Path, task: str):
    """Return the current value at the *target* layer (workspace L3 or
    task L4), or None when absent. Used for noop comparison so a write
    matching a deeper-layer (L0/L1/L2) effective value is still
    persisted at the requested scope."""
    if scope == "workspace":
        cfg_path = ws / ".codenook/config.yaml"
        if not cfg_path.is_file():
            return None
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if not isinstance(cfg, dict):
            return None
        overrides = (((cfg.get("plugins") or {}).get(plugin) or {})
                     .get("overrides") or {})
        return deep_get(overrides, parts)
    if scope == "task":
        state_path = ws / ".codenook/tasks" / task / "state.json"
        if not state_path.is_file():
            return None
        with state_path.open("r", encoding="utf-8") as f:
            state = json.load(f)
        return deep_get(state.get("config_overrides") or {}, parts)
    return None


def main() -> None:
    plugin = os.environ["CN_PLUGIN"]
    path_key = os.environ["CN_PATH"]
    raw_value = os.environ["CN_VALUE"]
    value_json = os.environ.get("CN_VALUE_JSON", "0") == "1"
    if value_json:
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as e:
            die(f"--value-json: invalid JSON: {e}", 2)
    else:
        # --value: parse as JSON for type fidelity (5 → int, true → bool,
        # "5" → str "5"); fall back to the raw string on parse failure.
        try:
            value = json.loads(raw_value)
        except (json.JSONDecodeError, ValueError):
            value = raw_value
    reason = os.environ["CN_REASON"]
    actor = os.environ["CN_ACTOR"]
    ws = Path(os.environ["CN_WORKSPACE"]).resolve()
    scope = os.environ["CN_SCOPE"]
    task = os.environ.get("CN_TASK", "")
    core = Path(os.environ["CN_CORE_DIR"]).resolve()

    if actor not in ACTORS:
        die(f"actor must be one of {sorted(ACTORS)}, got {actor!r}", 2)
    if any(p.startswith("_") or ".." in p for p in path_key.split(".")):
        die("invalid path: segments cannot start with _ or contain ..", 2)

    parts = path_key.split(".")
    if not parts or not parts[0] or parts[0] not in WHITELIST:
        die(f"unknown_top_key: {parts[0] if parts else ''}", 1)

    if plugin == ROUTER_SENTINEL and path_key.startswith("models.router"):
        die("router model is invariant (decision #44)", 1)

    # Compare against the *target-layer* value so a write that happens
    # to coincide with a deeper-layer (L0/L1/L2) default still gets
    # persisted at the requested scope. Using the merged effective
    # value here would mask such writes (Bug #3).
    current = read_target_layer_value(
        scope, plugin, parts, ws, task if scope == "task" else "")
    if current == value:
        print(json.dumps({"changed": False, "path": path_key, "value": value}))
        return

    # Apply write
    if scope == "workspace":
        cfg_path = ws / ".codenook/config.yaml"
        cfg: dict = {}
        if cfg_path.is_file():
            with cfg_path.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            if not isinstance(cfg, dict):
                cfg = {}
        plugins = cfg.setdefault("plugins", {})
        pl = plugins.setdefault(plugin, {})
        overrides = pl.setdefault("overrides", {})
        deep_set(overrides, parts, value)
        atomic_write_yaml(cfg_path, cfg)
    elif scope == "task":
        state_path = ws / ".codenook/tasks" / task / "state.json"
        if not state_path.is_file():
            die(f"task state missing: {state_path}")
        with state_path.open("r", encoding="utf-8") as f:
            state = json.load(f)
        overrides = state.setdefault("config_overrides", {})
        deep_set(overrides, parts, value)
        atomic_write_json(str(state_path), state)
    else:
        die(f"unknown scope: {scope!r}", 2)

    # Audit log
    log_dir = ws / ".codenook/history"
    log_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": now_iso(),
        "plugin": plugin,
        "scope": scope,
        "task": task if scope == "task" else None,
        "path": path_key,
        "old": current,
        "new": value,
        "actor": actor,
        "reason": reason,
    }
    with (log_dir / "config-changes.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(json.dumps({"changed": True, "path": path_key, "old": current, "new": value}))


if __name__ == "__main__":
    main()
