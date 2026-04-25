"""Memory layer (M9.1) — workspace-local writable knowledge / skills /
config store.

Layout (created by the ``init`` builtin skill):

    <workspace>/.codenook/memory/
      ├── knowledge/<topic>.md     # flat layout, single .md per topic
      ├── skills/<name>/SKILL.md   # each promoted skill in its own dir
      ├── config.yaml              # single-file entries[] (version: 1)
      ├── history/extraction-log.jsonl
      └── .index-snapshot.json     # mtime cache (gitignored)

Public API (locked, see docs/memory-and-extraction.md §10):

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


def _refresh_index_yaml(workspace_root: Path | str) -> None:
    """Best-effort refresh of memory/index.yaml. Never raises."""
    try:
        memory_index.export_index_yaml(workspace_root)
    except Exception:
        pass

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


def _atomic_write_text(
    path: Path,
    content: str,
    workspace_root: Path | str | None = None,
) -> None:
    """tempfile + os.replace in the same directory → atomic on POSIX.

    Also enforces the M9.7 plugin read-only invariant: any target that
    resolves under a ``plugins/`` directory raises
    :class:`plugin_readonly.PluginReadOnlyViolation` *before* the
    tempfile is created.

    Pass ``workspace_root`` so the guard scopes its check to within the
    workspace (avoids false-positives when the host checkout itself
    happens to be named ``plugins/``) and so the audit-log record is
    emitted to ``<ws>/.codenook/memory/history/extraction-log.jsonl``.
    """
    from plugin_readonly import assert_writable_path  # local: avoid import cycles

    assert_writable_path(path, workspace_root=workspace_root)
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


# Directory-level sentinel lock paths. Used to serialize the scan +
# fuzzy-match + merge + write sequence in write_knowledge / write_skill
# so two concurrent writers cannot both load pre-merge bodies and
# have os.replace silently drop one side's additions (post-D+E
# review finding 1). Per-file locks in patch_* protect patch-vs-patch;
# the directory lock covers merge-vs-merge and merge-vs-create on the
# same target.
#
# v0.27.6: relocated under <memory>/.locks/ instead of inside the content
# dir so os.listdir(knowledge/) returns only knowledge files (TC-M9.1-05).
def _locks_dir(ws: Path | str) -> Path:
    d = memory_root(ws) / ".locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _knowledge_write_lock(ws: Path | str) -> Path:
    return _locks_dir(ws) / "knowledge.write.lock"


def _skills_write_lock(ws: Path | str) -> Path:
    return _locks_dir(ws) / "skills.write.lock"


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
    fuzzy_merge: bool = True,
) -> Path:
    """Atomically create / overwrite a knowledge file.

    Two call shapes are supported:
        write_knowledge(ws, topic=..., summary=..., tags=[...], body=...)
        write_knowledge(ws, doc={"topic": ..., "frontmatter": {...}, "body": ...})

    When *fuzzy_merge* is True (change E, default) and the target file
    does not already exist, scan existing knowledge for a near-duplicate
    by normalized title / body fingerprint and, if found, merge the new
    evidence into the existing file instead of creating a new topic.
    Callers that must force a fresh write (e.g. tests, or the "replace"
    branch of an extractor decision) can pass ``fuzzy_merge=False``.
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

    # ── Change E: fuzzy-merge on write ──────────────────────────────
    # Locking scheme (post-D+E review finding 1): acquire a
    # directory-level sentinel lock for the entire scan → match →
    # merge → write sequence so concurrent extractors cannot both
    # load a pre-merge body and have os.replace drop one writer's
    # additions. The fresh-file branch (below) is unlocked: each
    # writer targets a distinct topic path there.
    if fuzzy_merge and not target.exists():
        lock_path = _knowledge_write_lock(workspace_root)
        fd = _flock_acquire(lock_path)
        try:
            # Re-check under lock: another writer may have just created
            # this exact topic path.
            if not target.exists():
                title = str(fm.get("title") or topic)
                source_task = str(
                    fm.get("created_from_task") or created_from_task or fm.get("source_task") or ""
                )
                matched = _fuzzy_match_existing_knowledge(workspace_root, title, body)
                if matched is not None:
                    return _merge_into_existing_knowledge(
                        workspace_root,
                        existing=matched,
                        source_task=source_task,
                        new_title=title,
                        new_body=body,
                        new_tags=list(fm.get("tags") or []),
                    )
        finally:
            _flock_release(fd)

    rendered = _render_frontmatter_doc(fm, body)
    _atomic_write_text(target, rendered, workspace_root=workspace_root)
    memory_index.invalidate(workspace_root, target)
    _refresh_index_yaml(workspace_root)
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
        _atomic_write_text(target, rendered, workspace_root=workspace_root)
    finally:
        _flock_release(fd)
        try:
            lock_path.unlink()
        except OSError:
            pass
    memory_index.invalidate(workspace_root, target)
    _refresh_index_yaml(workspace_root)
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
    _atomic_write_text(target, _render_frontmatter_doc(fm, body), workspace_root=workspace_root)
    memory_index.invalidate(workspace_root, target)
    _refresh_index_yaml(workspace_root)
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
    _atomic_write_text(p, rendered, workspace_root=workspace_root)
    memory_index.invalidate(workspace_root, p)
    _refresh_index_yaml(workspace_root)


