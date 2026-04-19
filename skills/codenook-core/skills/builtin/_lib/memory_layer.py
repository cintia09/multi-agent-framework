"""Memory layer (M9.1) — workspace-local writable knowledge / skills /
config store.

Layout (created by the ``init`` builtin skill):

    <workspace>/.codenook/memory/
      ├── knowledge/<topic>.md     # flat layout, single .md per topic
      ├── skills/<name>/SKILL.md   # each promoted skill in its own dir
      ├── config.yaml              # single-file entries[] (version: 1)
      ├── history/extraction-log.jsonl
      └── .index-snapshot.json     # mtime cache (gitignored)

Public API (locked, see docs/v6/memory-and-extraction-v6.md §10):

    init_memory_skeleton, scan_memory,
    scan_knowledge, read_knowledge, write_knowledge, patch_knowledge,
    replace_knowledge, promote_knowledge, archive_knowledge,
    scan_skills, read_skill, write_skill, patch_skill,
    read_config_entries, upsert_config_entry, match_entries_for_task,
    find_similar, has_hash, append_audit

Concurrency:
    Writes are atomic via tempfile + os.replace in the same directory.
    Mutating helpers (patch_*, upsert_*) take a per-file fcntl lock for
    the read-modify-write critical section.

Schema validation (M9.1 minimum):
    write_knowledge enforces summary ≤ 200 chars and tags ≤ 8.
    read_config_entries rejects duplicate keys (FR-LAY-6 / AC-LAY-6).
"""
from __future__ import annotations

import datetime as _dt
import fcntl
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Literal

import yaml

# memory_index ships alongside this module under skills/builtin/_lib/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memory_index  # noqa: E402

# ---------------------------------------------------------------- constants

CODENOOK_DIRNAME = ".codenook"
MEMORY_DIRNAME = "memory"

MAX_SUMMARY_CHARS = 200
MAX_TAGS = 8
MAX_TOPIC_CHARS = 64

LOCK_TIMEOUT_S = 5.0


# ---------------------------------------------------------------- exceptions


class MemoryLayoutError(RuntimeError):
    """Raised when the memory skeleton is missing or malformed."""


class ConfigSchemaError(ValueError):
    """Raised when config.yaml top-level structure is invalid."""


class SecretBlockedError(RuntimeError):
    """Raised by extractors when a secret-scanner hit is detected."""


class ConcurrentWriteError(RuntimeError):
    """Raised when a per-file fcntl lock cannot be acquired in time."""


# ---------------------------------------------------------------- paths


def memory_root(workspace_root: Path | str) -> Path:
    return Path(workspace_root) / CODENOOK_DIRNAME / MEMORY_DIRNAME


def has_memory(workspace_root: Path | str) -> bool:
    root = memory_root(workspace_root)
    return root.is_dir() and (root / "config.yaml").exists()


def _knowledge_dir(ws: Path | str) -> Path:
    return memory_root(ws) / "knowledge"


def _skills_dir(ws: Path | str) -> Path:
    return memory_root(ws) / "skills"


def _history_dir(ws: Path | str) -> Path:
    return memory_root(ws) / "history"


def _config_path(ws: Path | str) -> Path:
    return memory_root(ws) / "config.yaml"


def _audit_log(ws: Path | str) -> Path:
    return _history_dir(ws) / "extraction-log.jsonl"


# ---------------------------------------------------------------- skeleton


_EMPTY_CONFIG = "version: 1\nentries: []\n"


def init_memory_skeleton(workspace_root: Path | str) -> None:
    """Create the empty memory skeleton (FR-LAY-1 / AC-LAY-1)."""
    root = memory_root(workspace_root)
    for sub in (root, _knowledge_dir(workspace_root), _skills_dir(workspace_root), _history_dir(workspace_root)):
        sub.mkdir(parents=True, exist_ok=True)
    cfg = _config_path(workspace_root)
    if not cfg.exists():
        cfg.write_text(_EMPTY_CONFIG, encoding="utf-8")


