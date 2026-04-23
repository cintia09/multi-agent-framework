"""``codenook status`` — read state.json and per-task summaries."""
from __future__ import annotations

import json
import sys
from typing import Sequence

from .config import CodenookContext, resolve_task_id


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
        resolved, candidates = resolve_task_id(ctx.workspace, task)
        if resolved is None:
            if candidates:
                sys.stderr.write(
                    f"codenook status: ambiguous --task {task}; candidates: "
                    f"{', '.join(candidates)}\n")
            else:
                sys.stderr.write(f"codenook status: no such task: {task}\n")
            return 1
        f = ctx.workspace / ".codenook" / "tasks" / resolved / "state.json"
        if not f.is_file():
            sys.stderr.write(f"codenook status: no such task: {task}\n")
            return 1
        sys.stdout.write(f.read_text(encoding="utf-8"))
        # Append the resolved model so single-task status matches the
        # multi-task table column. Lazy import + try/except so a
        # corrupt model module degrades gracefully instead of failing
        # the whole command.
        try:
            from .. import models  # type: ignore
            s = json.loads(f.read_text(encoding="utf-8"))
            md = (models.resolve_model(  # type: ignore[attr-defined]
                ctx.workspace, s.get("plugin") or "",
                s.get("phase") or "", s) or "<default>")
        except Exception:
            md = "<unknown>"
        sys.stdout.write(f"\nmodel={md}\n")
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

    # Reuse the canonical record collector from cmd_task — keeps the
    # row shape (and the HITL-by-JSON-task_id matching) in sync with
    # ``codenook task list``. We still resolve the model column here
    # because list does not (it would over-couple list to models.py).
    from . import cmd_task
    records = cmd_task._collect_task_records(ctx)
    rows: list[str] = []
    for r in records:
        ph = r["phase"] or "<none>"
        st = r["status"] or "?"
        ex = r["execution_mode"] or "sub-agent"
        pr = r["profile"] or "<auto>"
        md = "<unknown>"
        if _resolve is not None:
            try:
                # Reload state to pass to resolve_model (it needs the
                # full state dict, not just the summary fields).
                state = json.loads(
                    (ctx.workspace / ".codenook" / "tasks"
                     / r["dir_name"] / "state.json").read_text(
                        encoding="utf-8"))
                md = (_resolve(ctx.workspace, state.get("plugin") or "",
                               state.get("phase") or "", state)
                      or "<default>")
            except Exception:
                md = "<unknown>"
        rows.append(
            f"  {r['dir_name']} phase={ph} status={st} "
            f"exec={ex} profile={pr} model={md}")
    if rows:
        print("Tasks:")
        print("\n".join(rows))
    return 0
