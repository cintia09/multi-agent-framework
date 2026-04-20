#!/usr/bin/env python3
"""Memory garbage collector CLI (M9.8 — locked decision #5).

Enforces the per-task caps from
``docs/memory-and-extraction.md`` §6 / §7 across the whole
workspace memory layer:

* ``knowledge`` — at most **3** entries per ``created_from_task``
* ``skill``     — at most **1** entry  per ``created_from_task``
* ``config``    — at most **5** entries per ``created_from_task``

When a per-task group is over its cap we drop the **oldest** entries
(by ``created_at`` for knowledge / skill, by ``updated_at`` /
``last_used_at`` falling back to ``created_at`` for config) until the
cap is satisfied. Promoted entries are never pruned — only
``status: candidate`` (or unset) entries are eligible.

Pruning goes through ``_atomic_write_text`` for config and through
``Path.unlink()`` for filesystem assets, both of which are
plugin-readonly safe (the memory tree never lives under ``plugins/``
but the linter still sees the intent). Each removal emits a single
audit record via :func:`extract_audit.audit` with
``outcome='gc_pruned', verdict='accepted'``.

Usage::

    python -m memory_gc --workspace <ws> [--dry-run] [--json]

Exit codes:
  0  nothing pruned, or pruned successfully
  1  unexpected error
  2  invalid arguments
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Resolve sibling _lib modules (memory_layer, memory_index, extract_audit).
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import memory_layer as ml  # noqa: E402
import memory_index  # noqa: E402
import extract_audit  # noqa: E402

# -------------------------------------------------------------- caps (§6/§7)

CAPS: dict[str, int] = {
    "knowledge": 3,
    "skill": 1,
    "config": 5,
}


# -------------------------------------------------------------- helpers


def _safe_str(v: Any) -> str:
    return v if isinstance(v, str) else ""


def _knowledge_groups(ws: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for meta in ml.scan_knowledge(ws):
        if _safe_str(meta.get("status")) == "promoted":
            continue
        task = _safe_str(meta.get("created_from_task"))
        if not task:
            continue
        out.setdefault(task, []).append(meta)
    return out


def _skill_groups(ws: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for meta in ml.scan_skills(ws):
        if _safe_str(meta.get("status")) == "promoted":
            continue
        task = _safe_str(meta.get("created_from_task"))
        if not task:
            continue
        out.setdefault(task, []).append(meta)
    return out


def _config_groups(ws: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    try:
        entries = ml.read_config_entries(ws)
    except (ml.MemoryLayoutError, ml.ConfigSchemaError):
        return out
    for entry in entries:
        if _safe_str(entry.get("status")) == "promoted":
            continue
        task = _safe_str(entry.get("created_from_task"))
        if not task:
            continue
        out.setdefault(task, []).append(entry)
    return out


def _sort_oldest_first(items: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    # Empty / missing timestamps sort first (treated as oldest).
    return sorted(items, key=lambda m: _safe_str(m.get(key)) or "")


def _plan_removals(ws: Path) -> dict[str, list[dict[str, Any]]]:
    """Return ``{asset_type: [meta-or-entry, ...]}`` of entries to drop."""
    plan: dict[str, list[dict[str, Any]]] = {"knowledge": [], "skill": [], "config": []}

    for task, items in _knowledge_groups(ws).items():
        cap = CAPS["knowledge"]
        if len(items) <= cap:
            continue
        # Tie-break on path so groups with second-resolution created_at
        # still prune the lexicographically earliest (= insertion order
        # for the deterministic topic naming in tests + extractors).
        ordered = sorted(items, key=lambda m: (_safe_str(m.get("created_at")), _safe_str(m.get("path"))))
        plan["knowledge"].extend(ordered[: len(items) - cap])

    for task, items in _skill_groups(ws).items():
        cap = CAPS["skill"]
        if len(items) <= cap:
            continue
        ordered = sorted(items, key=lambda m: (_safe_str(m.get("created_at")), _safe_str(m.get("path"))))
        plan["skill"].extend(ordered[: len(items) - cap])

    for task, items in _config_groups(ws).items():
        cap = CAPS["config"]
        if len(items) <= cap:
            continue
        # config entries prefer last_used_at then created_at as the recency
        # signal (spec §6.3 — "config patch by latest value, applies_when").
        def _recency(e: dict[str, Any]) -> tuple[str, str]:
            return (
                _safe_str(e.get("last_used_at")) or _safe_str(e.get("created_at")),
                _safe_str(e.get("key")),
            )
        ordered = sorted(items, key=_recency)
        plan["config"].extend(ordered[: len(items) - cap])

    return plan


# -------------------------------------------------------------- execution


def _delete_knowledge(ws: Path, meta: dict[str, Any]) -> None:
    p = Path(meta["path"])
    if p.is_file():
        p.unlink()
    memory_index.invalidate(ws, p)


def _delete_skill(ws: Path, meta: dict[str, Any]) -> None:
    p = Path(meta["path"])
    if p.is_file():
        p.unlink()
        # Best-effort: drop the now-empty <name>/ dir.
        parent = p.parent
        try:
            parent.rmdir()
        except OSError:
            pass
    memory_index.invalidate(ws, p)


def _delete_config_entries(ws: Path, drops: list[dict[str, Any]]) -> None:
    """Rewrite ``config.yaml`` minus *drops* atomically."""
    if not drops:
        return
    import yaml

    drop_keys = {e.get("key") for e in drops}
    cfg_path = ml._config_path(ws)
    data = ml._load_config_yaml(ws)
    data["entries"] = [e for e in data["entries"] if e.get("key") not in drop_keys]
    rendered = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    ml._atomic_write_text(cfg_path, rendered, workspace_root=ws)


def _emit_audit(
    ws: Path,
    *,
    asset_type: str,
    item: dict[str, Any],
    dry_run: bool,
) -> None:
    if dry_run:
        return
    extract_audit.audit(
        ws,
        asset_type=asset_type,
        outcome="gc_pruned",
        verdict="accepted",
        reason=f"per-task cap {CAPS[asset_type]} exceeded",
        source_task=_safe_str(item.get("created_from_task")),
        candidate_hash=_safe_str(item.get("dedup_hash")),
        existing_path=_safe_str(item.get("path")) or None,
    )


# -------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="memory_gc",
        description=(
            "Prune workspace memory entries that exceed the per-task "
            "caps from docs/memory-and-extraction.md §6/§7."
        ),
    )
    p.add_argument("--workspace", required=True, help="workspace root containing .codenook/memory/")
    p.add_argument("--dry-run", action="store_true", help="print planned removals; do not touch disk")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON envelope")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as e:
        # argparse exits 2 on error; bubble through.
        return int(e.code) if isinstance(e.code, int) else 2

    ws = Path(ns.workspace)
    if not ws.is_dir():
        sys.stderr.write(f"memory_gc: workspace not found: {ws}\n")
        return 2
    if not (ws / ".codenook" / "memory").is_dir():
        sys.stderr.write(f"memory_gc: memory tree not initialized in {ws}\n")
        return 2

    try:
        plan = _plan_removals(ws)
        counts = {k: len(v) for k, v in plan.items()}

        if ns.dry_run:
            envelope = {
                "dry_run": True,
                "workspace": str(ws),
                "planned": counts,
                "items": {
                    k: [
                        {
                            "path": _safe_str(m.get("path")) or _safe_str(m.get("key")),
                            "created_from_task": _safe_str(m.get("created_from_task")),
                            "created_at": _safe_str(m.get("created_at")),
                        }
                        for m in v
                    ]
                    for k, v in plan.items()
                },
            }
            if ns.json:
                print(json.dumps(envelope, ensure_ascii=False))
            else:
                print(f"[dry-run] planned removals: {counts}")
            return 0

        # Real run — order matters: emit audit BEFORE deletion so the
        # existing_path field is still resolvable; then mutate disk.
        for meta in plan["knowledge"]:
            _emit_audit(ws, asset_type="knowledge", item=meta, dry_run=False)
            _delete_knowledge(ws, meta)
        for meta in plan["skill"]:
            _emit_audit(ws, asset_type="skill", item=meta, dry_run=False)
            _delete_skill(ws, meta)
        for entry in plan["config"]:
            _emit_audit(ws, asset_type="config", item=entry, dry_run=False)
        _delete_config_entries(ws, plan["config"])

        # Refresh the index snapshot so subsequent scan_memory calls see
        # the post-prune state without a stale cache hit.
        memory_index.build_index(ws, force=True)

        envelope = {
            "dry_run": False,
            "workspace": str(ws),
            "pruned": counts,
        }
        if ns.json:
            print(json.dumps(envelope, ensure_ascii=False))
        else:
            print(f"pruned: {counts}")
        return 0

    except Exception as exc:  # noqa: BLE001 — surface as exit 1
        sys.stderr.write(f"memory_gc: error: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
