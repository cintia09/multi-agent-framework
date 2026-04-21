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

from .config import CodenookContext, compose_task_id, next_task_id, slugify

# atomic_write_json_validated lives in skills/builtin/_lib/atomic.py;
# load_context() prepends that dir to sys.path, so the import resolves
# at call-time (deferred to avoid import-order coupling).


HELP_TASK = """\
codenook task <new|set|set-model|set-exec|set-profile>

  new          create a new T-NNN under .codenook/tasks/
  set          mutate a writable field on an existing task
  set-model    set or clear the per-task LLM model_override
  set-exec     set the per-task execution_mode (sub-agent | inline)
  set-profile  set the per-task profile (must match plugin's phases.yaml)
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
  --title <str>           required (unless --interactive)
  --summary <str>
  --plugin <id>           defaults to first installed plugin
  --profile <name>        v0.20 — pick a profile from the plugin's
                          phases.yaml :: profiles. Validated against
                          declared profile keys; rejected with a list
                          of valid choices if unknown. When omitted,
                          falls back to the kernel's profile resolution
                          (clarifier output, then default).
  --input <text>          v0.20 — seed the initial task description
                          (used by phase agents / inline conductor as
                          additional context).
  --input-file <path>     v0.20 — read --input contents from a file.
                          Mutually exclusive with --input.
  --interactive           v0.20 — wizard mode: prompt for plugin /
                          profile / title / input / model / exec mode
                          via stdin/stdout. Mutually exclusive with
                          --accept-defaults.
  --target-dir <p>        defaults to src/
  --dual-mode <m>         serial | parallel
  --max-iterations <N>    positive integer (default: 3)
  --parent <T-NNN>
  --priority <P>          P0 | P1 | P2 | P3 (default: P2)
  --accept-defaults
  --id <T-NNN>            override generated task id (skips slug
                          derivation; use the literal value verbatim).
                          By default the id is auto-formatted as
                          T-NNN-<slug-from-input>.
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

HELP_SET_PROFILE = """\
Usage: codenook task set-profile --task T-NNN --profile <name>

  --profile <name>   one of the keys declared under `profiles:` in the
                     plugin's phases.yaml. Rejected with a list of valid
                     choices when invalid. Rejected when the task has
                     already advanced past phase 1 (clarify) — set the
                     profile up-front via `task new --profile <name>`
                     instead.
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
    if sub == "set-profile":
        return _task_set_profile(ctx, rest)
    sys.stderr.write(f"codenook task: unknown subcommand: {sub}\n")
    sys.stderr.write(HELP_TASK)
    return 2