def promote_knowledge(workspace_root: Path | str, path: Path | str) -> None:
    _set_status(workspace_root, path, "promoted")


def archive_knowledge(workspace_root: Path | str, path: Path | str) -> None:
    _set_status(workspace_root, path, "archived")


# ───────────────────── change E: fuzzy-merge helpers ─────────────────────


def _fuzzy_match_existing_knowledge(
    workspace_root: Path | str, new_title: str, new_body: str
) -> dict[str, Any] | None:
    """Scan existing knowledge for a near-duplicate by title/body fingerprint.

    Returns ``{"path", "frontmatter", "body", "reason", "score"}`` on
    the first hit (stable, alphabetical by filename via
    :func:`scan_knowledge`), or None when nothing is close enough.

    Finding 7 (review): bodies are cached by (path, mtime_ns) for the
    lifetime of the process so a single extractor batch that writes N
    topics does N disk-reads in total instead of O(N²). TODO: promote
    to a proper body index once memory grows > 200 entries.
    """
    try:
        import text_fingerprint as tf  # local: _lib is on sys.path
    except ImportError:
        return None
    for meta in scan_knowledge(workspace_root):
        ex_path = meta.get("path")
        if not ex_path:
            continue
        doc = _read_knowledge_cached(ex_path)
        if doc is None:
            continue
        ex_title = (
            doc["frontmatter"].get("title")
            or doc["frontmatter"].get("topic")
            or Path(ex_path).stem
        )
        ex_body = doc["body"] or ""
        matched, reason, score = tf.is_fuzzy_match(
            new_title, new_body, str(ex_title), ex_body
        )
        if matched:
            return {
                "path": ex_path,
                "frontmatter": doc["frontmatter"],
                "body": ex_body,
                "reason": reason,
                "score": score,
            }
    return None


# ── Body cache for fuzzy-match scans (finding 7) ────────────────────
# Module-level dict keyed by (path, mtime_ns). Invalidates automatically
# on mtime change, so atomic writes from this same process that bump
# mtime_ns will trigger a re-read on the next scan.
_BODY_CACHE: dict[tuple[str, int], dict[str, Any]] = {}


def _read_knowledge_cached(path: str | Path) -> dict[str, Any] | None:
    try:
        mtime_ns = os.stat(str(path)).st_mtime_ns
    except OSError:
        return None
    key = (str(path), mtime_ns)
    cached = _BODY_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        doc = read_knowledge(path)
    except OSError:
        return None
    _BODY_CACHE[key] = doc
    return doc


def _read_skill_cached(workspace_root: Path | str, name: str, path: str | Path) -> dict[str, Any] | None:
    try:
        mtime_ns = os.stat(str(path)).st_mtime_ns
    except OSError:
        return None
    key = (str(path), mtime_ns)
    cached = _BODY_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        doc = read_skill(workspace_root, name)
    except OSError:
        return None
    _BODY_CACHE[key] = doc
    return doc


