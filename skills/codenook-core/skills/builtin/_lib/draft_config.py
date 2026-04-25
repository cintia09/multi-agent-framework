"""Read/write helpers for tasks/<tid>/draft-config.yaml.

The draft-config is the evolving task config the router-agent maintains
across turns; it carries a `_draft: true` sentinel until the user
confirms, at which point `freeze_to_state_json` strips the sentinels
and reshapes the payload into a state.json seed acceptable to the
M4 orchestrator-tick state.json schema.

See docs/router-agent.md §4.2 + §8.
"""
from __future__ import annotations

import os
import re
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
_M4_STATE_VERSION = 2
_M4_DEFAULT_MAX_ITERATIONS = 8
_TASK_ID_RE = re.compile(r"^T-[A-Za-z0-9_\u4e00-\u9fff-]+$")
_PLUGIN_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _is_safe_plugin_slug(s: str) -> bool:
    """Pass-2 P3 #7: plugin id flows into ``_sh_run`` arg arrays via
    ``post_validate`` hooks; reject anything that contains path
    separators / NUL / starts with a dot before it ever reaches state.json
    so a malformed draft cannot smuggle a relative path.
    """
    if not isinstance(s, str) or not s:
        return False
    return bool(_PLUGIN_SLUG_RE.match(s)) and ".." not in s


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

    if "parent_id" in cfg and cfg["parent_id"] is not None:
        pid = cfg["parent_id"]
        if not isinstance(pid, str) or not pid:
            raise ValueError(
                "parent_id must be a non-empty 'T-...' string or null"
            )
        if not _TASK_ID_RE.match(pid):
            raise ValueError(
                f"parent_id {pid!r} must match ^T-[A-Za-z0-9_-]+$"
            )

    sp = cfg.get("selected_plugins")
    if sp is not None:
        if not isinstance(sp, list) or not all(isinstance(x, str) for x in sp):
            raise ValueError("selected_plugins must be a list of strings")

    rc = cfg.get("role_constraints")
    if rc is not None:
        if not isinstance(rc, dict):
            raise ValueError("role_constraints must be a mapping")
        for k in rc:
            if k not in ("included", "excluded"):
                raise ValueError(f"role_constraints unknown key: {k!r}")
        for k in ("included", "excluded"):
            v = rc.get(k)
            if v is None:
                continue
            if not isinstance(v, list):
                raise ValueError(f"role_constraints.{k} must be a list")
            for item in v:
                if (not isinstance(item, dict)
                        or not isinstance(item.get("plugin"), str)
                        or not isinstance(item.get("role"), str)):
                    raise ValueError(
                        f"role_constraints.{k}[*] must be {{plugin,role}}"
                    )


def _atomic_write_text(path: Path, text: str) -> None:
    """Atomic write helper for draft-config.yaml.

    Also enforces the M9.7 plugin read-only invariant: refuses any
    target whose resolved path contains a ``plugins/`` segment. The
    workspace_root is not threaded through ``write_draft`` to keep the
    public API stable; the resolved-path heuristic in
    :func:`plugin_readonly.assert_writable_path` (with
    ``workspace_root=None``) still catches every realistic write under
    a ``plugins/`` directory.
    """
    # Lazy import — _lib has no __init__.py; plugin_readonly is on the
    # same sys.path entry that already imported draft_config.
    from plugin_readonly import assert_writable_path  # noqa: WPS433

    assert_writable_path(path, workspace_root=None)

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

    NOTE — M10.3: ``parent_id`` is intentionally NOT propagated into the
    returned state by this function. The orchestration layer
    (``router-agent.render_prompt.cmd_confirm``) is responsible for
    calling ``task_chain.set_parent`` AFTER the state seed is written;
    that path enforces cycle / existence / already-attached invariants
    and emits the ``chain_attached`` audit. Keeping the freeze transform
    pure isolates the suggester / UX integration from the state-shape
    transform.
    """
    if not isinstance(draft, dict):
        raise TypeError("draft must be a dict")
    if not plugin:
        raise ValueError("plugin must be supplied")
    if not _is_safe_plugin_slug(plugin):
        raise ValueError(
            f"plugin must be a safe slug (alnum + ``-_.``, ≤64, no path "
            f"separators): {plugin!r}")
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
        "priority": draft.get("priority") or "P2",
        "history": [],
    }

    if "target_dir" in draft and draft["target_dir"]:
        state["target_dir"] = draft["target_dir"]
    if "dual_mode" in draft:
        state["dual_mode"] = "parallel" if draft["dual_mode"] else "serial"

    # M8.10 — top-level multi-plugin + role-gating fields (NOT under
    # config_overrides; orchestrator-tick reads them from state root).
    if "selected_plugins" in draft and draft["selected_plugins"] is not None:
        sp = draft["selected_plugins"]
        if not isinstance(sp, list) or not all(isinstance(x, str) for x in sp):
            raise ValueError("selected_plugins must be a list of strings")
        state["selected_plugins"] = list(sp)
    if "role_constraints" in draft and draft["role_constraints"] is not None:
        rc = draft["role_constraints"]
        if not isinstance(rc, dict):
            raise ValueError("role_constraints must be a mapping")
        for k in rc:
            if k not in ("included", "excluded"):
                raise ValueError(
                    f"role_constraints unknown key: {k!r}"
                )
        for k in ("included", "excluded"):
            v = rc.get(k)
            if v is None:
                continue
            if not isinstance(v, list):
                raise ValueError(f"role_constraints.{k} must be a list")
            for item in v:
                if (not isinstance(item, dict)
                        or not isinstance(item.get("plugin"), str)
                        or not isinstance(item.get("role"), str)):
                    raise ValueError(
                        f"role_constraints.{k}[*] must be {{plugin,role}}"
                    )
        state["role_constraints"] = {
            k: [dict(item) for item in rc[k]] for k in rc if rc[k] is not None
        }

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
