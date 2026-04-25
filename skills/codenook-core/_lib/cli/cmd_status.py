"""``codenook status`` — read state.json and per-task summaries."""
from __future__ import annotations

import json
import sys
from typing import Sequence

from .config import CodenookContext, resolve_task_id


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    task = ""
    json_mode = False
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--json":
                json_mode = True
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
        # R16 P1 fix: previously emitted state.json followed by a
        # `\nmodel=<x>\n` trailer, breaking any JSON parser. Resolve
        # the model first and merge it into the JSON object instead.
        try:
            from .. import models  # type: ignore
            s = json.loads(f.read_text(encoding="utf-8"))
            md = (models.resolve_model(  # type: ignore[attr-defined]
                ctx.workspace, s.get("plugin") or "",
                s.get("phase") or "", s) or "<default>")
        except Exception:
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                # Corrupt state.json — preserve legacy behaviour:
                # dump raw bytes and append model=<unknown>.
                sys.stdout.write(f.read_text(encoding="utf-8"))
                sys.stdout.write("\nmodel=<unknown>\n")
                return 0
            md = "<unknown>"
        s["_resolved_model"] = md
        sys.stdout.write(json.dumps(s, ensure_ascii=False, indent=2) + "\n")
        return 0

    if json_mode:
        # R16 P1 fix: machine-readable status output. Mirrors the human
        # table but as a single JSON object {workspace, state, tasks}.
        try:
            from .. import models  # type: ignore
            _resolve = models.resolve_model  # type: ignore[attr-defined]
        except Exception:
            _resolve = None
        from . import cmd_task
        records = cmd_task._collect_task_records(ctx)
        out_tasks = []
        for r in records:
            md = "<unknown>"
            if _resolve is not None:
                try:
                    state = json.loads(
                        (ctx.workspace / ".codenook" / "tasks"
                         / r["dir_name"] / "state.json").read_text(
                            encoding="utf-8"))
                    md = (_resolve(ctx.workspace, state.get("plugin") or "",
                                   state.get("phase") or "", state)
                          or "<default>")
                except Exception:
                    md = "<unknown>"
            out_tasks.append({
                "dir_name": r["dir_name"],
                "phase": r["phase"],
                "status": r["status"],
                "execution_mode": r["execution_mode"] or "sub-agent",
                "profile": r["profile"],
                "model": md,
            })
        try:
            ws_state = json.loads(
                ctx.state_file.read_text(encoding="utf-8"))
        except Exception:
            ws_state = {}
        sys.stdout.write(json.dumps({
            "workspace": str(ctx.workspace),
            "state": ws_state,
            "tasks": out_tasks,
        }, ensure_ascii=False, indent=2) + "\n")
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