def _append_source_ref(fm: dict[str, Any], source_task: str) -> bool:
    """Append *source_task* to frontmatter's ``sources`` list (dedup).

    Returns True when the list actually grew. Also mirrors into
    ``related_tasks`` for back-compat with existing readers.
    """
    changed = False
    if not source_task:
        return False
    sources = list(fm.get("sources") or [])
    if source_task not in sources:
        sources.append(source_task)
        fm["sources"] = sources
        changed = True
    related = list(fm.get("related_tasks") or [])
    if source_task not in related:
        related.append(source_task)
        fm["related_tasks"] = related
        changed = True
    return changed


def _merge_tags_into(fm: dict[str, Any], new_tags: list[str]) -> None:
    existing_tags = list(fm.get("tags") or [])
    for t in new_tags or []:
        if isinstance(t, str) and t and t not in existing_tags:
            existing_tags.append(t)
    fm["tags"] = existing_tags[:MAX_TAGS]


def _merge_into_existing_knowledge(
    workspace_root: Path | str,
    *,
    existing: dict[str, Any],
    source_task: str,
    new_title: str,
    new_body: str,
    new_tags: list[str] | None = None,
) -> Path:
    """Fold new evidence into an existing knowledge file in-place.

    Policy:
      * always append *source_task* under ``sources:`` (dedup).
      * if ≥ 20% of the new body's shingles are absent from the existing
        body, append a dated "Update — <task> — <iso>" section; else
        only record the source link.
    """
    import text_fingerprint as tf

    ex_path = Path(existing["path"])
    fm = dict(existing.get("frontmatter") or {})
    body = existing.get("body") or ""

    _append_source_ref(fm, source_task)
    _merge_tags_into(fm, list(new_tags or []))

    # Record the fuzzy match reason/score for audit traceability.
    match_reason = str(existing.get("reason") or "")
    match_score = existing.get("score")

    ratio = tf.new_content_ratio(new_body, body)
    body_changed = False
    if ratio >= tf.MATERIAL_NEW_RATIO and (new_body or "").strip():
        header = f"## Update — {source_task or 'unknown'} — {_now_iso()}"
        note = (new_title.strip() + "\n\n") if new_title else ""
        addition = f"\n\n{header}\n\n{note}{new_body.strip()}\n"
        body = body.rstrip() + addition
        body_changed = True

    fm["dedup_hash"] = memory_index.get_hash(body)
    _validate_frontmatter(fm)
    rendered = _render_frontmatter_doc(fm, body)
    _atomic_write_text(ex_path, rendered, workspace_root=workspace_root)
    memory_index.invalidate(workspace_root, ex_path)
    _refresh_index_yaml(workspace_root)
    append_audit(
        workspace_root,
        {
            "ts": _now_iso(),
            "asset_type": "knowledge",
            "topic": fm.get("topic") or ex_path.stem,
            "verdict": "fuzzy_merge",
            "rationale": (
                f"match={match_reason} score={match_score} "
                f"new_ratio={ratio:.2f} body_changed={body_changed}"
            )[:200],
            "path": str(ex_path),
            "source_task": source_task,
        },
    )
    return ex_path


