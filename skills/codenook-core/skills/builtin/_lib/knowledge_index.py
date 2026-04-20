"""Discovery helpers over plugin-shipped knowledge documents.

The router-agent uses this module to enumerate ``knowledge/*.md`` files
shipped with each installed plugin so it can decide which short
summaries to ground its draft on. Bodies are intentionally NOT read
here — see ``docs/router-agent.md`` §7 for the per-turn cap on
full-body fetches.

Public API
----------
- :func:`discover_knowledge`  — flat scan of one plugin's ``knowledge/``.
- :func:`aggregate_knowledge` — plugin_name → discover_knowledge output.
- :func:`find_relevant`       — score + rank against a query string.

Frontmatter shape
-----------------
Each ``.md`` file MAY start with a YAML frontmatter block delimited by
``---`` lines:

    ---
    title: CLI flag conventions
    summary: Long flags use --kebab-case; short flags reserved for the top 8.
    tags: [cli, argparse]
    ---

Files without frontmatter are still listed: ``title`` falls back to the
filename stem, ``summary`` is empty, and ``tags`` is an empty list.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


KNOWLEDGE_DIRNAME = "knowledge"
PLUGINS_DIRNAME = "plugins"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return ``(frontmatter_dict, body)``. Empty dict if absent/invalid."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return {}, text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text
    raw = "".join(lines[1:end_idx])
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    body = "".join(lines[end_idx + 1 :])
    return data, body


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [t.strip() for t in raw if isinstance(t, str) and t.strip()]


def discover_knowledge(plugin_dir: Path) -> list[dict]:
    """Flat scan of ``<plugin_dir>/knowledge/*.md``.

    Subdirectories are ignored. Returns
    ``[{path, title, summary, tags}]`` sorted alphabetically by
    ``path``. ``path`` is the full filesystem path as a string so the
    caller can fetch the body on demand.
    Missing ``knowledge/`` directory yields ``[]``.
    """
    plugin_dir = Path(plugin_dir)
    kdir = plugin_dir / KNOWLEDGE_DIRNAME
    if not kdir.is_dir():
        return []

    out: list[dict] = []
    for entry in sorted(kdir.iterdir(), key=lambda p: p.name):
        if not entry.is_file() or entry.suffix.lower() != ".md":
            continue
        try:
            text = entry.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, _body = _parse_frontmatter(text)
        title = fm.get("title")
        if not isinstance(title, str) or not title.strip():
            title = entry.stem
        summary = fm.get("summary")
        if not isinstance(summary, str):
            summary = ""
        out.append(
            {
                "path": str(entry),
                "title": title.strip(),
                "summary": summary.strip(),
                "tags": _str_list(fm.get("tags")),
            }
        )
    return out


def _plugin_dir_name_from_manifest(manifest_path: Path) -> str:
    """``plugins/<dir>/plugin.yaml`` → ``<dir>`` (the on-disk directory)."""
    return manifest_path.parent.name


def aggregate_knowledge(workspace_root: Path) -> dict[str, list[dict]]:
    """Discover knowledge for every installed plugin under ``workspace_root``.

    Returns ``{plugin_name: [knowledge_record, ...]}`` keyed by the
    plugin directory name (matches the on-disk identity used by
    discovery helpers). Plugins with no ``knowledge/`` directory yield
    an empty list. Missing top-level ``plugins/`` returns ``{}``.
    """
    workspace_root = Path(workspace_root)
    plugins_dir = workspace_root / PLUGINS_DIRNAME
    if not plugins_dir.is_dir():
        return {}
    out: dict[str, list[dict]] = {}
    for entry in sorted(plugins_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        out[entry.name] = discover_knowledge(entry)
    return out


def _score(record: dict, query: str) -> int:
    """+3 per tag substring hit, +2 per title hit, +1 per summary hit."""
    q = query.lower()
    score = 0
    for tag in record.get("tags", []):
        if isinstance(tag, str) and q in tag.lower():
            score += 3
    title = record.get("title") or ""
    if isinstance(title, str) and q in title.lower():
        score += 2
    summary = record.get("summary") or ""
    if isinstance(summary, str) and q in summary.lower():
        score += 1
    return score


def find_relevant(
    query: str,
    aggregated: dict[str, list[dict]],
    limit: int = 5,
) -> list[dict]:
    """Rank knowledge records across plugins by simple substring score.

    Returns flat
    ``[{plugin, path, title, summary, tags, score}, ...]`` truncated
    to ``limit``. Records with score 0 are omitted. Stable secondary
    sort key is ``(plugin, path)`` so equal scores have deterministic
    order. Empty/blank ``query`` returns ``[]``.
    """
    if not query or not query.strip() or limit <= 0:
        return []
    candidates: list[dict] = []
    for plugin, records in aggregated.items():
        for rec in records:
            s = _score(rec, query)
            if s <= 0:
                continue
            candidates.append(
                {
                    "plugin": plugin,
                    "path": rec.get("path", ""),
                    "title": rec.get("title", ""),
                    "summary": rec.get("summary", ""),
                    "tags": list(rec.get("tags", [])),
                    "score": s,
                }
            )
    candidates.sort(key=lambda r: (-r["score"], r["plugin"], r["path"]))
    return candidates[:limit]