# ---------------------------------------------------------------- atomic IO


def _atomic_write_text(path: Path, content: str) -> None:
    """tempfile + os.replace in the same directory → atomic on POSIX."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # suffix=".tmp" (not the real extension) so concurrent scanners that
    # filter by extension cannot race-pick the in-flight file.
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _flock_acquire(lock_path: Path, *, timeout: float = LOCK_TIMEOUT_S) -> int:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    import time

    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise ConcurrentWriteError(f"could not acquire lock {lock_path}")
            time.sleep(0.02)


def _flock_release(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


# -------------------------------------------------------------- frontmatter


_FRONT_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


def _parse_frontmatter_doc(text: str) -> tuple[dict[str, Any], str]:
    m = _FRONT_RE.match(text)
    if not m:
        return {}, text
    raw_fm, body = m.group(1), m.group(2)
    fm = yaml.safe_load(raw_fm) or {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def _render_frontmatter_doc(frontmatter: dict[str, Any], body: str) -> str:
    fm = yaml.safe_dump(frontmatter, sort_keys=True, allow_unicode=True).rstrip() + "\n"
    if body and not body.endswith("\n"):
        body = body + "\n"
    return f"---\n{fm}---\n{body}"


def _validate_frontmatter(fm: dict[str, Any]) -> None:
    summary = fm.get("summary", "")
    if not isinstance(summary, str):
        raise ValueError("summary must be a string")
    if len(summary) > MAX_SUMMARY_CHARS:
        raise ValueError(f"summary exceeds {MAX_SUMMARY_CHARS} chars (got {len(summary)})")
    tags = fm.get("tags", [])
    if not isinstance(tags, list):
        raise ValueError("tags must be a list")
    if len(tags) > MAX_TAGS:
        raise ValueError(f"tags exceed {MAX_TAGS} (got {len(tags)})")
    for t in tags:
        if not isinstance(t, str):
            raise ValueError(f"tag must be a string: {t!r}")


# --------------------------------------------------------------- topic util


_TOPIC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-.]*$")


def _validate_topic(topic: str) -> None:
    if "/" in topic or "\\" in topic or os.sep in topic:
        raise ValueError(f"topic must use flat layout (no path separators): {topic!r}")
    if not _TOPIC_RE.match(topic):
        raise ValueError(f"invalid topic name: {topic!r}")
    if len(topic) > MAX_TOPIC_CHARS:
        raise ValueError(f"topic exceeds {MAX_TOPIC_CHARS} chars (got {len(topic)})")


def _knowledge_path(ws: Path | str, topic: str) -> Path:
    _validate_topic(topic)
    return _knowledge_dir(ws) / f"{topic}.md"


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- knowledge


def scan_knowledge(workspace_root: Path | str) -> list[dict[str, Any]]:
    """Return frontmatter-only metadata for every knowledge entry."""
    return memory_index.build_index(workspace_root)["knowledge"]


def read_knowledge(path: Path | str) -> dict[str, Any]:
    """Read ``{path, frontmatter, body}`` from a knowledge file."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter_doc(text)
    return {"path": str(p), "frontmatter": fm, "body": body}


