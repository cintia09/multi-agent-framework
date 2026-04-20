"""Discovery + scoring helpers over installed plugin manifests.

The router-agent uses these helpers to enumerate the plugins shipped with
the workspace without forcing the main session to read any domain file.

Manifest filename
-----------------
The canonical M2/M6 plugin manifest is ``plugins/<id>/plugin.yaml`` (see
``docs/router-agent.md`` §2 and §5). This module scans for that
file. The earlier M8 spec draft referenced ``manifest.yaml``; the
filename was finalised to ``plugin.yaml`` before M6 shipped.

Public API
----------
- :func:`discover_plugins` — enumerate ``plugins/*/plugin.yaml``.
- :func:`index_by_keyword` — lowercased keyword → list of plugin names.
- :func:`match_plugins`    — substring-keyword match against user text.
- :func:`summary_for_router` — compact projection embedded in the
  router-agent prompt.

Pure stdlib + PyYAML; no I/O outside the supplied workspace_root.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


MANIFEST_FILENAME = "plugin.yaml"
DEFAULT_PRIORITY = 100


def discover_plugins(workspace_root: Path) -> list[dict]:
    """Return parsed manifests for every ``plugins/*/plugin.yaml``.

    Each result has ``_path`` injected as a POSIX path relative to
    ``workspace_root``. Missing ``plugins/`` directory returns ``[]``.
    Manifests that fail to parse or do not yield a dict are skipped.
    Sorted alphabetically by plugin directory name for stability.
    """
    workspace_root = Path(workspace_root)
    plugins_dir = workspace_root / "plugins"
    if not plugins_dir.is_dir():
        return []

    out: list[dict] = []
    for entry in sorted(plugins_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        manifest = entry / MANIFEST_FILENAME
        if not manifest.is_file():
            continue
        try:
            with manifest.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except (yaml.YAMLError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        rel = manifest.relative_to(workspace_root).as_posix()
        data["_path"] = rel
        out.append(data)
    return out


def _normalise_keywords(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    keep: list[str] = []
    for kw in raw:
        if not isinstance(kw, str):
            continue
        norm = kw.strip().lower()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        keep.append(norm)
    return keep


def _plugin_name(plugin: dict) -> str | None:
    """Resolve the plugin's public name, preferring ``name`` over ``id``."""
    for key in ("name", "id"):
        v = plugin.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def index_by_keyword(plugins: list[dict]) -> dict[str, list[str]]:
    """Build keyword → list[plugin_name] index.

    - Keywords are lowercased and de-duplicated per plugin.
    - Plugins without ``routing.keywords`` (or with an empty list) are
      skipped — they contribute no entries.
    - Within a keyword's list, plugin names appear in input order and
      are de-duplicated.
    """
    index: dict[str, list[str]] = {}
    for plugin in plugins:
        routing = plugin.get("routing") if isinstance(plugin, dict) else None
        if not isinstance(routing, dict):
            continue
        keywords = _normalise_keywords(routing.get("keywords"))
        if not keywords:
            continue
        name = _plugin_name(plugin)
        if name is None:
            continue
        for kw in keywords:
            bucket = index.setdefault(kw, [])
            if name not in bucket:
                bucket.append(name)
    return index


def match_plugins(
    user_text: str, index: dict[str, list[str]]
) -> list[tuple[str, int]]:
    """Score plugins by substring keyword hits in ``user_text``.

    Case-insensitive substring match. Returns ``[(name, hits)]`` sorted
    by hits descending, then plugin name ascending. Plugins with zero
    hits are omitted.
    """
    text = (user_text or "").lower()
    if not text or not index:
        return []
    hits: dict[str, int] = {}
    for keyword, names in index.items():
        if not keyword:
            continue
        if keyword in text:
            for name in names:
                hits[name] = hits.get(name, 0) + 1
    return sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))


def summary_for_router(plugins: list[dict]) -> list[dict]:
    """Project each manifest into the compact dict embedded in the prompt.

    Shape: ``{name, description, keywords, applies_to, priority}``.
    - ``name`` falls back to ``id`` when ``name`` is absent.
    - ``description`` reads ``summary`` (M6 plugins use ``summary``);
      whitespace is collapsed.
    - ``keywords`` and ``applies_to`` are normalised string lists.
    - ``priority`` reads ``routing.priority`` and defaults to
      :data:`DEFAULT_PRIORITY` when missing or non-numeric.
    Plugins without a resolvable name are skipped.
    """
    out: list[dict] = []
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        name = _plugin_name(plugin)
        if name is None:
            continue
        summary = plugin.get("summary") or plugin.get("description") or ""
        if isinstance(summary, str):
            description = " ".join(summary.split())
        else:
            description = ""
        keywords: list[str] = []
        applies_to: list[str] = []
        routing = plugin.get("routing") if isinstance(plugin.get("routing"), dict) else {}
        for kw in routing.get("keywords", []) or []:
            if isinstance(kw, str) and kw.strip():
                keywords.append(kw.strip())
        for tag in plugin.get("applies_to", []) or []:
            if isinstance(tag, str) and tag.strip():
                applies_to.append(tag.strip())
        priority_raw = routing.get("priority", DEFAULT_PRIORITY)
        try:
            priority = int(priority_raw)
        except (TypeError, ValueError):
            priority = DEFAULT_PRIORITY
        out.append(
            {
                "name": name,
                "description": description,
                "keywords": keywords,
                "applies_to": applies_to,
                "priority": priority,
            }
        )
    return out
