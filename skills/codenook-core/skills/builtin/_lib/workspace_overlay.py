"""Workspace user-overlay layer (M8.9).

Each workspace has a writable user-overlay that mirrors the read-only
plugin shape but is project-scoped. Layout:

    <workspace>/.codenook/user-overlay/
      ├── description.md     # project context the user accumulates
      ├── skills/<skill>/    # workspace-only skills (mirror plugins/<p>/skills/)
      ├── knowledge/*.md     # workspace-only knowledge (frontmatter optional)
      └── config.yaml        # workspace-only config overrides

A missing overlay directory is the normal case for a fresh workspace;
all helpers degrade gracefully to empty results rather than raising.
The single exception is malformed YAML in config.yaml, which raises
ValueError with the offending path so the router-agent can surface
the problem to the user.

See docs/router-agent.md §7 (knowledge access) and the M8 plan
"Design patch — multi-plugin + workspace-overlay" section.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

OVERLAY_DIRNAME = "user-overlay"
CODENOOK_DIRNAME = ".codenook"


# ---------------------------------------------------------------- paths


def overlay_root(workspace_root: Path | str) -> Path:
    return Path(workspace_root) / CODENOOK_DIRNAME / OVERLAY_DIRNAME


def has_overlay(workspace_root: Path | str) -> bool:
    return overlay_root(workspace_root).is_dir()


# ---------------------------------------------------------------- atoms


def read_description(workspace_root: Path | str) -> str:
    p = overlay_root(workspace_root) / "description.md"
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8")


def read_config(workspace_root: Path | str) -> dict:
    p = overlay_root(workspace_root) / "config.yaml"
    if not p.is_file():
        return {}
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"malformed YAML in {p}: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{p}: top-level must be a mapping, got {type(data).__name__}")
    return data


def discover_overlay_skills(workspace_root: Path | str) -> list[dict]:
    skills_dir = overlay_root(workspace_root) / "skills"
    if not skills_dir.is_dir():
        return []
    out: list[dict] = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        out.append({
            "name": entry.name,
            "path": entry.resolve(),
            "has_skill_md": (entry / "SKILL.md").is_file(),
        })
    return out


# ---------------------------------------------------------------- knowledge


_FM_OPEN = "---\n"


def _parse_knowledge_frontmatter(text: str) -> tuple[dict, str]:
    """Split optional YAML frontmatter from markdown body.

    Returns ({}, text) when no leading '---\\n...\\n---' block is present
    or when the block is malformed (lenient — knowledge files can be
    plain markdown).
    """
    if not text.startswith("---"):
        return {}, text
    rest = text[len("---"):]
    if not rest.startswith("\n") and not rest.startswith("\r\n"):
        return {}, text
    rest = rest.lstrip("\n")
    end = rest.find("\n---")
    if end == -1:
        return {}, text
    fm_text = rest[:end]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(fm, dict):
        return {}, text
    body = rest[end + len("\n---"):]
    if body.startswith("\n"):
        body = body[1:]
    return fm, body


def discover_overlay_knowledge(workspace_root: Path | str) -> list[dict]:
    kdir = overlay_root(workspace_root) / "knowledge"
    if not kdir.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(kdir.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".md":
            continue
        text = p.read_text(encoding="utf-8")
        fm, _body = _parse_knowledge_frontmatter(text)
        title = fm.get("title") if isinstance(fm.get("title"), str) else None
        summary = fm.get("summary") if isinstance(fm.get("summary"), str) else None
        tags = fm.get("tags") if isinstance(fm.get("tags"), list) else None
        out.append({
            "path": str(p.resolve()),
            "title": title if title else p.stem,
            "summary": summary if summary is not None else "",
            "tags": list(tags) if tags is not None else [],
        })
    return out


# ---------------------------------------------------------------- aggregate


def overlay_bundle(workspace_root: Path | str) -> dict:
    if not has_overlay(workspace_root):
        return {
            "present": False,
            "description": "",
            "config": {},
            "skills": [],
            "knowledge": [],
        }
    return {
        "present": True,
        "description": read_description(workspace_root),
        "config": read_config(workspace_root),
        "skills": discover_overlay_skills(workspace_root),
        "knowledge": discover_overlay_knowledge(workspace_root),
    }


def merge_config_into_draft(
    draft: dict | None,
    overlay_config: dict | None,
) -> dict:
    """Shallow merge: overlay keys win over draft keys.

    Always returns a new dict; never mutates the inputs. ``None`` is
    treated as an empty mapping.
    """
    a: dict[str, Any] = dict(draft) if draft else {}
    b: dict[str, Any] = dict(overlay_config) if overlay_config else {}
    a.update(b)
    return a


__all__ = [
    "OVERLAY_DIRNAME",
    "CODENOOK_DIRNAME",
    "overlay_root",
    "has_overlay",
    "read_description",
    "read_config",
    "discover_overlay_skills",
    "discover_overlay_knowledge",
    "overlay_bundle",
    "merge_config_into_draft",
]
