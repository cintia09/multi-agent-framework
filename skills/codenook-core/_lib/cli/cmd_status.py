"""``codenook status`` — read state.json and per-task summaries."""
from __future__ import annotations

import json
import sys
from typing import Sequence

from .config import CodenookContext, iter_active_task_dirs


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    task = ""
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            else:
                sys.stderr.write(f"codenook status: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook status: missing value for last flag\n")
        return 2

    if task:
        f = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
        if not f.is_file():
            sys.stderr.write(f"codenook status: no such task: {task}\n")
            return 1
        sys.stdout.write(f.read_text(encoding="utf-8"))
        return 0

    print(f"Workspace: {ctx.workspace}")
    sys.stdout.write(ctx.state_file.read_text(encoding="utf-8"))
    sys.stdout.write("\n")

    # Lazy-import models so a corrupt model module never blocks `status`.
    try:
        from .. import models  # type: ignore
        _resolve = models.resolve_model  # type: ignore[attr-defined]
    except Exception:
        _resolve = None  # graceful degrade — model column shows <unknown>

    tasks_dir = ctx.workspace / ".codenook" / "tasks"
    rows = []
    for d in iter_active_task_dirs(tasks_dir):
        sf = d / "state.json"
        try:
            s = json.loads(sf.read_text(encoding="utf-8"))
            ph = s.get("phase") or "<none>"
            st = s.get("status") or "?"
            ex = s.get("execution_mode") or "sub-agent"
            pr = s.get("profile") or "<auto>"
            md = "<unknown>"
            if _resolve is not None:
                try:
                    md = (_resolve(ctx.workspace, s.get("plugin") or "",
                                   s.get("phase") or "", s)
                          or "<default>")
                except Exception:
                    md = "<unknown>"
        except Exception:
            ph, st, ex, pr, md = "?", "?", "?", "?", "?"
        rows.append(
            f"  {d.name} phase={ph} status={st} "
            f"exec={ex} profile={pr} model={md}")
    if rows:
        print("Tasks:")
        print("\n".join(rows))
    return 0
