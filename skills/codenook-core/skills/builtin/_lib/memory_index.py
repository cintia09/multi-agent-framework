"""Memory index for the workspace memory layer (M9.1).

Maintains an mtime-cached snapshot of frontmatter metadata at
``.codenook/memory/.index-snapshot.json`` so that ``scan_memory`` can
return a 1000-file index in well under 500 ms even on cold runs and
under 200 ms on warm hits (NFR-PERF-1 / AC-LAY-4).

Snapshot schema (JSON):

    {
      "version": 1,
      "knowledge": {
        "<absolute path>": {
          "mtime": <float>,
          "size": <int>,
          "frontmatter": {...}
        },
        ...
      },
      "skills":   { "<absolute path>": {...} },
      "config":   {...}        # not yet used in M9.1; reserved
    }

The snapshot lives **inside** the workspace's memory dir so it is
naturally per-workspace and is not shared. The path is added to
.gitignore by the init skill.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

SNAPSHOT_NAME = ".index-snapshot.json"
SNAPSHOT_VERSION = 1


# ---------------------------------------------------------------- paths


def _memory_dir(workspace_root: Path | str) -> Path:
    return Path(workspace_root) / ".codenook" / "memory"


def _snapshot_path(workspace_root: Path | str) -> Path:
    return _memory_dir(workspace_root) / SNAPSHOT_NAME


# --------------------------------------------------------------- helpers


def get_hash(content: str) -> str:
    """SHA-256 of the first 512 chars of *content* (FR-EXT-DEDUP)."""
    return hashlib.sha256(content[:512].encode("utf-8")).hexdigest()


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter delimited by leading/trailing ``---`` lines.

    Returns ``{}`` when the document has no frontmatter or the YAML is
    empty. Malformed YAML raises ``yaml.YAMLError``.
    """
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    block = text[4:end]
    data = yaml.safe_load(block) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _read_snapshot(workspace_root: Path | str) -> dict[str, Any]:
    p = _snapshot_path(workspace_root)
    if not p.is_file():
        return {"version": SNAPSHOT_VERSION, "knowledge": {}, "skills": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": SNAPSHOT_VERSION, "knowledge": {}, "skills": {}}
    if data.get("version") != SNAPSHOT_VERSION:
        return {"version": SNAPSHOT_VERSION, "knowledge": {}, "skills": {}}
    data.setdefault("knowledge", {})
    data.setdefault("skills", {})
    return data


def _write_snapshot(workspace_root: Path | str, snapshot: dict[str, Any]) -> None:
    import fcntl
    import tempfile

    p = _snapshot_path(workspace_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Per-call unique tmp prevents collisions across threads/processes;
    # the leading "." keeps it filtered by build_index's scandir loops.
    fd, tmp = tempfile.mkstemp(
        dir=str(p.parent), prefix=".tmp-snap.", suffix=".json"
    )
    lock_path = p.with_name(p.name + ".lock")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=False, default=str))
            f.flush()
            os.fsync(f.fileno())
        # Serialize the rename across threads/processes so concurrent
        # writers do not race os.replace targeting the same path.
        lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            os.replace(tmp, p)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            # DR-011: unlink the lock-file after release. Other writers
            # racing the same window will simply re-create it via
            # O_CREAT; flock semantics on the inode protect correctness.
            try:
                os.unlink(lock_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------- public


def build_index(workspace_root: Path | str, *, force: bool = False) -> dict[str, Any]:
    """Return ``{"knowledge": [...], "skills": [...]}`` of metadata dicts.

    Each entry is a dict ``{"path": <abs-path>, **frontmatter}``. Uses an
    on-disk mtime/size cache so unchanged files are not re-parsed.

    When *force* is true the snapshot is ignored and rebuilt from disk.
    """
    mem = _memory_dir(workspace_root)
    snapshot = (
        {"version": SNAPSHOT_VERSION, "knowledge": {}, "skills": {}}
        if force
        else _read_snapshot(workspace_root)
    )

    knowledge_meta: list[dict[str, Any]] = []
    skills_meta: list[dict[str, Any]] = []

    snap_changed = False

    # ---- knowledge: flat *.md under memory/knowledge/
    kdir = mem / "knowledge"
    if kdir.is_dir():
        new_k: dict[str, dict[str, Any]] = {}
        with os.scandir(kdir) as it:
            for entry in it:
                # Skip hidden / in-flight tmp files (".tmp.*", ".tmp-snap.*").
                if entry.name.startswith("."):
                    continue
                if not entry.is_file() or not entry.name.endswith(".md"):
                    continue
                ap = entry.path
                st = entry.stat()
                cached = snapshot["knowledge"].get(ap)
                if cached and cached.get("mtime") == st.st_mtime and cached.get("size") == st.st_size:
                    fm = cached["frontmatter"]
                else:
                    text = Path(ap).read_text(encoding="utf-8")
                    fm = _parse_frontmatter(text)
                    snap_changed = True
                new_k[ap] = {"mtime": st.st_mtime, "size": st.st_size, "frontmatter": fm}
                meta = {"path": ap}
                meta.update(fm)
                knowledge_meta.append(meta)
        if snapshot["knowledge"] != new_k:
            snapshot["knowledge"] = new_k
            snap_changed = True

    # ---- skills: each subdir's SKILL.md
    sdir = mem / "skills"
    if sdir.is_dir():
        new_s: dict[str, dict[str, Any]] = {}
        with os.scandir(sdir) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                if not entry.is_dir():
                    continue
                skill_md = Path(entry.path) / "SKILL.md"
                if not skill_md.is_file():
                    continue
                ap = str(skill_md)
                st = skill_md.stat()
                cached = snapshot["skills"].get(ap)
                if cached and cached.get("mtime") == st.st_mtime and cached.get("size") == st.st_size:
                    fm = cached["frontmatter"]
                else:
                    text = skill_md.read_text(encoding="utf-8")
                    fm = _parse_frontmatter(text)
                    snap_changed = True
                new_s[ap] = {"mtime": st.st_mtime, "size": st.st_size, "frontmatter": fm}
                meta = {"path": ap, "name": entry.name}
                meta.update(fm)
                skills_meta.append(meta)
        if snapshot["skills"] != new_s:
            snapshot["skills"] = new_s
            snap_changed = True

    if snap_changed and mem.is_dir():
        _write_snapshot(workspace_root, snapshot)

    return {"knowledge": knowledge_meta, "skills": skills_meta}


def invalidate(workspace_root: Path | str, path: Path | str) -> None:
    """Drop *path* from the snapshot so the next ``build_index`` re-reads it."""
    snapshot = _read_snapshot(workspace_root)
    sp = str(path)
    changed = False
    for bucket in ("knowledge", "skills"):
        if sp in snapshot.get(bucket, {}):
            snapshot[bucket].pop(sp, None)
            changed = True
    if changed:
        _write_snapshot(workspace_root, snapshot)


# ---------------------------------------------------------- index.yaml export


INDEX_YAML_NAME = "index.yaml"
INDEX_YAML_VERSION = 1


def _rel_to_workspace(workspace_root: Path | str, path: str) -> str:
    ws = Path(workspace_root).resolve()
    try:
        return str(Path(path).resolve().relative_to(ws))
    except (ValueError, OSError):
        return path


def _collect_sources(meta: dict[str, Any]) -> list[str]:
    """Derive a de-duplicated list of source task-ids from a meta dict.

    Precedence: explicit ``sources:`` list (new, populated by the
    fuzzy-merge path) → legacy ``related_tasks`` → single
    ``created_from_task`` fallback. Preserves first-seen order so the
    list is stable across regenerations.
    """
    out: list[str] = []
    seen: set[str] = set()

    def _push(val: Any) -> None:
        if isinstance(val, str) and val and val not in seen:
            seen.add(val)
            out.append(val)

    for v in meta.get("sources") or []:
        _push(v)
    for v in meta.get("related_tasks") or []:
        _push(v)
    _push(meta.get("created_from_task"))
    _push(meta.get("source_task"))
    return out


def export_index_yaml(workspace_root: Path | str) -> Path:
    """Write a human-readable summary of memory/{skills,knowledge}/.

    Schema::

        version: 1
        generated_at: <iso8601>
        skills:
          - name: <str>
            summary: <str>
            tags: [<str>...]
            status: <str>
            path: .codenook/memory/skills/<name>/SKILL.md
        knowledge:
          - topic: <str>
            summary: <str>
            tags: [<str>...]
            status: <str>
            path: .codenook/memory/knowledge/<topic>.md

    Derived from :func:`build_index`; the YAML is a 2nd output of the
    same scan. Atomic write via tempfile + os.replace.
    """
    import datetime as _dt
    import tempfile

    mem = _memory_dir(workspace_root)
    mem.mkdir(parents=True, exist_ok=True)
    index = build_index(workspace_root)

    skills_out: list[dict[str, Any]] = []
    for meta in index.get("skills", []):
        ap = meta.get("path", "")
        skills_out.append(
            {
                "name": meta.get("name") or Path(ap).parent.name,
                "summary": meta.get("summary", ""),
                "tags": list(meta.get("tags") or []),
                "status": meta.get("status", ""),
                "sources": _collect_sources(meta),
                "path": _rel_to_workspace(workspace_root, ap),
            }
        )

    knowledge_out: list[dict[str, Any]] = []
    for meta in index.get("knowledge", []):
        ap = meta.get("path", "")
        knowledge_out.append(
            {
                "topic": meta.get("topic") or Path(ap).stem,
                "summary": meta.get("summary", ""),
                "tags": list(meta.get("tags") or []),
                "status": meta.get("status", ""),
                "sources": _collect_sources(meta),
                "path": _rel_to_workspace(workspace_root, ap),
            }
        )

    payload = {
        "version": INDEX_YAML_VERSION,
        "generated_at": _dt.datetime.now(tz=_dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "skills": skills_out,
        "knowledge": knowledge_out,
    }

    target = mem / INDEX_YAML_NAME
    fd, tmp = tempfile.mkstemp(dir=str(mem), prefix=".tmp-index.", suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target
