"""``codenook task new`` and ``codenook task set`` — direct in-process
implementations of the bash wrapper's task subcommands.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .config import CodenookContext, next_task_id


HELP_TASK = """\
codenook task <new|set|set-model|set-exec>

  new        create a new T-NNN under .codenook/tasks/
  set        mutate a writable field on an existing task
  set-model  set or clear the per-task LLM model_override
  set-exec   set the per-task execution_mode (sub-agent | inline)
"""

HELP_SET = """\
Usage: codenook task set --task T-NNN --field <field> --value <val>

Writable fields:
  dual_mode       serial | parallel
  target_dir      directory path (e.g. src/)
  priority        P0 | P1 | P2 | P3
  max_iterations  positive integer
  summary         free text
  title           free text
"""

HELP_NEW = """\
Usage: codenook task new --title "..." [options]

Options:
  --title <str>           required
  --summary <str>
  --plugin <id>           defaults to first installed plugin
  --target-dir <p>        defaults to src/
  --dual-mode <m>         serial | parallel
  --max-iterations <N>    positive integer (default: 3)
  --parent <T-NNN>
  --priority <P>          P0 | P1 | P2 | P3 (default: P2)
  --accept-defaults
  --id <T-NNN>            override generated task id
  --model <name>          v0.18 — set per-task model_override (highest layer
                          in the C/B/A/D model resolution chain). Opaque
                          string forwarded verbatim to the conductor.
  --exec <mode>           v0.19 — per-task execution mode. One of:
                            sub-agent  (default) each phase dispatched as
                                       a separate sub-agent via the
                                       conductor's task tool.
                            inline     conductor reads role.md inline in
                                       its own session and writes the
                                       phase output itself; no sub-agent
                                       spawn. Best for chatty / serial
                                       phases.
"""

HELP_SET_MODEL = """\
Usage: codenook task set-model --task T-NNN (--model <name> | --clear)

  --model <name>   set the per-task model_override (opaque string).
  --clear          remove model_override; resolution falls through to the
                   phase / plugin / workspace defaults.
"""

HELP_SET_EXEC = """\
Usage: codenook task set-exec --task T-NNN --mode <sub-agent|inline>

  --mode sub-agent   default: each phase dispatched as a separate
                     sub-agent via the conductor's task tool.
  --mode inline      conductor reads role.md inline in its own session
                     and writes the phase output itself; no sub-agent
                     spawn.
