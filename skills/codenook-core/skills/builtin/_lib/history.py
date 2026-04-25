"""``history`` — manual + auto session-history snapshots (v0.29.0).

Two flavors of snapshot live side-by-side:

* **Memory snapshots** — ``.codenook/memory/history/<ISO>-<slug>/`` are
  created when the user explicitly says "save context" / "保存上下文"
  via ``codenook history save --description "..."``. The conductor
  passes the conversation body via ``--content-file`` or stdin. No
  dedup — every save creates a new directory.

* **Task snapshots** — ``.codenook/tasks/<T-NNN>/history/<ISO>-<phase>-<slug>/``
  are created automatically by ``codenook tick`` after every phase
  advance / terminal status. Best-effort; never blocks tick exit.

Each snapshot directory has the same shape::

    <stamp_dir>/
      meta.json    {timestamp, kind, scope, phase?, status?, description?, slug}
      content.md   the snapshot body (may be empty for auto snapshots)

Retention is handled by :func:`prune` (default: 10 days, all scopes).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
from pathlib import Path
from typing import Iterable


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _stamp(now: _dt.datetime | None = None) -> str:
    """Filesystem-safe ISO-8601 stamp (UTC, second precision)."""
    n = now or _now_utc()
    return n.strftime("%Y-%m-%dT%H-%M-%SZ")


def slugify(text: str, fallback: str = "snap") -> str:
    s = _SLUG_RE.sub("-", (text or "").strip().lower()).strip("-")
    return (s or fallback)[:48]


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _write_meta(snap_dir: Path, meta: dict) -> None:
    _atomic_write_text(snap_dir / "meta.json",
                       json.dumps(meta, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------- save (memory)
def save_memory_snapshot(workspace: Path, description: str,
                         content: str = "",
                         now: _dt.datetime | None = None) -> Path:
    """Materialise a manual memory snapshot.

    Returns the new snapshot directory. Always creates a fresh dir
    (no dedup); callers wanting dedup should check existence first.
    """
    n = now or _now_utc()
    slug = slugify(description, fallback="save")
    name = f"{_stamp(n)}-{slug}"
    snap_dir = workspace / ".codenook" / "memory" / "history" / name
    snap_dir.mkdir(parents=True, exist_ok=False)
    _write_meta(snap_dir, {
        "timestamp": n.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": "manual",
        "scope": "memory",
        "description": description,
        "slug": slug,
    })
    _atomic_write_text(snap_dir / "content.md", content or "")
    return snap_dir


# ---------------------------------------------------------------- auto (task)
def snapshot_task_phase(workspace: Path, task_id: str, phase: str,
                        status: str,
                        now: _dt.datetime | None = None) -> Path | None:
    """Auto-snapshot a single phase advance under
    ``.codenook/tasks/<task_id>/history/<ISO>-<phase>-<slug>/``.

    Best-effort: returns ``None`` on any I/O / validation failure so
    callers (notably ``orchestrator-tick.after_phase``) never block.
    """
    if not task_id:
        return None
    n = now or _now_utc()
    safe_phase = slugify(phase or "phase", fallback="phase")
    slug = slugify(status or "tick", fallback="tick")
    name = f"{_stamp(n)}-{safe_phase}-{slug}"
    task_root = workspace / ".codenook" / "tasks" / task_id
    if not task_root.is_dir():
        return None
    snap_dir = task_root / "history" / name
    try:
        snap_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        # Sub-second collision (rare) — fall back to a numeric suffix.
        for i in range(1, 100):
            cand = snap_dir.with_name(snap_dir.name + f"-{i}")
            try:
                cand.mkdir(parents=True, exist_ok=False)
                snap_dir = cand
                break
            except FileExistsError:
                continue
        else:
            return None
    meta = {
        "timestamp": n.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": "auto",
        "scope": "task",
        "task_id": task_id,
        "phase": phase or "",
        "status": status or "",
        "slug": safe_phase,
    }
    _write_meta(snap_dir, meta)
    # Best-effort: include the latest history entry from state.json so
    # the snapshot has a meaningful body rather than just metadata.
    body_lines = [
        f"# Phase snapshot: {task_id} / {phase or '(unknown)'} / {status}",
        "",
        f"_Captured at {meta['timestamp']} (auto)._",
        "",
    ]
    state_p = task_root / "state.json"
    if state_p.is_file():
        try:
            state = json.loads(state_p.read_text(encoding="utf-8"))
        except Exception:
            state = {}
        history = state.get("history") if isinstance(state, dict) else None
        if isinstance(history, list) and history:
            last = history[-1]
            body_lines.append("## Last history entry")
            body_lines.append("")
            body_lines.append("```json")
            body_lines.append(json.dumps(last, ensure_ascii=False, indent=2))
            body_lines.append("```")
            body_lines.append("")
    # R5 fix: also embed the corresponding phase output file so the
    # snapshot is a usable forensic artifact rather than metadata-only.
    # Match by filename pattern phase-<N>-<role>.md under outputs/.
    outputs_dir = task_root / "outputs"
    if outputs_dir.is_dir() and phase:
        # Find any output file whose name contains the phase id.
        # phases.yaml convention is phase-<N>-<role>.md and the role
        # name doesn't always match the phase id (e.g. test-plan -> test-planner).
        # So we accept either contains-phase or contains-<role-from-history>.
        candidates = sorted(outputs_dir.glob(f"phase-*.md"))
        # Prefer files whose basename includes the phase token.
        phase_token = phase.replace("_", "-")
        matched = [p for p in candidates
                   if phase_token in p.stem or p.stem.endswith(f"-{phase}")]
        # Fallback: pick the most recently modified output file.
        if not matched and candidates:
            matched = [max(candidates, key=lambda x: x.stat().st_mtime)]
        for op in matched[:1]:  # only embed one to keep snapshots small
            try:
                body_lines.append(f"## Phase output: `{op.name}`")
                body_lines.append("")
                body_lines.append("```markdown")
                # Truncate large outputs to keep snapshot bounded.
                t = op.read_text(encoding="utf-8")
                if len(t) > 8000:
                    t = t[:8000] + "\n\n…[truncated, original " + str(len(t)) + " chars]"
                body_lines.append(t)
                body_lines.append("```")
                body_lines.append("")
            except Exception:
                pass
    _atomic_write_text(snap_dir / "content.md", "\n".join(body_lines))
    return snap_dir


# ---------------------------------------------------------------- list
def list_snapshots(workspace: Path, scope: str = "all") -> list[dict]:
    """Return snapshot metadata across the requested scope.

    *scope* is one of ``memory``, ``tasks``, or ``all``.
    Each entry is ``{path, scope, timestamp, kind, slug, ...meta}``.
    """
    out: list[dict] = []
    if scope in ("memory", "all"):
        out.extend(_iter_dir(workspace / ".codenook" / "memory" / "history",
                             default_scope="memory"))
    if scope in ("tasks", "all"):
        tasks_root = workspace / ".codenook" / "tasks"
        if tasks_root.is_dir():
            for tdir in sorted(tasks_root.iterdir(), key=lambda p: p.name):
                if not tdir.is_dir():
                    continue
                out.extend(_iter_dir(tdir / "history",
                                     default_scope="task",
                                     extra={"task_id": tdir.name}))
    out.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return out


def _iter_dir(history_dir: Path, default_scope: str,
              extra: dict | None = None) -> Iterable[dict]:
    if not history_dir.is_dir():
        return []
    out: list[dict] = []
    for sub in sorted(history_dir.iterdir(), key=lambda p: p.name):
        if not sub.is_dir():
            continue
        meta_p = sub / "meta.json"
        meta: dict = {}
        if meta_p.is_file():
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        meta.setdefault("scope", default_scope)
        meta["path"] = str(sub)
        if extra:
            meta.update(extra)
        out.append(meta)
    return out


# ---------------------------------------------------------------- prune
def prune(workspace: Path, days: int = 10, scope: str = "all",
          now: _dt.datetime | None = None) -> list[Path]:
    """Delete snapshots older than *days*. Returns deleted paths.

    Snapshots without a parseable timestamp are KEPT (better safe).
    """
    n = now or _now_utc()
    cutoff = n - _dt.timedelta(days=days)
    deleted: list[Path] = []
    for entry in list_snapshots(workspace, scope=scope):
        ts = entry.get("timestamp")
        if not isinstance(ts, str):
            continue
        try:
            stamp = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=_dt.timezone.utc)
        except ValueError:
            # Fall back to parsing the directory-name stamp.
            try:
                base = Path(entry["path"]).name.split("-", 4)
                # name format: YYYY-MM-DDTHH-MM-SSZ-<slug...>
                if len(base) >= 4:
                    stamp_str = "-".join(base[:4]).rstrip("Z") + "Z"
                    stamp = _dt.datetime.strptime(
                        stamp_str, "%Y-%m-%dT%H-%M-%SZ"
                    ).replace(tzinfo=_dt.timezone.utc)
                else:
                    continue
            except Exception:
                continue
        if stamp < cutoff:
            p = Path(entry["path"])
            try:
                shutil.rmtree(p)
                deleted.append(p)
            except OSError:
                continue
    return deleted
