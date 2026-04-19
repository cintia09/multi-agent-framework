"""Read/write helpers for tasks/<tid>/draft-config.yaml.

The draft-config is the evolving task config the router-agent maintains
across turns; it carries a `_draft: true` sentinel until the user
confirms, at which point `freeze_to_state_json` strips the sentinels
and reshapes the payload into a state.json seed acceptable to the
M4 orchestrator-tick state.json schema.

See docs/v6/router-agent-v6.md §4.2 + §8.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from atomic import atomic_write_json  # noqa: F401,E402  (re-exported)

SCHEMA_PATH = (
    _HERE.parent
    / "router-agent"
    / "schemas"
    / "draft-config.yaml.schema.yaml"
)

_REQUIRED_KEYS = ("_draft", "plugin", "input")
_VALID_TIERS = ("tier_strong", "tier_balanced", "tier_cheap")
_VALID_ROLES = (
    "implementer",
    "reviewer",
    "planner",
    "designer",
    "tester",
    "acceptor",
    "validator",
    "distiller",
    "clarifier",
)
_VALID_ACCEPT = ("required", "optional", "skip")
_M4_STATE_VERSION = 1
_M4_DEFAULT_MAX_ITERATIONS = 8


def _validate(cfg: dict) -> None:
    if not isinstance(cfg, dict):
        raise ValueError("draft-config must be a YAML mapping")
    for k in _REQUIRED_KEYS:
        if k not in cfg:
            raise ValueError(f"draft-config missing required key: {k!r}")
    if cfg["_draft"] is not True:
        raise ValueError("_draft must be exactly True")
    if not isinstance(cfg["plugin"], str) or not cfg["plugin"]:
        raise ValueError("plugin must be a non-empty string")
    if not isinstance(cfg["input"], str) or not cfg["input"]:
        raise ValueError("input must be a non-empty string")

    if "max_iterations" in cfg:
        mi = cfg["max_iterations"]
        if isinstance(mi, bool) or not isinstance(mi, int) or mi < 1:
            raise ValueError(f"max_iterations must be int >= 1, got {mi!r}")

    if "dual_mode" in cfg and not isinstance(cfg["dual_mode"], bool):
        raise ValueError("dual_mode must be boolean")

    models = cfg.get("models")
    if models is not None:
        if not isinstance(models, dict):
            raise ValueError("models must be a mapping")
        for role, val in models.items():
            if role == "router":
                raise ValueError("models.router is not allowed (decision #37)")
            if role not in _VALID_ROLES:
                raise ValueError(f"models.{role} unknown role")
            if val not in _VALID_TIERS:
                raise ValueError(
                    f"models.{role} {val!r} not in {list(_VALID_TIERS)}"
                )

    hitl = cfg.get("hitl_overrides")
    if hitl is not None:
        if not isinstance(hitl, dict):
            raise ValueError("hitl_overrides must be a mapping")
        if "accept" in hitl and hitl["accept"] not in _VALID_ACCEPT:
            raise ValueError(
                f"hitl_overrides.accept {hitl['accept']!r} "
                f"not in {list(_VALID_ACCEPT)}"
            )

    if "custom" in cfg and not isinstance(cfg["custom"], dict):
        raise ValueError("custom must be a mapping")


def _atomic_write_text(path: Path, text: str) -> None:
    d = path.parent
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".draft-", suffix=".tmp")
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


def read_draft(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("draft-config top-level must be a mapping")
    _validate(data)
    return data


def write_draft(path: Path, config: dict) -> None:
    cfg = dict(config)
    cfg["_draft"] = True  # invariant — always set, regardless of caller
    _validate(cfg)
    text = yaml.safe_dump(
        cfg,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    _atomic_write_text(Path(path), text)


def freeze_to_state_json(
    draft: dict,
    *,
    plugin: str,
    task_id: str,
    now: str | None = None,
) -> dict:
    """Pure transform. Strips `_draft*` keys, reshapes the remaining
    fields into a state.json seed that satisfies the M4
    schemas/task-state.schema.json contract.

    Non-state-schema fields (input, models, hitl_overrides, custom) are
    parked under `config_overrides`, which is the only schema-permitted
    object container for arbitrary task configuration.
    """
    if not isinstance(draft, dict):
        raise TypeError("draft must be a dict")
    if not plugin:
        raise ValueError("plugin must be supplied")
    if not task_id:
        raise ValueError("task_id must be supplied")

    overrides: dict[str, Any] = {}
    state: dict[str, Any] = {
        "schema_version": _M4_STATE_VERSION,
        "task_id": task_id,
        "plugin": plugin,
        "phase": None,
        "iteration": 0,
        "max_iterations": int(draft.get("max_iterations") or _M4_DEFAULT_MAX_ITERATIONS),
        "status": "pending",
        "history": [],
    }

    if "target_dir" in draft and draft["target_dir"]:
        state["target_dir"] = draft["target_dir"]
    if "dual_mode" in draft:
        state["dual_mode"] = "parallel" if draft["dual_mode"] else "serial"

    for k in ("input", "models", "hitl_overrides", "custom"):
        if k in draft and draft[k] is not None:
            overrides[k] = draft[k]
    if overrides:
        state["config_overrides"] = overrides

    if now:
        state["created_at"] = now

    return state


__all__ = [
    "read_draft",
    "write_draft",
    "freeze_to_state_json",
    "SCHEMA_PATH",
]
