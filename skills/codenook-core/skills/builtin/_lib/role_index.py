"""Role enumeration + plugin/role constraint helpers (M8.10).

The router-agent uses these to surface available roles per plugin
(via ``one_line_job``) so the user can opt-in/out at task creation
time. ``orchestrator-tick`` calls :func:`is_role_allowed` before
dispatching each phase to honour ``state.role_constraints``.

Role file layout (mirrors M2/M6 plugin shape):

    plugins/<plugin>/roles/<role>.md
        ---
        name: <role>
        plugin: <plugin>
        phase: <phase-id>
        manifest: <phase-N-role.md>
        one_line_job: "<short job description>"
        ---

        # Title

        **One-line job:** <same text>

If the frontmatter omits ``one_line_job`` (legacy roles), we fall back
to the first markdown body line matching the ``**One-line job:** ...``
pattern. If neither is present we yield an empty string rather than
raising — the router-agent UI will simply show an empty hint.

Pure stdlib + PyYAML; no I/O outside the supplied paths.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROLES_DIRNAME = "roles"
PLUGINS_DIRNAME = "plugins"

_FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_ONE_LINE_RE = re.compile(r"\*\*One-line job:\*\*\s*(.+)")


# ---------------------------------------------------------------- discovery


def _parse_role_file(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _FM_RE.match(text)
    if not m:
        return None
    fm_text, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None

    one_line = fm.get("one_line_job")
    if not (isinstance(one_line, str) and one_line.strip()):
        body_match = _ONE_LINE_RE.search(body)
        one_line = body_match.group(1).strip() if body_match else ""

    return {
        "plugin": fm.get("plugin", "") or "",
        "role": fm.get("name", path.stem) or path.stem,
        "phase": fm.get("phase", "") or "",
        "manifest": fm.get("manifest", "") or "",
        "one_line_job": one_line,
    }


def discover_roles(plugin_dir: Path | str) -> list[dict]:
    """Return parsed role records for every ``plugin_dir/roles/*.md``.

    Missing ``roles/`` directory yields ``[]``. Files that fail to
    parse (bad frontmatter, unreadable) are skipped silently. Sorted
    alphabetically by role name for stability.
    """
    plugin_dir = Path(plugin_dir)
    roles_dir = plugin_dir / ROLES_DIRNAME
    if not roles_dir.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(roles_dir.glob("*.md"), key=lambda x: x.name):
        rec = _parse_role_file(p)
        if rec is not None:
            out.append(rec)
    return out


def aggregate_roles(workspace_root: Path | str) -> dict[str, list[dict]]:
    """Map ``plugin_name -> discover_roles(plugins/<plugin>)``.

    Empty dict when ``plugins/`` is missing.
    """
    workspace_root = Path(workspace_root)
    plugins_dir = workspace_root / PLUGINS_DIRNAME
    if not plugins_dir.is_dir():
        return {}
    out: dict[str, list[dict]] = {}
    for entry in sorted(plugins_dir.iterdir(), key=lambda p: p.name):
        if entry.is_dir():
            out[entry.name] = discover_roles(entry)
    return out


# ---------------------------------------------------------------- filtering


def _as_pair_set(items: Any) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    if not isinstance(items, list):
        return out
    for it in items:
        if isinstance(it, dict) and "plugin" in it and "role" in it:
            out.add((str(it["plugin"]), str(it["role"])))
    return out


def filter_roles(roles: list[dict], constraints: dict | None) -> list[dict]:
    """Apply include/exclude constraints to a flat list of role records.

    - empty constraints -> identity (returns a *new* list)
    - included non-empty -> whitelist; excluded subtracts from it
    - included empty + excluded non-empty -> blacklist
    Never mutates the input list.
    """
    constraints = constraints or {}
    included = _as_pair_set(constraints.get("included"))
    excluded = _as_pair_set(constraints.get("excluded"))

    out: list[dict] = []
    for r in roles:
        key = (str(r.get("plugin", "")), str(r.get("role", "")))
        if included and key not in included:
            continue
        if key in excluded:
            continue
        out.append(dict(r))
    return out


def is_role_allowed(
    plugin: str, role: str, constraints: dict | None
) -> bool:
    """Convenience predicate for orchestrator-tick.

    Returns True when the (plugin, role) pair survives the constraints.
    Empty constraints -> True.
    """
    constraints = constraints or {}
    included = _as_pair_set(constraints.get("included"))
    excluded = _as_pair_set(constraints.get("excluded"))
    key = (str(plugin), str(role))
    if key in excluded:
        return False
    if included and key not in included:
        return False
    return True


__all__ = [
    "discover_roles",
    "aggregate_roles",
    "filter_roles",
    "is_role_allowed",
]