def append_by_role_reference(
    workspace_root: Path | str,
    *,
    topic: str,
    role: str,
    source_task: str = "",
) -> Path | None:
    """Record a *role* as a contributing source for an existing knowledge
    topic, without duplicating any body content.

    This is the "by_role/<role>.md points at the same by_topic content"
    invariant expressed in change D: one canonical content file, many
    per-role references via the ``sources_by_role`` frontmatter list.

    Returns the topic path on success, or None when the topic does not
    exist. Best-effort — never raises into the caller.
    """
    try:
        target = _knowledge_path(workspace_root, topic)
    except ValueError:
        return None
    if not target.is_file():
        return None

    def _mutate(doc: dict[str, Any]) -> dict[str, Any]:
        fm = dict(doc.get("frontmatter") or {})
        roles = list(fm.get("sources_by_role") or [])
        if role and role not in roles:
            roles.append(role)
            fm["sources_by_role"] = roles
        _append_source_ref(fm, source_task)
        return {"frontmatter": fm, "body": doc.get("body", "")}

    try:
        return patch_knowledge(
            workspace_root, topic=topic, mutator=_mutate,
            rationale=f"by_role-ref role={role}",
        )
    except (FileNotFoundError, ValueError):
        # Expected not-found / validation failure modes: fall through
        # silently — the caller treats None as "topic unavailable".
        return None
    except Exception as e:  # noqa: BLE001 — see comment
        # Finding 5 (review): keep the best-effort contract (never raise
        # into the caller) but leave an audit breadcrumb so lock
        # timeouts and other real failures are distinguishable from
        # "topic didn't exist".
        try:
            append_audit(
                workspace_root,
                {
                    "ts": _now_iso(),
                    "asset_type": "knowledge",
                    "topic": topic,
                    "verdict": "by_role_reference_failed",
                    "reason": f"{type(e).__name__}: {e}"[:200],
                    "role": role,
                    "source_task": source_task,
                },
            )
        except Exception:
            pass
        return None


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
    fuzzy_merge: bool = True,
) -> Path:
    fm = dict(frontmatter)
    fm.setdefault("name", name)
    fm.setdefault("status", status)
    fm.setdefault("created_from_task", created_from_task)
    fm.setdefault("created_at", _now_iso())
    fm["dedup_hash"] = memory_index.get_hash(body)
    target = _skill_md(workspace_root, name)

    # ── Change E: fuzzy-merge on write (skills) ─────────────────────
    # See write_knowledge for locking rationale — same scheme applied
    # to the skills tree.
    if fuzzy_merge and not target.exists():
        lock_path = _skills_write_lock(workspace_root)
        fd = _flock_acquire(lock_path)
        try:
            if not target.exists():
                title = str(fm.get("title") or fm.get("name") or name)
                source_task = str(
                    fm.get("created_from_task") or created_from_task or fm.get("source_task") or ""
                )
                matched = _fuzzy_match_existing_skill(workspace_root, title, body)
                if matched is not None:
                    return _merge_into_existing_skill(
                        workspace_root,
                        existing=matched,
                        source_task=source_task,
                        new_title=title,
                        new_body=body,
                        new_tags=list(fm.get("tags") or []),
                    )
        finally:
            _flock_release(fd)

    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(target, _render_frontmatter_doc(fm, body), workspace_root=workspace_root)
    memory_index.invalidate(workspace_root, target)
    _refresh_index_yaml(workspace_root)
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
        _atomic_write_text(target, _render_frontmatter_doc(fm, body), workspace_root=workspace_root)
    finally:
        _flock_release(fd)
        try:
            lock_path.unlink()
        except OSError:
            pass
    memory_index.invalidate(workspace_root, target)
    _refresh_index_yaml(workspace_root)
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
    _atomic_write_text(p, _render_frontmatter_doc(doc["frontmatter"], doc["body"]), workspace_root=workspace_root)
    memory_index.invalidate(workspace_root, p)
    _refresh_index_yaml(workspace_root)


def _fuzzy_match_existing_skill(
    workspace_root: Path | str, new_title: str, new_body: str
) -> dict[str, Any] | None:
    """Skill-side counterpart of :func:`_fuzzy_match_existing_knowledge`."""
    try:
        import text_fingerprint as tf
    except ImportError:
        return None
    for meta in scan_skills(workspace_root):
        ex_path = meta.get("path")
        name = meta.get("name") or (
            Path(ex_path).parent.name if ex_path else ""
        )
        if not name or not ex_path:
            continue
        doc = _read_skill_cached(workspace_root, name, ex_path)
        if doc is None:
            continue
        ex_title = (
            doc["frontmatter"].get("title")
            or doc["frontmatter"].get("name")
            or name
        )
        ex_body = doc["body"] or ""
        matched, reason, score = tf.is_fuzzy_match(
            new_title, new_body, str(ex_title), ex_body
        )
        if matched:
            return {
                "path": ex_path,
                "name": name,
                "frontmatter": doc["frontmatter"],
                "body": ex_body,
                "reason": reason,
                "score": score,
            }
    return None