def write_knowledge(
    workspace_root: Path | str,
    *,
    topic: str | None = None,
    summary: str = "",
    tags: list[str] | None = None,
    body: str = "",
    frontmatter: dict[str, Any] | None = None,
    doc: dict[str, Any] | None = None,
    status: str = "candidate",
    created_from_task: str = "",
    atomic: bool = True,  # noqa: ARG001 — kept for API compatibility
) -> Path:
    """Atomically create / overwrite a knowledge file.

    Two call shapes are supported:
        write_knowledge(ws, topic=..., summary=..., tags=[...], body=...)
        write_knowledge(ws, doc={"topic": ..., "frontmatter": {...}, "body": ...})
    """
    if doc is not None:
        topic = topic or doc.get("topic") or doc.get("frontmatter", {}).get("topic")
        frontmatter = frontmatter or doc.get("frontmatter")
        body = body or doc.get("body", "")
    if topic is None:
        raise ValueError("topic is required")
    fm = dict(frontmatter) if frontmatter else {}
    fm.setdefault("topic", topic)
    if summary or "summary" not in fm:
        fm["summary"] = summary or fm.get("summary", "")
    if tags is not None or "tags" not in fm:
        fm["tags"] = list(tags) if tags is not None else fm.get("tags", [])
    fm.setdefault("status", status)
    fm.setdefault("created_from_task", created_from_task)
    fm.setdefault("created_at", _now_iso())
    fm["dedup_hash"] = memory_index.get_hash(body)
    _validate_frontmatter(fm)

    target = _knowledge_path(workspace_root, topic)
    rendered = _render_frontmatter_doc(fm, body)
    _atomic_write_text(target, rendered)
    memory_index.invalidate(workspace_root, target)
    return target


def patch_knowledge(
    workspace_root: Path | str,
    *,
    topic: str,
    mutator: Callable[[dict[str, Any]], dict[str, Any]],
    rationale: str = "",
) -> Path:
    """Read-modify-atomic-write under a per-file fcntl lock.

    *mutator* receives ``{"path", "frontmatter", "body"}`` and must
    return the (possibly modified) same shape. Audit log records
    ``verdict=merge`` with the rationale.
    """
    target = _knowledge_path(workspace_root, topic)
    if not target.is_file():
        raise FileNotFoundError(f"knowledge topic not found: {topic}")
    lock_path = target.with_suffix(target.suffix + ".lock")
    fd = _flock_acquire(lock_path)
    try:
        current = read_knowledge(target)
        new = mutator(current)
        if new is None:
            new = current
        fm = new.get("frontmatter", {})
        body = new.get("body", "")
        fm["dedup_hash"] = memory_index.get_hash(body)
        _validate_frontmatter(fm)
        rendered = _render_frontmatter_doc(fm, body)
        _atomic_write_text(target, rendered)
    finally:
        _flock_release(fd)
        try:
            lock_path.unlink()
        except OSError:
            pass
    memory_index.invalidate(workspace_root, target)
    append_audit(
        workspace_root,
        {
            "ts": _now_iso(),
            "asset_type": "knowledge",
            "topic": topic,
            "verdict": "merge",
            "rationale": rationale,
            "path": str(target),
        },
    )
    return target


def replace_knowledge(
    workspace_root: Path | str,
    *,
    topic: str,
    frontmatter: dict[str, Any],
    body: str,
    rationale: str = "",
) -> Path:
    """Full overwrite (verdict=replace) — used by extractor when LLM picks
    the *replace* branch."""
    fm = dict(frontmatter)
    fm["topic"] = topic
    fm["dedup_hash"] = memory_index.get_hash(body)
    _validate_frontmatter(fm)
    target = _knowledge_path(workspace_root, topic)
    _atomic_write_text(target, _render_frontmatter_doc(fm, body))
    memory_index.invalidate(workspace_root, target)
    append_audit(
        workspace_root,
        {
            "ts": _now_iso(),
            "asset_type": "knowledge",
            "topic": topic,
            "verdict": "replace",
            "rationale": rationale,
            "path": str(target),
        },
    )
    return target


def _set_status(workspace_root: Path | str, path: Path | str, status: str) -> None:
    p = Path(path)
    doc = read_knowledge(p)
    doc["frontmatter"]["status"] = status
    rendered = _render_frontmatter_doc(doc["frontmatter"], doc["body"])
    _atomic_write_text(p, rendered)
    memory_index.invalidate(workspace_root, p)


def promote_knowledge(workspace_root: Path | str, path: Path | str) -> None:
    _set_status(workspace_root, path, "promoted")


