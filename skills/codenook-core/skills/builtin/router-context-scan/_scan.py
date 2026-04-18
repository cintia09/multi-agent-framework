#!/usr/bin/env python3
"""router-context-scan core. Invoked by scan.sh.

Walks the workspace once and emits a compact JSON envelope.

Bounded walks: file-count and byte-count walks short-circuit as soon
as they exceed their warning threshold so this skill stays cheap to
call on every router invocation (architecture §4 — "lightweight,
fast").
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow imports from the sibling _lib/ package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from manifest_load import load_all  # noqa: E402

FILE_WARN_THRESHOLD  = 10_000
BYTES_WARN_THRESHOLD = 100 * 1024 * 1024  # 100 MB
DONE_STATUSES = {"done", "cancelled", "abandoned"}


def collect_active_tasks(ws: Path, max_tasks: int) -> list[dict]:
    tdir = ws / ".codenook" / "tasks"
    if not tdir.is_dir():
        return []
    out = []
    for child in sorted(tdir.iterdir()):
        if not child.is_dir():
            continue
        sf = child / "state.json"
        if not sf.is_file():
            continue
        try:
            with sf.open("r", encoding="utf-8") as f:
                st = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if (st.get("status") or "in_progress") in DONE_STATUSES:
            continue
        out.append({
            "task_id":      st.get("task_id") or child.name,
            "plugin":       st.get("plugin"),
            "phase":        st.get("phase"),
            "last_tick_at": st.get("last_tick_at"),
            "subtasks_n":   len(st.get("subtasks") or []),
        })
    return out[:max_tasks]


def count_hitl(ws: Path) -> int:
    qdir = ws / ".codenook" / "hitl-queue"
    if not qdir.is_dir():
        return 0
    return sum(1 for c in qdir.iterdir() if c.is_file() and c.suffix == ".json")


def scan_workspace_size(ws: Path) -> list[str]:
    """Return warnings; bounded walk that stops at the first triggered limit."""
    warnings: list[str] = []
    files_n = 0
    bytes_n = 0
    over_files = False
    over_bytes = False
    for root, dirs, files in os.walk(ws):
        # Skip the audit/history tree to keep the walk cheap-ish; it
        # can grow large but isn't user payload.
        if ".git" in dirs:
            dirs.remove(".git")
        for fn in files:
            files_n += 1
            if files_n > FILE_WARN_THRESHOLD:
                over_files = True
            if not over_bytes:
                try:
                    bytes_n += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
                if bytes_n > BYTES_WARN_THRESHOLD:
                    over_bytes = True
            if over_files and over_bytes:
                break
        if over_files and over_bytes:
            break
    if over_files:
        warnings.append(f">10K files in workspace ({files_n}+ files)")
    if over_bytes:
        warnings.append(f">100MB on disk in workspace")
    return warnings


def main() -> int:
    ws = Path(os.environ["CN_WORKSPACE"]).resolve()
    max_tasks = int(os.environ["CN_MAX_TASKS"])

    plugins = []
    for m in load_all(ws):
        plugins.append({"id": m.get("id"), "version": m.get("version")})

    tasks_full = collect_active_tasks(ws, max_tasks)
    fanout = sum(t.pop("subtasks_n", 0) for t in tasks_full)

    out = {
        "installed_plugins":  plugins,
        "active_tasks":       tasks_full,
        "hitl_pending":       count_hitl(ws),
        "fanout_pending":     fanout,
        "workspace_warnings": scan_workspace_size(ws),
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