"""

ALLOWED = {
    "dual_mode": ("serial", "parallel"),
    "priority": ("P0", "P1", "P2", "P3"),
}
INT_FIELDS = {"max_iterations"}
WRITABLE = {"dual_mode", "target_dir", "priority", "max_iterations", "summary", "title"}


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    if not args:
        sys.stderr.write(HELP_TASK)
        return 2
    sub, rest = args[0], list(args[1:])
    if sub == "new":
        return _task_new(ctx, rest)
    if sub == "set":
        return _task_set(ctx, rest)
    if sub == "set-model":
        return _task_set_model(ctx, rest)
    if sub == "set-exec":
        return _task_set_exec(ctx, rest)
    sys.stderr.write(f"codenook task: unknown subcommand: {sub}\n")
    sys.stderr.write(HELP_TASK)
    return 2


def _task_new(ctx: CodenookContext, args: list[str]) -> int:
    if args and args[0] in ("-h", "--help"):
        print(HELP_NEW)
        return 0
    title = summary = plugin = target_dir = ""
    dual_mode = ""
    dual_mode_set = False
    priority = "P2"
    max_iter = 3
    parent = ""
    accept_defaults = False
    task_id = ""
    model = ""
    exec_mode_val = ""

    it = iter(args)
    try:
        for a in it:
            if a == "--title":
                title = next(it)
            elif a == "--summary":
                summary = next(it)
            elif a == "--plugin":
                plugin = next(it)
            elif a == "--target-dir":
                target_dir = next(it)
            elif a == "--dual-mode":
                dual_mode = next(it); dual_mode_set = True
            elif a == "--max-iterations":
                max_iter = int(next(it))
            elif a == "--parent":
                parent = next(it)
            elif a == "--priority":
                priority = next(it)
            elif a == "--accept-defaults":
                accept_defaults = True
            elif a == "--id":
                task_id = next(it)
            elif a == "--model":
                model = next(it)
            elif a == "--exec":
                exec_mode_val = next(it)
            else:
                sys.stderr.write(f"codenook task new: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook task new: missing value for last flag\n")
        return 2

    if not title:
        sys.stderr.write("codenook task new: --title is required\n")
        return 2
    if priority not in ALLOWED["priority"]:
        sys.stderr.write(
            f"codenook task new: invalid --priority '{priority}' "
            f"(allowed: P0|P1|P2|P3)\n")
        return 2
    if exec_mode_val and exec_mode_val not in ("sub-agent", "inline"):
        sys.stderr.write(
            f"codenook task new: invalid --exec '{exec_mode_val}' "
            f"(allowed: sub-agent|inline)\n")
        return 2

    if not target_dir:
        target_dir = "src/"

    if not plugin:
        installed = ctx.state.get("installed_plugins") or []
        plugin = (installed[0].get("id") if installed else "") or ""
    if not plugin:
        sys.stderr.write(
            "codenook task new: no installed plugin found in state.json\n")
        return 1

    if not task_id:
        task_id = next_task_id(ctx.workspace)

    tdir = ctx.workspace / ".codenook" / "tasks" / task_id
    (tdir / "outputs").mkdir(parents=True, exist_ok=True)
    (tdir / "prompts").mkdir(parents=True, exist_ok=True)
    (tdir / "notes").mkdir(parents=True, exist_ok=True)

    state: dict = {
        "schema_version": 1,
        "task_id": task_id,
        "plugin": plugin,
        "phase": None,
        "iteration": 0,
        "max_iterations": max_iter,
        "status": "in_progress",
        "history": [],
        "priority": priority,
    }
    if dual_mode_set:
        state["dual_mode"] = dual_mode or "serial"
    elif accept_defaults:
        state["dual_mode"] = "serial"

    if title:
        state["title"] = title
    if summary:
        state["summary"] = summary
    if target_dir:
        state["target_dir"] = target_dir
    if parent:
        state["parent_id"] = parent
    if model:
        state["model_override"] = model
    if exec_mode_val:
        state["execution_mode"] = exec_mode_val

    (tdir / "state.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8")

    if parent:
        try:
            subprocess.run(
                [sys.executable, "-m", "task_chain",
                 "--workspace", str(ctx.workspace),
                 "attach", task_id, parent],
                check=False,
                env=_subproc_env(ctx),
            )
        except Exception:
            pass

    if not dual_mode_set and not accept_defaults:
        recovery = (
            f"codenook task set --task {task_id} "
            f"--field dual_mode --value <serial|parallel>"
        )
        sys.stdout.write(json.dumps({
            "action": "entry_question",
            "task": task_id,
            "field": "dual_mode",
            "allowed_values": ["serial", "parallel"],
            "recovery": recovery,
        }) + "\n")
        return 2

    print(task_id)
    return 0


def _task_set(ctx: CodenookContext, args: list[str]) -> int:
    if args and args[0] in ("-h", "--help"):
        print(HELP_SET)
        return 0

    task = field = value = ""
    value_set = False
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--field":
                field = next(it)
            elif a == "--value":
                value = next(it); value_set = True
            else:
                sys.stderr.write(f"codenook task set: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook task set: missing value for last flag\n")
        return 2

    if not (task and field and value_set):
        sys.stderr.write(
            "codenook task set: --task, --field, --value all required\n")
        return 2

    sf = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
    if not sf.is_file():
        sys.stderr.write(f"codenook task set: no such task: {task}\n")
        return 1

    if field not in WRITABLE:
        sys.stderr.write(
            f"codenook task set: field '{field}' is not writable "
            f"(allowed: {sorted(WRITABLE)})\n")
        return 2
    if field in ALLOWED and value not in ALLOWED[field]:
        sys.stderr.write(
            f"codenook task set: invalid value '{value}' for {field} "
            f"(allowed: {ALLOWED[field]})\n")
        return 2

    typed_value: object = value
    if field in INT_FIELDS:
        try:
            typed_value = int(value)
        except ValueError:
            sys.stderr.write(
                f"codenook task set: {field} must be an integer\n")
            return 2

    state = json.loads(sf.read_text(encoding="utf-8"))
    state[field] = typed_value
    sf.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(json.dumps({
        "task": state.get("task_id"),
        "field": field,
        "value": typed_value,
    }))
    return 0


def _task_set_model(ctx: CodenookContext, args: list[str]) -> int:
    if args and args[0] in ("-h", "--help"):
        print(HELP_SET_MODEL)
        return 0

    task = model = ""
    model_set = False
    clear = False
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--model":
                model = next(it); model_set = True
            elif a == "--clear":
                clear = True
            else:
                sys.stderr.write(f"codenook task set-model: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook task set-model: missing value for last flag\n")
        return 2

    if not task:
        sys.stderr.write("codenook task set-model: --task is required\n")
        return 2
    if model_set and clear:
        sys.stderr.write(
            "codenook task set-model: --model and --clear are mutually exclusive\n")
        return 2
    if not model_set and not clear:
        sys.stderr.write(
            "codenook task set-model: one of --model <name> or --clear is required\n")
        return 2

    sf = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
    if not sf.is_file():
        sys.stderr.write(f"codenook task set-model: no such task: {task}\n")
        return 1

    state = json.loads(sf.read_text(encoding="utf-8"))
    if clear:
        state.pop("model_override", None)
        result_value: object = None
    else:
        state["model_override"] = model
        result_value = model
    sf.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(json.dumps({
        "task": state.get("task_id"),
        "field": "model_override",
        "value": result_value,
    }))
    return 0


def _task_set_exec(ctx: CodenookContext, args: list[str]) -> int:
    if args and args[0] in ("-h", "--help"):
        print(HELP_SET_EXEC)
        return 0

    task = mode = ""
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--mode":
                mode = next(it)
            else:
                sys.stderr.write(f"codenook task set-exec: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook task set-exec: missing value for last flag\n")
        return 2

    if not task:
        sys.stderr.write("codenook task set-exec: --task is required\n")
        return 2
    if mode not in ("sub-agent", "inline"):
        sys.stderr.write(
            "codenook task set-exec: --mode must be 'sub-agent' or 'inline'\n")
        return 2

    sf = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
    if not sf.is_file():
        sys.stderr.write(f"codenook task set-exec: no such task: {task}\n")
        return 1

    state = json.loads(sf.read_text(encoding="utf-8"))
    state["execution_mode"] = mode
    sf.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(json.dumps({
        "task": state.get("task_id"),
        "field": "execution_mode",
        "value": mode,
    }))
    return 0


def _subproc_env(ctx: CodenookContext) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(ctx.kernel_lib)
        + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    env["CODENOOK_WORKSPACE"] = str(ctx.workspace)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env