def _merge_into_existing_skill(
    workspace_root: Path | str,
    *,
    existing: dict[str, Any],
    source_task: str,
    new_title: str,
    new_body: str,
    new_tags: list[str] | None = None,
) -> Path:
    """Fold new evidence into an existing skill file in-place (see
    :func:`_merge_into_existing_knowledge` for policy)."""
    import text_fingerprint as tf

    ex_path = Path(existing["path"])
    fm = dict(existing.get("frontmatter") or {})
    body = existing.get("body") or ""

    _append_source_ref(fm, source_task)
    _merge_tags_into(fm, list(new_tags or []))

    match_reason = str(existing.get("reason") or "")
    match_score = existing.get("score")

    ratio = tf.new_content_ratio(new_body, body)
    body_changed = False
    if ratio >= tf.MATERIAL_NEW_RATIO and (new_body or "").strip():
        header = f"## Update — {source_task or 'unknown'} — {_now_iso()}"
        note = (new_title.strip() + "\n\n") if new_title else ""
        body = body.rstrip() + f"\n\n{header}\n\n{note}{new_body.strip()}\n"
        body_changed = True

    fm["dedup_hash"] = memory_index.get_hash(body)
    rendered = _render_frontmatter_doc(fm, body)
    _atomic_write_text(ex_path, rendered, workspace_root=workspace_root)
    memory_index.invalidate(workspace_root, ex_path)
    _refresh_index_yaml(workspace_root)
    append_audit(
        workspace_root,
        {
            "ts": _now_iso(),
            "asset_type": "skill",
            "name": existing.get("name") or ex_path.parent.name,
            "verdict": "fuzzy_merge",
            "rationale": (
                f"match={match_reason} score={match_score} "
                f"new_ratio={ratio:.2f} body_changed={body_changed}"
            )[:200],
            "path": str(ex_path),
            "source_task": source_task,
        },
    )
    return ex_path


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
        _atomic_write_text(cfg_path, rendered, workspace_root=workspace_root)
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
                    workspace_root=workspace_root,
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
                    workspace_root=workspace_root,
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
            aw_raw = entry.get("applies_when")
            tokens = _tokenize_applies_when(aw_raw)
            if (
                "applies_when" not in entry
                or aw_raw in (None, "")
                or (isinstance(aw_raw, list) and not aw_raw)
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
    workspace_root: Path | str,
    title_from: Callable[[dict[str, Any]], str],
    key_from: Callable[[dict[str, Any]], str],
) -> dict[str, Any] | None:
    aw_raw = meta.get("applies_when")
    if aw_raw is None or aw_raw == "" or (
        isinstance(aw_raw, list) and not aw_raw
    ):
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
        "path": _normalize_meta_path(meta.get("path", ""), workspace_root),
        "key": key_from(meta),
        "title": title_from(meta),
        "summary": meta.get("summary", ""),
        "applies_when": aw_text,
        "score": score,
    }


def _normalize_meta_path(
    raw_path: str, workspace_root: Path | str
) -> str:
    """Convert an absolute on-disk asset path to its workspace-relative
    form (``memory/...``). Falls back to the basename and audits a
    warning if the path falls outside the expected ``.codenook`` root
    (defensive — should not happen in normal flow)."""
    if not raw_path:
        return ""
    p = Path(raw_path)
    base = Path(workspace_root) / ".codenook"
    try:
        return str(p.relative_to(base))
    except ValueError:
        try:
            _emit_router_audit(
                workspace_root,
                source_task="-",
                matched=0,
                reason=(
                    f"meta path outside workspace .codenook root: "
                    f"{raw_path}"
                ),
            )
        except Exception:
            pass
        return p.name


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
    """Append a single JSON line to ``history/extraction-log.jsonl``.

    Concurrency: lines may exceed ``PIPE_BUF`` (4 KiB on Linux,
    smaller on some BSDs), so a plain ``O_APPEND`` write is **not**
    atomic across concurrent writers (extractor + HITL decide can race).
    Pass-2 P2 #6 fix: take an exclusive ``fcntl.flock`` on the log file
    for the duration of the write so the JSONL stays parseable.
    Falls back to plain append on platforms without ``fcntl`` (Windows).
    """
    log_path = _audit_log(workspace_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    try:
        import fcntl  # POSIX only
    except ImportError:
        fcntl = None  # type: ignore[assignment]
    with open(log_path, "a", encoding="utf-8") as f:
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line)
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        else:
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