def archive_knowledge(workspace_root: Path | str, path: Path | str) -> None:
    _set_status(workspace_root, path, "archived")


# ----------------------------------------------------------------- skills


def scan_skills(workspace_root: Path | str) -> list[dict[str, Any]]:
    return memory_index.build_index(workspace_root)["skills"]


def _skill_md(ws: Path | str, name: str) -> Path:
    if "/" in name or "\\" in name:
        raise ValueError(f"skill name must be flat: {name!r}")
    return _skills_dir(ws) / name / "SKILL.md"


def read_skill(workspace_root: Path | str, name: str) -> dict[str, Any]:
    p = _skill_md(workspace_root, name)
    text = p.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter_doc(text)
    return {"path": str(p), "name": name, "frontmatter": fm, "body": body}


def write_skill(
    workspace_root: Path | str,
    *,
    name: str,
    frontmatter: dict[str, Any],
    body: str,
    status: str = "candidate",
    created_from_task: str = "",
) -> Path:
    fm = dict(frontmatter)
    fm.setdefault("name", name)
    fm.setdefault("status", status)
    fm.setdefault("created_from_task", created_from_task)
    fm.setdefault("created_at", _now_iso())
    fm["dedup_hash"] = memory_index.get_hash(body)
    target = _skill_md(workspace_root, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(target, _render_frontmatter_doc(fm, body))
    memory_index.invalidate(workspace_root, target)
    return target


def patch_skill(
    workspace_root: Path | str,
    *,
    name: str,
    mutator: Callable[[dict[str, Any]], dict[str, Any]],
    rationale: str = "",
) -> Path:
    target = _skill_md(workspace_root, name)
    if not target.is_file():
        raise FileNotFoundError(f"skill not found: {name}")
    lock_path = target.with_suffix(target.suffix + ".lock")
    fd = _flock_acquire(lock_path)
    try:
        current = read_skill(workspace_root, name)
        new = mutator(current) or current
        fm = new.get("frontmatter", {})
        body = new.get("body", "")
        fm["dedup_hash"] = memory_index.get_hash(body)
        _atomic_write_text(target, _render_frontmatter_doc(fm, body))
    finally:
        _flock_release(fd)
        try:
            lock_path.unlink()
        except OSError:
            pass
    memory_index.invalidate(workspace_root, target)
    append_audit(
        workspace_root,
        {
            "ts": _now_iso(),
            "asset_type": "skill",
            "name": name,
            "verdict": "merge",
            "rationale": rationale,
            "path": str(target),
        },
    )
    return target


def promote_skill(workspace_root: Path | str, name: str) -> None:
    p = _skill_md(workspace_root, name)
    doc = read_skill(workspace_root, name)
    doc["frontmatter"]["status"] = "promoted"
    _atomic_write_text(p, _render_frontmatter_doc(doc["frontmatter"], doc["body"]))
    memory_index.invalidate(workspace_root, p)


# ----------------------------------------------------------------- config


def _load_config_yaml(ws: Path | str) -> dict[str, Any]:
    p = _config_path(ws)
    if not p.is_file():
        raise MemoryLayoutError(f"config.yaml missing: {p}")
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ConfigSchemaError("config.yaml top-level must be a mapping")
    if "entries" not in data:
        data["entries"] = []
    if not isinstance(data["entries"], list):
        raise ConfigSchemaError("config.yaml entries must be a list")
    return data


def read_config_entries(workspace_root: Path | str) -> list[dict[str, Any]]:
    """Return the ``entries[]`` list from config.yaml.

    Raises ``ValueError`` (subclass ``ConfigSchemaError``) when two
    entries share the same ``key`` (FR-LAY-6 / AC-LAY-6). The file is
    not modified.
    """
    data = _load_config_yaml(workspace_root)
    seen: set[str] = set()
    for e in data["entries"]:
        if not isinstance(e, dict) or "key" not in e:
            raise ConfigSchemaError(f"malformed config entry: {e!r}")
        k = e["key"]
        if k in seen:
            raise ConfigSchemaError(f"duplicate key in config.yaml: {k!r}")
        seen.add(k)
    return list(data["entries"])


def upsert_config_entry(
    workspace_root: Path | str,
    *,
    entry: dict[str, Any],
    rationale: str = "",
) -> dict[str, Any]:
    """Insert or merge an entry by key (§4.2 — same key → latest value)."""
    if "key" not in entry:
        raise ValueError("entry.key is required")
    cfg_path = _config_path(workspace_root)
    lock_path = cfg_path.with_suffix(cfg_path.suffix + ".lock")
    fd = _flock_acquire(lock_path)
    try:
        data = _load_config_yaml(workspace_root)
        out_entries: list[dict[str, Any]] = []
        merged = False
        for e in data["entries"]:
            if e.get("key") == entry["key"]:
                if merged:
                    raise ConfigSchemaError(f"duplicate key in config.yaml: {entry['key']!r}")
                e = {**e, **entry, "last_used_at": _now_iso()}
                merged = True
            out_entries.append(e)
        if not merged:
            new_entry = {
                "applies_when": "always",
                "summary": "",
                "status": "candidate",
                "created_from_task": "",
                "created_at": _now_iso(),
                "last_used_at": None,
                **entry,
            }
            out_entries.append(new_entry)
        data["entries"] = out_entries
        rendered = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        _atomic_write_text(cfg_path, rendered)
    finally:
        _flock_release(fd)
        try:
            lock_path.unlink()
        except OSError:
            pass
    append_audit(
        workspace_root,
        {
            "ts": _now_iso(),
            "asset_type": "config",
            "key": entry["key"],
            "verdict": "merge" if merged else "create",
            "rationale": rationale,
        },
    )
    return next(e for e in out_entries if e.get("key") == entry["key"])


def promote_config_entry(workspace_root: Path | str, key: str) -> None:
    upsert_config_entry(
        workspace_root,
        entry={"key": key, "status": "promoted"},
        rationale="promote",
    )


# --------------------------------------------------- M9.6 matcher constants

_DEFAULT_ASSET_TYPES = ("knowledge", "skill", "config")
_MATCH_RESULT_CAP = 20

# applies_when tokens are split on commas, pipes, slashes and whitespace
# (see plan.md decision #4 / docs §4.3).
_AW_SPLIT_RE = re.compile(r"[,|/\s]+")
# task brief tokens are non-word splits (lowercased) — mirrors the
# "lowercase, split on non-word" rule from the M9.6 task spec.
_BRIEF_SPLIT_RE = re.compile(r"\W+", re.UNICODE)


def _tokenize_applies_when(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        raw = " ".join(str(v) for v in value)
    else:
        raw = str(value)
    return {t for t in (s.lower() for s in _AW_SPLIT_RE.split(raw)) if t}


def _tokenize_brief(brief: str) -> set[str]:
    return {t for t in (s.lower() for s in _BRIEF_SPLIT_RE.split(brief or "")) if t}


def _config_title(entry: dict[str, Any]) -> str:
    val = entry.get("value")
    if val is None:
        return str(entry.get("key", ""))
    return f"{entry.get('key')}={val}"


def match_entries_for_task(
    workspace_root: Path | str,
    task_brief: str,
    asset_types: list[str] | None = None,
    *,
    cap: int = _MATCH_RESULT_CAP,
    source_task: str = "",
) -> list[dict[str, Any]]:
    """Deterministic ``applies_when`` matcher used by the router-agent.

    Algorithm (M9.6, plan.md decision #4):
      * brief is lowercased and split on non-word boundaries;
      * each entry's ``applies_when`` is split on ``[,|/\\s]+``;
      * ``score = |applies_when_tokens ∩ brief_tokens|``;
      * entries with no ``applies_when`` field are treated as ``score=1``
        when the brief is non-empty (always-applicable, minor relevance);
      * results with ``score == 0`` are dropped;
      * sorted by score desc (stable for equal scores);
      * truncated to *cap* (default 20).

    A single audit record is emitted per call via
    ``extract_audit.audit`` so callers (router-agent) get observability
    without doing extra plumbing.
    """
    types = list(asset_types) if asset_types else list(_DEFAULT_ASSET_TYPES)
    brief_tokens = _tokenize_brief(task_brief)

    out: list[dict[str, Any]] = []

    if not brief_tokens:
        _emit_router_audit(
            workspace_root,
            source_task=source_task,
            matched=0,
            reason="empty brief — no matching attempted",
        )
        return out

    if "knowledge" in types:
        try:
            for meta in scan_knowledge(workspace_root):
                out.append(_score_meta(
                    meta, brief_tokens, asset_type="knowledge",
                    title_from=lambda m: m.get("title") or m.get("topic")
                    or _basename_no_ext(m.get("path", "")),
                    key_from=lambda m: m.get("topic") or _basename_no_ext(
                        m.get("path", "")
                    ),
                ))
        except MemoryLayoutError:
            pass

    if "skill" in types:
        try:
            for meta in scan_skills(workspace_root):
                out.append(_score_meta(
                    meta, brief_tokens, asset_type="skill",
                    title_from=lambda m: m.get("title") or m.get("name")
                    or _basename_no_ext(m.get("path", "")),
                    key_from=lambda m: m.get("name") or _basename_no_ext(
                        m.get("path", "")
                    ),
                ))
        except MemoryLayoutError:
            pass

    if "config" in types:
        try:
            cfg_entries = read_config_entries(workspace_root)
        except (MemoryLayoutError, ConfigSchemaError):
            cfg_entries = []
        for entry in cfg_entries:
            tokens = _tokenize_applies_when(entry.get("applies_when"))
            if "applies_when" not in entry or entry.get("applies_when") in (
                None, "",
            ):
                score = 1
            elif tokens == {"always"}:
                score = 1
            else:
                score = len(tokens & brief_tokens)
            if score <= 0:
                continue
            out.append({
                "asset_type": "config",
                "path": "memory/config.yaml",
                "key": entry.get("key"),
                "title": _config_title(entry),
                "summary": entry.get("summary", ""),
                "applies_when": entry.get("applies_when", ""),
                "score": score,
            })

    out = [r for r in out if r is not None and r["score"] > 0]
    # Stable sort by score desc.
    out.sort(key=lambda r: r["score"], reverse=True)
    if len(out) > cap:
        out = out[:cap]

    _emit_router_audit(
        workspace_root,
        source_task=source_task,
        matched=len(out),
        reason=f"{len(out)} entries matched",
    )
    return out


def _basename_no_ext(p: str) -> str:
    base = os.path.basename(p)
    if base.endswith(".md"):
        base = base[:-3]
    return base


def _score_meta(
    meta: dict[str, Any],
    brief_tokens: set[str],
    *,
    asset_type: str,
    title_from: Callable[[dict[str, Any]], str],
    key_from: Callable[[dict[str, Any]], str],
) -> dict[str, Any] | None:
    aw_raw = meta.get("applies_when")
    if aw_raw is None or aw_raw == "":
        score = 1
        aw_text = ""
    else:
        tokens = _tokenize_applies_when(aw_raw)
        if tokens == {"always"}:
            score = 1
        else:
            score = len(tokens & brief_tokens)
        aw_text = aw_raw if isinstance(aw_raw, str) else ",".join(
            str(v) for v in (aw_raw or [])
        )
    if score <= 0:
        return None
    return {
        "asset_type": asset_type,
        "path": meta.get("path", ""),
        "key": key_from(meta),
        "title": title_from(meta),
        "summary": meta.get("summary", ""),
        "applies_when": aw_text,
        "score": score,
    }


def _emit_router_audit(
    workspace_root: Path | str,
    *,
    source_task: str,
    matched: int,
    reason: str,
) -> None:
    """Single audit line per match call. Lazy-imports extract_audit to
    avoid a circular import (extract_audit imports memory_layer)."""
    try:
        import extract_audit  # noqa: WPS433 — local lazy import
    except ImportError:
        return
    try:
        extract_audit.audit(
            workspace_root,
            asset_type="router",
            outcome="matched",
            verdict="noop",
            reason=reason,
            source_task=source_task,
            extra={"matched_count": matched},
        )
    except (MemoryLayoutError, OSError):
        # Audit failure must never break the matcher.
        pass


# ---------------------------------------------------------------- generic


def _title_token_set(title: str) -> set[str]:
    return {t for t in re.split(r"[^A-Za-z0-9]+", (title or "").lower()) if t}


def find_similar(
    workspace_root: Path | str,
    kind: Literal["knowledge", "skill", "config"],
    title: str,
    tags: list[str] | None = None,
    *,
    tag_overlap_threshold: float = 0.5,
    title_cosine_threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """Return existing entries that look similar to a new candidate.

    Heuristic (token-set Jaccard, per M9.0 decision #1):
      * tag overlap = ``|cand ∩ exist| / max(|cand|, |exist|)``
      * title overlap = same Jaccard over lowercase alphanumeric tokens
    A match is reported when **either** ratio meets its threshold.
    """
    cand_tags = set(tags or [])
    cand_title_tokens = _title_token_set(title)
    if kind == "knowledge":
        candidates = scan_knowledge(workspace_root)
    elif kind == "skill":
        candidates = scan_skills(workspace_root)
    else:
        return []

    out: list[dict[str, Any]] = []
    for meta in candidates:
        existing_tags = set(meta.get("tags") or [])
        existing_title = meta.get("title") or meta.get("name") or ""
        existing_tokens = _title_token_set(existing_title)

        tag_overlap = 0.0
        if cand_tags and existing_tags:
            denom = max(len(cand_tags), len(existing_tags))
            tag_overlap = len(cand_tags & existing_tags) / denom if denom else 0.0

        title_overlap = 0.0
        if cand_title_tokens and existing_tokens:
            denom = max(len(cand_title_tokens), len(existing_tokens))
            title_overlap = (
                len(cand_title_tokens & existing_tokens) / denom if denom else 0.0
            )

        if (
            tag_overlap >= tag_overlap_threshold
            or title_overlap >= title_cosine_threshold
        ):
            out.append(
                {
                    "path": meta.get("path"),
                    "topic": meta.get("topic"),
                    "title": existing_title,
                    "tags": list(existing_tags),
                    "tag_overlap": tag_overlap,
                    "title_overlap": title_overlap,
                    "dedup_hash": meta.get("dedup_hash"),
                }
            )
    return out


def has_hash(workspace_root: Path | str, kind: str, dedup_key: str) -> bool:
    """Return True iff *dedup_key* matches an existing entry's
    ``dedup_hash`` (FR-EXT-DEDUP)."""
    idx = memory_index.build_index(workspace_root)
    bucket = "knowledge" if kind == "knowledge" else "skills"
    for meta in idx.get(bucket, []):
        if meta.get("dedup_hash") == dedup_key:
            return True
    return False


def append_audit(workspace_root: Path | str, entry: dict[str, Any]) -> None:
    """Append a single JSON line to ``history/extraction-log.jsonl``."""
    log_path = _audit_log(workspace_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


# ----------------------------------------------------------------- index


def scan_memory(workspace_root: Path | str) -> dict[str, Any]:
    """Aggregate metadata index used by router-agent (NFR-PERF-1)."""
    idx = memory_index.build_index(workspace_root)
    try:
        idx["config"] = read_config_entries(workspace_root)
    except (MemoryLayoutError, ConfigSchemaError):
        idx["config"] = []
    return idx
