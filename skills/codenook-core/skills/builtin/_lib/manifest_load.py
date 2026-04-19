"""Shared loader for installed-plugin manifests (M3).

Used by router-bootstrap, router-context-scan and router-dispatch-build
(and historically by router-triage, removed in M8.7) to enumerate
`<ws>/.codenook/plugins/<id>/plugin.yaml` without each skill
re-implementing the same I/O + light validation.

Design notes
------------
* Per architecture decision, the on-disk manifest filename is
  `plugin.yaml` (matches M2 plugin-schema). The user-facing M3 spec
  refers to it as a "manifest" — surfaced as a doc-only naming gloss,
  not a code change.
* Loader is tolerant: a missing `intent_patterns` field becomes []
  rather than an error (intent_patterns is optional for non-domain
  plugins).
* Returns a stable, sorted list keyed by plugin id so downstream
  decisions are deterministic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml  # PyYAML
except ImportError as e:  # pragma: no cover — caller surfaces this
    raise SystemExit(f"manifest_load: PyYAML not installed ({e})")

MANIFEST_FILENAME = "plugin.yaml"


class ManifestError(Exception):
    """Raised when a plugin.yaml is missing required fields or unparseable."""


def plugins_dir(workspace: Path) -> Path:
    return workspace / ".codenook" / "plugins"


def list_installed_ids(workspace: Path) -> list[str]:
    """Return sorted ids of subdirectories under .codenook/plugins/."""
    pdir = plugins_dir(workspace)
    if not pdir.is_dir():
        return []
    out = []
    for child in pdir.iterdir():
        if child.is_dir() and (child / MANIFEST_FILENAME).is_file():
            out.append(child.name)
    return sorted(out)


def load_manifest(workspace: Path, plugin_id: str) -> dict[str, Any]:
    """Load and lightly validate one plugin manifest.

    Returns the parsed mapping. Raises ManifestError on parse error or
    missing top-level `id`/`version` (the only fields router code
    actually consumes — full schema enforcement is M2's job).
    """
    path = plugins_dir(workspace) / plugin_id / MANIFEST_FILENAME
    if not path.is_file():
        raise ManifestError(f"manifest not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ManifestError(f"invalid YAML in {path}: {e}") from e
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: top-level not a mapping")
    if "id" not in data or "version" not in data:
        raise ManifestError(f"{path}: missing id/version")
    data.setdefault("intent_patterns", [])
    if not isinstance(data["intent_patterns"], list):
        raise ManifestError(f"{path}: intent_patterns must be a list")
    return data


def load_all(workspace: Path) -> list[dict[str, Any]]:
    """Load every installed manifest. Skips invalid ones with a marker entry
    so callers can surface partial failures without aborting."""
    out = []
    for pid in list_installed_ids(workspace):
        try:
            out.append(load_manifest(workspace, pid))
        except ManifestError as e:
            out.append({"id": pid, "version": "?", "intent_patterns": [],
                        "_error": str(e)})
    return out