# ─────────────────────────── task-extracted bucket (routing feature) ──────


def task_extracted_root(workspace_root: Path | str, task_id: str) -> Path:
    """Return the per-task extracted artefact root directory.

    Layout::

        <workspace>/.codenook/tasks/<task_id>/extracted/
          ├── knowledge/<topic>.md
          ├── skills/<name>/SKILL.md
          └── config.yaml
    """
    return Path(workspace_root) / CODENOOK_DIRNAME / "tasks" / task_id / "extracted"


def _task_knowledge_dir(ws: Path | str, task_id: str) -> Path:
    return task_extracted_root(ws, task_id) / "knowledge"


def _task_skills_dir(ws: Path | str, task_id: str) -> Path:
    return task_extracted_root(ws, task_id) / "skills"


def _task_config_path(ws: Path | str, task_id: str) -> Path:
    return task_extracted_root(ws, task_id) / "config.yaml"


def has_task_extracted(workspace_root: Path | str, task_id: str) -> bool:
    """True when the per-task extracted skeleton exists."""
    root = task_extracted_root(workspace_root, task_id)
    return root.is_dir() and (_task_config_path(workspace_root, task_id)).exists()


def init_task_extracted_skeleton(workspace_root: Path | str, task_id: str) -> None:
    """Create the empty per-task extracted skeleton."""
    root = task_extracted_root(workspace_root, task_id)
    for sub in (
        root,
        _task_knowledge_dir(workspace_root, task_id),
        _task_skills_dir(workspace_root, task_id),
    ):
        sub.mkdir(parents=True, exist_ok=True)
    cfg = _task_config_path(workspace_root, task_id)
    if not cfg.exists():
        cfg.write_text(_EMPTY_CONFIG, encoding="utf-8")


def _task_knowledge_path(ws: Path | str, task_id: str, topic: str) -> Path:
    _validate_topic(topic)
    return _task_knowledge_dir(ws, task_id) / f"{topic}.md"


def _task_skill_md(ws: Path | str, task_id: str, name: str) -> Path:
    if "/" in name or "\\" in name:
        raise ValueError(f"skill name must be flat: {name!r}")
    return _task_skills_dir(ws, task_id) / name / "SKILL.md"


def scan_task_knowledge(workspace_root: Path | str, task_id: str) -> list[dict[str, Any]]:
    """Return frontmatter metadata for per-task extracted knowledge entries."""
    k_dir = _task_knowledge_dir(workspace_root, task_id)
    if not k_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(k_dir.glob("*.md")):
        if p.name.startswith("."):
            continue
        try:
            text = p.read_text(encoding="utf-8")
            fm, _ = _parse_frontmatter_doc(text)
        except OSError:
            fm = {}
        meta = {"path": str(p)}
        meta.update(fm)
        out.append(meta)
    return out


def scan_task_skills(workspace_root: Path | str, task_id: str) -> list[dict[str, Any]]:
    """Return frontmatter metadata for per-task extracted skill entries."""
    s_dir = _task_skills_dir(workspace_root, task_id)
    if not s_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for sdir in sorted(s_dir.iterdir()):
        if sdir.name.startswith(".") or not sdir.is_dir():
            continue
        skill_md = sdir / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
            fm, _ = _parse_frontmatter_doc(text)
        except OSError:
            fm = {}
        meta = {"path": str(skill_md), "name": sdir.name}
        meta.update(fm)
        out.append(meta)
    return out