def _load_plugin_profiles(ctx: CodenookContext, plugin: str) -> list[str]:
    """Return the ordered list of profile names declared in the plugin's
    phases.yaml, or [] when the plugin has no top-level ``profiles:``
    block (legacy single-pipeline layout)."""
    phases_yaml = (
        ctx.workspace / ".codenook" / "plugins" / plugin / "phases.yaml"
    )
    if not phases_yaml.is_file():
        return []
    try:
        import yaml  # type: ignore[import-untyped]
        doc = yaml.safe_load(phases_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    profiles = doc.get("profiles")
    if not isinstance(profiles, dict):
        return []
    return [str(k) for k in profiles.keys()]


def _read_input_file(path: str) -> tuple[str | None, str | None]:
    """Return (text, error_message). At most one is non-None."""
    p = Path(path).expanduser()
    if not p.is_file():
        return None, f"--input-file not found: {path}"
    try:
        return p.read_text(encoding="utf-8"), None
    except Exception as exc:
        return None, f"--input-file read error: {exc}"


def _task_new(ctx: CodenookContext, args: list[str]) -> int:
    if args and args[0] in ("-h", "--help"):
        print(HELP_NEW)
        return 0
    if "--interactive" in args:
        if "--accept-defaults" in args:
            sys.stderr.write(
                "codenook task new: --interactive and --accept-defaults "
                "are mutually exclusive\n")
            return 2
        return _task_new_interactive(ctx, args)
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
    profile = ""
    task_input = ""
    task_input_set = False
    input_file = ""

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
            elif a == "--profile":
                profile = next(it)
            elif a == "--input":
                task_input = next(it); task_input_set = True
            elif a == "--input-file":
                input_file = next(it)
            else:
                sys.stderr.write(f"codenook task new: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook task new: missing value for last flag\n")
        return 2

    if task_input_set and input_file:
        sys.stderr.write(
            "codenook task new: --input and --input-file are mutually "
            "exclusive\n")
        return 2
    if input_file:
        text, err = _read_input_file(input_file)
        if err:
            sys.stderr.write(f"codenook task new: {err}\n")
            return 2
        task_input = text or ""
        task_input_set = True

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

    if profile:
        valid = _load_plugin_profiles(ctx, plugin)
        if valid and profile not in valid:
            sys.stderr.write(
                f"codenook task new: invalid --profile '{profile}' for "
                f"plugin '{plugin}' (valid: {', '.join(valid)})\n")
            return 2
        # When the plugin has no profiles block, accept silently — the
        # field becomes a no-op for legacy pipelines.

    if not task_id:
        # Reserve the slot atomically by mkdir(exist_ok=False). Two
        # concurrent `task new` invocations that compute the same
        # next_task_id() would otherwise both pass mkdir(exist_ok=True)
        # and the second would clobber the first's state.json. Retry
        # up to 16 times to absorb concurrent reservers.
        # Slug source preference: --title wins because it is the
        # human-curated short label (≤24 chars). --input is rejected
        # as a slug source when it looks like multi-line interview
        # answers — those produce meaningless first-24-char slugs
        # like "数据来源-题库本地路径-volumes". Fallback chain is
        # title → single-line input → summary.
        single_line_input = (
            task_input if task_input and "\n" not in task_input.strip()
            else None
        )
        slug_source = title or single_line_input or summary
        slug = slugify(slug_source) if slug_source else ""
        tasks_root = ctx.workspace / ".codenook" / "tasks"
        tasks_root.mkdir(parents=True, exist_ok=True)
        for _attempt in range(16):
            n = next_task_id(ctx.workspace)
            task_id = compose_task_id(n, slug)
            tdir = tasks_root / task_id
            try:
                tdir.mkdir(parents=False, exist_ok=False)
                break
            except FileExistsError:
                task_id = ""
                continue
        else:
            sys.stderr.write(
                "codenook task new: could not reserve a task id slot "
                "after 16 attempts; another writer is racing.\n")
            return 1
    else:
        tdir = ctx.workspace / ".codenook" / "tasks" / task_id
        tdir.mkdir(parents=True, exist_ok=True)

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
    if profile:
        state["profile"] = profile
    if task_input_set and task_input:
        state["task_input"] = task_input

    # Atomic + schema-validated write (every other kernel writer
    # uses this; a bare write_text + SIGINT mid-write would brick
    # the task with a truncated state.json).
    from atomic import atomic_write_json_validated  # type: ignore
    _schema_path = str(Path(__file__).resolve().parents[2]
                       / "schemas" / "task-state.schema.json")
    atomic_write_json_validated(
        str(tdir / "state.json"), state, _schema_path)

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


def _task_set_profile(ctx: CodenookContext, args: list[str]) -> int:
    if args and args[0] in ("-h", "--help"):
        print(HELP_SET_PROFILE)
        return 0

    task = profile = ""
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--profile":
                profile = next(it)
            else:
                sys.stderr.write(f"codenook task set-profile: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook task set-profile: missing value for last flag\n")
        return 2

    if not task or not profile:
        sys.stderr.write(
            "codenook task set-profile: --task and --profile are both required\n")
        return 2

    sf = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
    if not sf.is_file():
        sys.stderr.write(f"codenook task set-profile: no such task: {task}\n")
        return 1

    state = json.loads(sf.read_text(encoding="utf-8"))
    plugin = state.get("plugin", "")
    valid = _load_plugin_profiles(ctx, plugin)
    if valid and profile not in valid:
        sys.stderr.write(
            f"codenook task set-profile: invalid --profile '{profile}' for "
            f"plugin '{plugin}' (valid: {', '.join(valid)})\n")
        return 2

    # Reject when the task has already advanced past the first phase.
    # The history is appended once per phase verdict (done/skipped/...);
    # when len(history) > 0 OR state.phase is set to anything other than
    # the very first phase, the task is "in flight" and switching the
    # profile would silently change the pipeline mid-walk.
    history = state.get("history") or []
    cur_phase = state.get("phase")
    if history or (cur_phase and cur_phase not in (None, "", "complete")):
        # Allow when we're still parked on the very first phase with no
        # history (i.e. tick has resolved & dispatched but no verdict yet).
        # The conservative check: any non-empty history means past phase 1.
        if history:
            sys.stderr.write(
                f"codenook task set-profile: task {task} has already "
                f"advanced past phase 1 (history has "
                f"{len(history)} entries); profile is locked. Create a "
                f"new task with --profile <name> instead.\n")
            return 2

    state["profile"] = profile
    sf.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(json.dumps({
        "task": state.get("task_id"),
        "field": "profile",
        "value": profile,
    }))
    return 0


_PROMPT_EOF = object()


def _prompt(prompt: str, default: str = ""):
    """Plain stdin/stdout prompt. No readline; works on cmd / PowerShell
    / POSIX shells alike.

    Returns the user-entered string (or ``default`` if the user just hit
    enter). Returns the sentinel :data:`_PROMPT_EOF` when stdin is at
    EOF (``readline()`` returned ``""``) so callers can distinguish
    "user pressed enter" from "stdin closed" — the wizard relies on
    this to abort instead of spinning forever.
    """
    suffix = f" [{default}]" if default else ""
    sys.stdout.write(f"{prompt}{suffix}: ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if line == "":
        return _PROMPT_EOF
    line = line.rstrip("\r\n")
    return line if line else default


def _prompt_multiline(prompt: str) -> str:
    """Multi-line stdin reader. Termination: empty line or EOF."""
    sys.stdout.write(f"{prompt}\n")
    sys.stdout.write("(end with empty line; Ctrl-D / Ctrl-Z+Enter for EOF)\n")
    sys.stdout.flush()
    lines: list[str] = []
    while True:
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            return ""
        if not line:  # EOF
            break
        stripped = line.rstrip("\r\n")
        if stripped == "":
            break
        lines.append(stripped)
    return "\n".join(lines)


def _task_new_interactive(ctx: CodenookContext, args: list[str]) -> int:
    """Wizard for `task new --interactive`.

    Walks the user through the minimum set of fields needed to create a
    task: plugin, profile, title, input, model, execution mode.
    Validates as we go (rejects empty title, validates profile against
    the chosen plugin). Final summary + Y/n confirmation, then dispatches
    to ``_task_new`` with the equivalent flag set.
    """
    # Filter --interactive out of args so any other flags the user passed
    # alongside it (e.g. --id) are forwarded to _task_new verbatim.
    forwarded: list[str] = [a for a in args if a != "--interactive"]

    installed = [
        p.get("id") for p in (ctx.state.get("installed_plugins") or [])
        if isinstance(p, dict) and p.get("id")
    ]
    if not installed:
        sys.stderr.write(
            "codenook task new: no installed plugin found in state.json\n")
        return 1

    def _abort_eof() -> int:
        sys.stderr.write(
            "codenook task new: stdin closed; aborting wizard.\n")
        return 1

    try:
        sys.stdout.write("codenook task new — interactive wizard\n\n")
        sys.stdout.write(f"Installed plugins: {', '.join(installed)}\n")
        plugin = _prompt("Plugin", default=installed[0])
        if plugin is _PROMPT_EOF:
            return _abort_eof()
        while plugin not in installed:
            sys.stdout.write(f"  ! '{plugin}' is not installed.\n")
            plugin = _prompt("Plugin", default=installed[0])
            if plugin is _PROMPT_EOF:
                return _abort_eof()

        profiles = _load_plugin_profiles(ctx, plugin)
        profile = ""
        if profiles:
            default_profile = "default" if "default" in profiles else profiles[0]
            sys.stdout.write(
                f"Profiles for '{plugin}': {', '.join(profiles)}\n")
            profile = _prompt("Profile", default=default_profile)
            if profile is _PROMPT_EOF:
                return _abort_eof()
            while profile not in profiles:
                sys.stdout.write(
                    f"  ! '{profile}' is not a valid profile (valid: "
                    f"{', '.join(profiles)})\n")
                profile = _prompt("Profile", default=default_profile)
                if profile is _PROMPT_EOF:
                    return _abort_eof()
        else:
            sys.stdout.write(
                f"(plugin '{plugin}' has no profiles block — skipping)\n")

        title = ""
        eof_streak = 0
        while not title:
            raw = _prompt("Title (required)")
            if raw is _PROMPT_EOF:
                eof_streak += 1
                if eof_streak >= 1:
                    return _abort_eof()
                continue
            eof_streak = 0
            title = raw.strip()
            if not title:
                sys.stdout.write("  ! title cannot be empty.\n")

        task_input = _prompt_multiline("Input (multi-line)")

        model = _prompt("Model (empty = use plugin/phase defaults)")
        if model is _PROMPT_EOF:
            return _abort_eof()

        exec_mode = _prompt(
            "Exec mode (sub-agent | inline)", default="sub-agent")
        if exec_mode is _PROMPT_EOF:
            return _abort_eof()
        while exec_mode not in ("sub-agent", "inline"):
            sys.stdout.write("  ! exec mode must be 'sub-agent' or 'inline'.\n")
            exec_mode = _prompt(
                "Exec mode (sub-agent | inline)", default="sub-agent")
            if exec_mode is _PROMPT_EOF:
                return _abort_eof()

        # Summary
        sys.stdout.write("\nSummary:\n")
        sys.stdout.write(f"  plugin     : {plugin}\n")
        sys.stdout.write(f"  profile    : {profile or '(default)'}\n")
        sys.stdout.write(f"  title      : {title}\n")
        sys.stdout.write(
            f"  input      : {(task_input[:60] + '...') if len(task_input) > 60 else (task_input or '(none)')}\n")
        sys.stdout.write(f"  model      : {model or '(plugin/phase default)'}\n")
        sys.stdout.write(f"  exec mode  : {exec_mode}\n")
        confirm_raw = _prompt("Create? [Y/n]", default="Y")
        if confirm_raw is _PROMPT_EOF:
            return _abort_eof()
        confirm = confirm_raw.strip().lower()
        if confirm and confirm not in ("y", "yes"):
            sys.stdout.write("aborted.\n")
            return 1
    except KeyboardInterrupt:
        sys.stderr.write("\ncodenook task new: interrupted; aborting wizard.\n")
        return 1

    # Build the equivalent argv and dispatch through _task_new so we
    # share validation and state-write logic.
    new_args: list[str] = ["--title", title, "--plugin", plugin,
                           "--accept-defaults"]
    if profile:
        new_args += ["--profile", profile]
    if task_input:
        new_args += ["--input", task_input]
    if model:
        new_args += ["--model", model]
    if exec_mode and exec_mode != "sub-agent":
        new_args += ["--exec", exec_mode]
    # Forward any extra flags the caller already passed (e.g. --id) but
    # avoid re-injecting fields the wizard just collected.
    skip_next = False
    skip_keys = {
        "--title", "--plugin", "--profile", "--input", "--input-file",
        "--model", "--exec", "--accept-defaults",
    }
    for a in forwarded:
        if skip_next:
            skip_next = False
            continue
        if a in skip_keys:
            if a != "--accept-defaults":
                skip_next = True
            continue
        new_args.append(a)

    return _task_new(ctx, new_args)


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