def read_task_config_entries(workspace_root: Path | str, task_id: str) -> list[dict[str, Any]]:
    """Return entries[] from the per-task config.yaml."""
    p = _task_config_path(workspace_root, task_id)
    if not p.is_file():
        return []
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        return []
    entries = data.get("entries") or []
    if not isinstance(entries, list):
        return []
    seen: set[str] = set()
    for e in entries:
        if not isinstance(e, dict) or "key" not in e:
            raise ConfigSchemaError(f"malformed task config entry: {e!r}")
        k = e["key"]
        if k in seen:
            raise ConfigSchemaError(f"duplicate key in task config.yaml: {k!r}")
        seen.add(k)
    return list(entries)


def has_hash_in_task(
    workspace_root: Path | str, task_id: str, kind: str, dedup_key: str
) -> bool:
    """True iff *dedup_key* already exists in the per-task extracted bucket."""
    if kind == "knowledge":
        metas = scan_task_knowledge(workspace_root, task_id)
    elif kind == "skill":
        metas = scan_task_skills(workspace_root, task_id)
    else:
        return False
    return any(m.get("dedup_hash") == dedup_key for m in metas)


def find_similar_in_task(
    workspace_root: Path | str,
    task_id: str,
    kind: Literal["knowledge", "skill"],
    title: str,
    tags: list[str] | None = None,
    *,
    tag_overlap_threshold: float = 0.5,
    title_cosine_threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """Return similar entries within the per-task extracted bucket."""
    cand_tags = set(tags or [])
    cand_title_tokens = _title_token_set(title)
    candidates = (
        scan_task_knowledge(workspace_root, task_id)
        if kind == "knowledge"
        else scan_task_skills(workspace_root, task_id)
    )
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
                    "name": meta.get("name"),
                    "title": existing_title,
                    "tags": list(existing_tags),
                    "tag_overlap": tag_overlap,
                    "title_overlap": title_overlap,
                    "dedup_hash": meta.get("dedup_hash"),
                }
            )
    return out


def build_task_context(workspace_root: Path | str, task_id: str) -> str:
    """Build the ``{{TASK_CONTEXT}}`` prompt slot content.

    Scans ``tasks/<task_id>/extracted/`` and returns a markdown section
    listing every artefact found.  Returns an empty string when the
    directory is absent or empty so templates that include the slot do
    not emit a spurious header.
    """
    extracted_dir = task_extracted_root(workspace_root, task_id)
    if not extracted_dir.is_dir():
        return ""

    lines: list[str] = []

    k_dir = extracted_dir / "knowledge"
    if k_dir.is_dir():
        for p in sorted(k_dir.glob("*.md")):
            if p.name.startswith("."):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            fm, body = _parse_frontmatter_doc(text)
            desc = str(fm.get("summary") or "")
            if not desc:
                for line in (body or "").splitlines():
                    if line.strip():
                        desc = line.strip()[:80]
                        break
            lines.append(f"- knowledge/{p.name}  — {desc}")

    s_dir = extracted_dir / "skills"
    if s_dir.is_dir():
        for sdir in sorted(s_dir.iterdir()):
            if sdir.name.startswith(".") or not sdir.is_dir():
                continue
            skill_md = sdir / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            fm, body = _parse_frontmatter_doc(text)
            desc = str(fm.get("summary") or "")
            if not desc:
                for line in (body or "").splitlines():
                    if line.strip():
                        desc = line.strip()[:80]
                        break
            lines.append(f"- skills/{sdir.name}/SKILL.md — {desc}")

    cfg_path = extracted_dir / "config.yaml"
    if cfg_path.is_file():
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            for e in (data.get("entries") or [])[:5]:
                if isinstance(e, dict) and "key" in e:
                    lines.append(
                        f"- config: {e['key']}={e.get('value')!r}"
                    )
        except Exception:
            pass

    if not lines:
        return ""

    return "## Task-extracted context\n" + "\n".join(lines) + "\n"
