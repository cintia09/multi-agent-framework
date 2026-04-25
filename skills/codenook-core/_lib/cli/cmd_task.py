"""``codenook task new`` and ``codenook task set`` — direct in-process
implementations of the bash wrapper's task subcommands.

Workspace conventions used by ``task list/delete/restore``:

  .codenook/tasks/<id>/        active task dir (state.json + outputs/)
  .codenook/tasks/_archive/    soft-deleted tasks (``task delete`` default).
                               Leading ``_`` makes ``iter_active_task_dirs``
                               skip them so they never resurface in the
                               active table. ``task restore`` moves them
                               back.
  .codenook/hitl-queue/        active gate entries (one *.json per gate)
  .codenook/hitl-queue/_consumed/
                               historical gate entries — either decided
                               by ``codenook hitl decide`` or moved here
                               by ``task delete`` when archiving a task.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .config import (
    CodenookContext, compose_task_id, is_safe_task_component,
    iter_active_task_dirs, next_task_id, resolve_task_id, slugify,
)

# atomic_write_json_validated lives in skills/builtin/_lib/atomic.py;
# load_context() prepends that dir to sys.path, so the import resolves
# at call-time (deferred to avoid import-order coupling).


HELP_TASK = """\
codenook task <new|list|show|delete|restore|set|set-model|set-exec|set-profile|set-phase|suggest-parent>

  new             create a new T-NNN under .codenook/tasks/
  list            list tasks grouped by status (with HITL-pending hints)
  show            print full details of a single task (state + HITL)
  delete          archive (default) or purge tasks + their HITL queue files
  restore         restore archived tasks from .codenook/tasks/_archive/
  set             mutate a writable field on an existing task
  set-model       set or clear the per-task LLM model_override
  set-exec        set the per-task execution_mode (sub-agent | inline)
  set-profile     set the per-task profile (must match plugin's phases.yaml)
  set-phase       rewind/jump task to any phase in the active profile chain
  suggest-parent  rank open tasks by similarity to a child brief (Jaccard)
"""

HELP_LIST = """\
Usage: codenook task list [options]

Group active tasks under .codenook/tasks/ by status and surface
HITL-pending counts per task. By default emits a human-readable
table; pass --json for machine-readable output, or --tree to render
parent → child relationships (from state.json :: parent_id).

Options:
  --status <s>      filter by status (e.g. in_progress, waiting, done)
                    repeatable; comma-separated also accepted
  --phase <p>       filter by phase id (repeatable / comma-separated)
  --plugin <id>     filter by plugin id
  --include-done    include status=done tasks in the human table
                    (always included in --json)
  --tree            print roots first then indent each child by 2
                    spaces under its parent (status filters still
                    apply, but a filtered-out parent shows up as a
                    placeholder so children stay reachable)
  --json            emit a JSON array on stdout, one object per task
"""

HELP_DELETE = """\
Usage: codenook task delete <T-NNN> [T-NNN ...] [options]
       codenook task delete --task T-NNN [--task T-NNN ...] [options]

Archive (default) or purge tasks from .codenook/tasks/ and their
related entries under .codenook/hitl-queue/. Bare T-NNN ids are
resolved to their slugged directory the same way every other task
subcommand does (see `task set`).

Default behaviour is non-destructive: each task directory is moved
to ``.codenook/tasks/_archive/<orig>-<UTC-ts>/`` (the leading
underscore makes ``iter_active_task_dirs`` skip it) and matching
HITL queue entries are moved into ``.codenook/hitl-queue/_consumed/``
to preserve the audit trail.

Options:
  --task <T-NNN>    task id to delete (repeatable; alternative to
                    bare positional ids)
  --status <s>      bulk-select tasks by status (e.g. waiting).
                    Combined with positional/--task ids via union.
  --purge           rm -rf instead of archive (irreversible).
  --force           allow deleting status=in_progress tasks.
  --yes             skip the interactive y/N confirmation prompt.
  --dry-run         print what would happen, change nothing.
  --json            emit one JSON object per processed task on stdout.

Exit codes:
  0  all selected tasks deleted (or dry-run preview printed)
  1  one or more tasks could not be resolved / refused by --force
  2  usage error
"""

HELP_SUGGEST_PARENT = """\
Usage: codenook task suggest-parent --brief "<child brief text>" [options]

Rank open tasks in the workspace by token-set Jaccard similarity to
the supplied brief, so the conductor can offer the user the choice
to (a) resume an existing task, (b) chain the new one as a child via
`task new --parent T-NNN`, or (c) ignore and create independently.

Options:
  --brief <text>      required (the candidate child task's brief)
  --top-k <N>         number of candidates to return (default: 3)
  --threshold <F>     minimum Jaccard score in [0, 1] (default: 0.15)
  --exclude <T-NNN>   task id to exclude (repeatable)
  --json              emit JSON array on stdout (recommended for
                      machine consumption); plain TSV otherwise

Exit 0 with empty output / `[]` when no open tasks meet the
threshold (this is normal — proceed to create a fresh task).
"""

HELP_SET = """\
Usage: codenook task set --task T-NNN --field <field> (--value <val> | --value-file <path>)

Writable fields:
  dual_mode       serial | parallel
  target_dir      directory path (e.g. src/)
  priority        P0 | P1 | P2 | P3
  max_iterations  positive integer
  summary         free text
  title           free text
  task_input      free text (use --value-file for multi-line / long input)

Plugin entry-question fields (v0.29.3):
  Any field declared under `plugins/<id>/entry-questions.yaml` (in a
  phase's `required:` or `questions:` map) is auto-routed to
  `state["entry_answers"][<field>]`. Use `task set --field <plugin_field>
  --value <answer>` to satisfy the entry-question gate before the next
  tick.
"""

HELP_NEW = """\
Usage: codenook task new --title "..." [options]

Options:
  --title <str>           required (unless --interactive)
  --summary <str>
  --plugin <id>           installed plugin id. When omitted:
                            * single plugin installed → use it silently
                            * multiple plugins → interactive menu prompt
                              (or auto-pick first with --accept-defaults)
                            Unknown plugin ids are rejected with the
                            list of available ones.
  --profile <name>        v0.20 — pick a profile from the plugin's
                          phases.yaml :: profiles. Validated against
                          declared profile keys; rejected with a list
                          of valid choices if unknown. When omitted
                          AND the plugin advertises profiles, an
                          interactive menu prompt is shown (or the
                          profile named "default" is auto-picked
                          silently with --accept-defaults, falling
                          back to the first declared profile).
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

HELP_SET_PHASE = """\
Usage: codenook task set-phase --task T-NNN --phase <id> [--keep-outputs] [--yes]

  --phase <id>       phase id to jump/rewind to. Must exist in the active
                     profile chain (run `codenook task show` to see the
                     chain). Backward jumps trim history entries for
                     phases at or after the target so the next `tick`
                     re-dispatches the target phase.

  --keep-outputs     by default, output files for the trimmed phases are
                     archived to outputs/_archive/<ts>/ to avoid stale
                     replies leaking into a re-dispatch. Pass this flag
                     to leave them in place (the next dispatch will
                     overwrite them anyway).

  --yes              skip the confirmation prompt (required for
                     non-interactive use).

Behavior:
  • Validates the phase id against the active profile's chain.
  • Clears state.in_flight_agent (any pending sub-agent dispatch is
    abandoned; tick will re-dispatch the target phase).
  • Trims state.history of all entries whose phase appears at or after
    the target in the chain.
  • Resets state.iteration to 0 (the target phase starts a fresh round).
  • Appends a `phase_reset_from_<old>` warning marker to history for
    audit.
  • Archives matching outputs/phase-N-*.md files to outputs/_archive/<ts>/
    unless --keep-outputs.

Forward jumps (skipping ahead) are also supported but will leave any
intermediate phases unrun — `tick` will resume from the new pointer.
"""

ALLOWED = {
    "dual_mode": ("serial", "parallel"),
    "priority": ("P0", "P1", "P2", "P3"),
}
INT_FIELDS = {"max_iterations"}
WRITABLE = {"dual_mode", "target_dir", "priority", "max_iterations", "summary", "title", "task_input"}


def _plugin_entry_question_keys(workspace: Path, plugin: str) -> set[str]:
    """Collect every field name that any phase in the plugin's
    entry-questions.yaml lists under `required` or `questions`.

    Returned set drives v0.29.3 auto-routing: `task set --field K`
    where K is in this set is written to `state["entry_answers"][K]`
    instead of being rejected as non-writable.
    """
    keys: set[str] = set()
    if not plugin:
        return keys
    eq_path = workspace / ".codenook" / "plugins" / plugin / "entry-questions.yaml"
    if not eq_path.is_file():
        return keys
    try:
        import yaml  # type: ignore
        with eq_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return keys
    if not isinstance(data, dict):
        return keys
    for spec in data.values():
        if not isinstance(spec, dict):
            continue
        for k in spec.get("required") or []:
            if isinstance(k, str):
                keys.add(k)
        questions = spec.get("questions") or {}
        if isinstance(questions, dict):
            for k in questions.keys():
                if isinstance(k, str):
                    keys.add(k)
    return keys


def _persist_state(sf: Path, state: dict) -> None:
    """Atomic + schema-validated write of <task>/state.json.

    All four task-mutation subcommands (set, set-model, set-exec,
    set-profile) used to do bare ``sf.write_text(json.dumps(...))``,
    which v0.25.0 fixed only for ``task new``. A SIGINT or crash
    mid-write would truncate state.json and brick every subsequent
    tick/status for that task. This helper ensures every writer goes
    through atomic_write_json_validated.
    """
    from atomic import atomic_write_json_validated  # type: ignore
    schema_path = str(Path(__file__).resolve().parents[2]
                      / "schemas" / "task-state.schema.json")
    atomic_write_json_validated(str(sf), state, schema_path)


def _resolve_or_error(
    ctx: CodenookContext, task: str, subcmd: str,
) -> tuple[str | None, int]:
    """Resolve a (possibly bare) ``T-NNN`` to the actual dir name.

    Returns ``(resolved_id, exit_code)`` — when ``resolved_id`` is
    ``None`` the caller must return ``exit_code`` immediately. Writes
    a uniformly-formatted error to stderr.
    """
    resolved, candidates = resolve_task_id(ctx.workspace, task)
    if resolved is None:
        if candidates:
            sys.stderr.write(
                f"codenook task {subcmd}: ambiguous --task {task}; "
                f"candidates: {', '.join(candidates)}\n")
        else:
            sys.stderr.write(
                f"codenook task {subcmd}: no such task: {task}\n")
        return None, 1
    return resolved, 0


def _safe_state_path(
    ctx: CodenookContext, task: str, subcmd: str,
) -> tuple[Path | None, str | None, int]:
    """Validate *task* as a single-component slug and return its state.json.

    Combines the ``is_safe_task_component`` path-traversal guard with
    the ``resolve_task_id`` slug-completion fallback used by every task
    mutator. Returns ``(state_path, resolved_task, 0)`` on success or
    ``(None, None, exit_code)`` on failure (caller returns exit_code).
    """
    if not is_safe_task_component(task):
        sys.stderr.write(
            f"codenook task {subcmd}: invalid --task {task!r} "
            "(must be a single safe path component)\n")
        return None, None, 2
    sf = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
    if not sf.is_file():
        resolved, rc = _resolve_or_error(ctx, task, subcmd)
        if resolved is None:
            return None, None, rc
        # resolve_task_id only returns existing dir names, so resolved
        # is already known-safe; re-validate as belt-and-braces.
        if not is_safe_task_component(resolved):
            sys.stderr.write(
                f"codenook task {subcmd}: resolved task id {resolved!r} "
                "failed safety check\n")
            return None, None, 2
        task = resolved
        sf = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
    return sf, task, 0



def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    if not args:
        sys.stderr.write(HELP_TASK)
        return 2
    sub, rest = args[0], list(args[1:])
    if sub == "new":
        return _task_new(ctx, rest)
    if sub == "list":
        return _task_list(ctx, rest)
    if sub == "show":
        return _task_show(ctx, rest)
    if sub == "delete":
        return _task_delete(ctx, rest)
    if sub == "restore":
        return _task_restore(ctx, rest)
    if sub == "set":
        return _task_set(ctx, rest)
    if sub == "set-model":
        return _task_set_model(ctx, rest)
    if sub == "set-exec":
        return _task_set_exec(ctx, rest)
    if sub == "set-profile":
        return _task_set_profile(ctx, rest)
    if sub == "set-phase":
        return _task_set_phase(ctx, rest)
    if sub == "suggest-parent":
        return _task_suggest_parent(ctx, rest)
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


def _load_plugin_phase_chain(
    ctx: CodenookContext, plugin: str, profile: str | None,
) -> list[str]:
    """Return the ordered phase id chain for ``plugin`` under ``profile``.

    Falls back to the flat ``phases:`` list when phases.yaml has no
    ``profiles:`` block (legacy layout). Returns ``[]`` on any error so
    callers can surface a friendly message.
    """
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
    if isinstance(profiles, dict) and profile and profile in profiles:
        spec = profiles.get(profile)
        chain = spec.get("phases") if isinstance(spec, dict) else spec
        if isinstance(chain, list):
            return [str(x) for x in chain]
        return []
    raw = doc.get("phases", [])
    if isinstance(raw, list):
        return [
            str(ph.get("id")) for ph in raw
            if isinstance(ph, dict) and ph.get("id")
        ]
    if isinstance(raw, dict):
        return [str(k) for k in raw.keys()]
    return []


def _read_input_file(path: str) -> tuple[str | None, str | None]:
    """Return (text, error_message). At most one is non-None.

    A literal ``-`` reads the entire body from stdin (v0.29.10).
    """
    if path == "-":
        try:
            return sys.stdin.read(), None
        except Exception as exc:
            return None, f"--input-file stdin read error: {exc}"
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
                if not is_safe_task_component(task_id):
                    sys.stderr.write(
                        f"codenook task new: invalid --id (path traversal "
                        f"or reserved prefix): {task_id!r}\n")
                    return 2
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

    # v0.29.10 — null-byte rejection. JSON would round-trip \u0000 but
    # downstream consumers (shells, prompt renderers) often crash on
    # embedded NULs. Treat as a usage error.
    if task_input_set and "\x00" in task_input:
        sys.stderr.write(
            "codenook task new: --input / --input-file contains NUL byte "
            "(\\x00); refusing to seed task with binary data\n"
        )
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

    prompted_any = False
    if not plugin:
        installed = [
            p.get("id") for p in (ctx.state.get("installed_plugins") or [])
            if isinstance(p, dict) and p.get("id")
        ]
        if not installed:
            sys.stderr.write(
                "codenook task new: no installed plugin found in state.json\n")
            return 1
        if len(installed) == 1 or accept_defaults:
            plugin = installed[0]
            if not accept_defaults and len(installed) == 1:
                sys.stdout.write(
                    f"(only one plugin installed — using '{plugin}')\n")
        else:
            plugin = _prompt_choice(
                "Plugin", installed, default=installed[0],
                label_for=lambda pid: pid,
            )
            if plugin is None:
                sys.stderr.write(
                    "codenook task new: plugin selection aborted.\n")
                return 1
            prompted_any = True
    else:
        # Explicit --plugin: validate it's actually installed.
        installed_ids = [
            p.get("id") for p in (ctx.state.get("installed_plugins") or [])
            if isinstance(p, dict) and p.get("id")
        ]
        if installed_ids and plugin not in installed_ids:
            sys.stderr.write(
                f"codenook task new: plugin '{plugin}' is not installed "
                f"(available: {', '.join(installed_ids)})\n")
            return 2

    # Profile selection: if the plugin advertises profiles and none
    # was passed, prompt interactively (unless --accept-defaults).
    prompted_profile = False
    if profile:
        valid = _load_plugin_profiles(ctx, plugin)
        if valid and profile not in valid:
            sys.stderr.write(
                f"codenook task new: invalid --profile '{profile}' for "
                f"plugin '{plugin}' (valid: {', '.join(valid)})\n")
            return 2
        # When the plugin has no profiles block, accept silently — the
        # field becomes a no-op for legacy pipelines.
    else:
        valid = _load_plugin_profiles(ctx, plugin)
        if valid and not accept_defaults:
            default_profile = (
                "default" if "default" in valid else valid[0])
            chosen = _prompt_choice(
                f"Profile for '{plugin}'", valid, default=default_profile,
                label_for=lambda p: p,
            )
            if chosen is None:
                sys.stderr.write(
                    "codenook task new: profile selection aborted.\n")
                return 1
            profile = chosen
            prompted_profile = True

    # Summary + confirm page — only when we actually prompted the
    # user for something AND stdin is a TTY (keeps scripted / CI
    # flows from blocking). Non-TTY pipelines already saw the
    # auto-select transparency lines above; re-confirming via a
    # blocking prompt would hang them.
    if (prompted_any or prompted_profile) and sys.stdin.isatty() \
            and not accept_defaults:
        sys.stdout.write("\nSummary:\n")
        sys.stdout.write(f"  title     : {title}\n")
        sys.stdout.write(f"  plugin    : {plugin}\n")
        sys.stdout.write(f"  profile   : {profile or '(default)'}\n")
        sys.stdout.write(f"  priority  : {priority}\n")
        if parent:
            sys.stdout.write(f"  parent    : {parent}\n")
        if model:
            sys.stdout.write(f"  model     : {model}\n")
        if exec_mode_val:
            sys.stdout.write(f"  exec mode : {exec_mode_val}\n")
        if dual_mode_set:
            sys.stdout.write(f"  dual-mode : {dual_mode}\n")
        if task_input:
            preview = task_input[:60] + ("…" if len(task_input) > 60 else "")
            sys.stdout.write(f"  input     : {preview}\n")
        confirm_raw = _prompt("Create? [Y/n]", default="Y")
        if confirm_raw is _PROMPT_EOF:
            sys.stderr.write(
                "codenook task new: stdin closed during confirmation; "
                "aborted.\n")
            return 1
        confirm = confirm_raw.strip().lower()
        if confirm and confirm not in ("y", "yes"):
            sys.stdout.write("aborted.\n")
            return 1

    if not task_id:
        # Reserve the slot atomically by mkdir(exist_ok=False). Two
        # concurrent `task new` invocations that compute the same
        # next_task_id() would otherwise both pass mkdir(exist_ok=True)
        # and the second would clobber the first's state.json. Retry
        # up to 128 times to absorb bursty concurrent reservers.
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
        for _attempt in range(128):
            n = next_task_id(ctx.workspace)
            task_id = compose_task_id(n, slug)
            tdir = tasks_root / task_id
            try:
                tdir.mkdir(parents=False, exist_ok=False)
                break
            except FileExistsError:
                task_id = ""
                continue
            except OSError as e:
                sys.stderr.write(
                    f"codenook task new: failed to create {tdir}: {e}\n")
                return 1
        else:
            sys.stderr.write(
                "codenook task new: could not reserve a task id slot "
                "after 128 attempts; another writer is racing.\n")
            return 1
    else:
        tdir = ctx.workspace / ".codenook" / "tasks" / task_id
        # Refuse to clobber an existing task. The atomic state-write
        # below would otherwise wipe history/model_override/parent
        # links in a single fsync. Tolerate an empty pre-existing dir
        # (operator may have pre-created it) by checking for state.json.
        try:
            tdir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            if (tdir / "state.json").is_file():
                sys.stderr.write(
                    f"codenook task new: task {task_id} already exists; "
                    f"refusing to overwrite\n")
                return 1
            # empty pre-existing dir is fine; fall through.
        except OSError as e:
            sys.stderr.write(
                f"codenook task new: failed to create {tdir}: {e}\n")
            return 1

    (tdir / "outputs").mkdir(parents=True, exist_ok=True)
    (tdir / "prompts").mkdir(parents=True, exist_ok=True)

    state: dict = {
        "schema_version": 2,
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

    # Atomic + schema-validated write (centralised helper).
    _persist_state(tdir / "state.json", state)

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
    value_file = ""
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--field":
                field = next(it)
            elif a == "--value":
                value = next(it); value_set = True
            elif a == "--value-file":
                value_file = next(it)
            else:
                sys.stderr.write(f"codenook task set: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook task set: missing value for last flag\n")
        return 2

    if value_set and value_file:
        sys.stderr.write(
            "codenook task set: --value and --value-file are mutually exclusive\n")
        return 2
    if value_file:
        p = Path(value_file).expanduser()
        if not p.is_file():
            sys.stderr.write(
                f"codenook task set: --value-file not found: {value_file}\n")
            return 2
        try:
            value = p.read_text(encoding="utf-8")
        except Exception as exc:
            sys.stderr.write(
                f"codenook task set: --value-file read error: {exc}\n")
            return 2
        value_set = True

    if not (task and field and value_set):
        sys.stderr.write(
            "codenook task set: --task, --field, and one of "
            "(--value | --value-file) are required\n")
        return 2

    sf, task, rc = _safe_state_path(ctx, task, "set")
    if sf is None:
        return rc

    if field not in WRITABLE:
        # v0.29.3: auto-route plugin-defined entry-question fields to
        # state["entry_answers"][field] instead of rejecting them.
        state = json.loads(sf.read_text(encoding="utf-8"))
        plugin_keys = _plugin_entry_question_keys(
            ctx.workspace, state.get("plugin", ""))
        if field in plugin_keys:
            answers = state.get("entry_answers")
            if not isinstance(answers, dict):
                answers = {}
            answers[field] = value
            state["entry_answers"] = answers
            _persist_state(sf, state)
            print(json.dumps({
                "task": state.get("task_id"),
                "field": field,
                "value": value,
                "stored_under": f"entry_answers.{field}",
            }))
            return 0
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
    _persist_state(sf, state)
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

    sf, task, rc = _safe_state_path(ctx, task, "set-model")
    if sf is None:
        return rc

    state = json.loads(sf.read_text(encoding="utf-8"))
    if clear:
        state.pop("model_override", None)
        result_value: object = None
    else:
        state["model_override"] = model
        result_value = model
    _persist_state(sf, state)
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

    sf, task, rc = _safe_state_path(ctx, task, "set-exec")
    if sf is None:
        return rc

    state = json.loads(sf.read_text(encoding="utf-8"))
    state["execution_mode"] = mode
    _persist_state(sf, state)
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

    sf, task, rc = _safe_state_path(ctx, task, "set-profile")
    if sf is None:
        return rc

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
    _persist_state(sf, state)
    print(json.dumps({
        "task": state.get("task_id"),
        "field": "profile",
        "value": profile,
    }))
    return 0


def _task_set_phase(ctx: CodenookContext, args: list[str]) -> int:
    if args and args[0] in ("-h", "--help"):
        print(HELP_SET_PHASE)
        return 0

    task = phase = ""
    keep_outputs = False
    yes = False
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--phase":
                phase = next(it)
            elif a == "--keep-outputs":
                keep_outputs = True
            elif a == "--yes" or a == "-y":
                yes = True
            else:
                sys.stderr.write(f"codenook task set-phase: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook task set-phase: missing value for last flag\n")
        return 2

    if not task or not phase:
        sys.stderr.write(
            "codenook task set-phase: --task and --phase are both required\n")
        return 2

    sf, task, rc = _safe_state_path(ctx, task, "set-phase")
    if sf is None:
        return rc

    state = json.loads(sf.read_text(encoding="utf-8"))
    plugin = state.get("plugin", "")
    profile = state.get("profile") or None

    chain = _load_plugin_phase_chain(ctx, plugin, profile)
    if not chain:
        sys.stderr.write(
            f"codenook task set-phase: cannot resolve phase chain for "
            f"plugin='{plugin}' profile='{profile or '<unset>'}'. Check "
            f"phases.yaml is present and the profile name matches.\n")
        return 2
    if phase not in chain:
        sys.stderr.write(
            f"codenook task set-phase: invalid --phase '{phase}' for "
            f"plugin '{plugin}' profile '{profile or '<default>'}' "
            f"(valid: {', '.join(chain)})\n")
        return 2

    cur_phase = state.get("phase")
    target_idx = chain.index(phase)
    cur_idx = chain.index(cur_phase) if cur_phase in chain else len(chain)
    direction = "rewind" if target_idx < cur_idx else (
        "forward" if target_idx > cur_idx else "self")

    history = state.get("history") or []
    # Trim history of all entries whose phase is at-or-after target_idx in
    # the chain. Entries for phases not in the chain (legacy / cross-
    # plugin) are kept as-is.
    keep_history: list[dict] = []
    trimmed_phases: set[str] = set()
    for entry in history:
        ep = entry.get("phase")
        if ep in chain and chain.index(ep) >= target_idx:
            trimmed_phases.add(ep)
            continue
        keep_history.append(entry)

    # Confirm prompt unless --yes
    if not yes:
        sys.stderr.write(
            f"set-phase preview for {state.get('task_id')}:\n"
            f"  plugin/profile : {plugin} / {profile or '<default>'}\n"
            f"  current phase  : {cur_phase}\n"
            f"  target phase   : {phase} ({direction})\n"
            f"  history trim   : {len(history) - len(keep_history)} entries "
            f"(phases: {', '.join(sorted(trimmed_phases)) or '<none>'})\n"
            f"  in_flight      : "
            f"{'cleared' if state.get('in_flight_agent') else 'none'}\n"
            f"  outputs        : "
            f"{'archived to outputs/_archive/' if not keep_outputs else 'kept in place'}\n"
            f"Confirm? [y/N] ")
        sys.stderr.flush()
        try:
            ans = sys.stdin.readline().strip().lower()
        except Exception:
            ans = ""
        if ans not in ("y", "yes"):
            sys.stderr.write("aborted (pass --yes to skip this prompt)\n")
            return 1

    # Archive outputs for trimmed phases (best-effort).
    archived: list[str] = []
    if not keep_outputs and trimmed_phases:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        outputs_dir = ctx.workspace / ".codenook" / "tasks" / task / "outputs"
        archive_dir = outputs_dir / "_archive" / f"set-phase-{ts}"
        if outputs_dir.is_dir():
            archive_dir.mkdir(parents=True, exist_ok=True)
            for f in sorted(outputs_dir.glob("phase-*.md")):
                # filename like phase-4-implementer.md → phase id is whatever
                # phase the role belongs to; cheapest match is by role name
                # in filename, but role↔phase mapping isn't trivial. Safer:
                # archive any phase-N output where N is at-or-after target's
                # 1-based index.
                m = f.name.split("-", 2)
                if len(m) >= 2 and m[0] == "phase":
                    try:
                        n = int(m[1])
                    except ValueError:
                        continue
                    if n - 1 >= target_idx:
                        f.rename(archive_dir / f.name)
                        archived.append(f.name)

    # Mutate state.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["phase"] = phase
    state["in_flight_agent"] = None
    state["iteration"] = 0
    trimmed_count = len(history) - len(keep_history)
    state["history"] = keep_history
    state["history"].append({
        "ts": now,
        "phase": phase,
        "_warning": f"phase_reset_from_{cur_phase}",
    })
    state["status"] = "in_progress"
    state["phase_started_at"] = now
    state["updated_at"] = now
    if "last_tick_ts" in state:
        del state["last_tick_ts"]

    _persist_state(sf, state)
    print(json.dumps({
        "task": state.get("task_id"),
        "field": "phase",
        "value": phase,
        "direction": direction,
        "trimmed_history_entries": trimmed_count,
        "archived_outputs": archived,
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


def _prompt_choice(title: str, choices: list[str], default: str,
                   label_for=None) -> str | None:
    """Render a numbered menu for *choices* and prompt the user.

    Accepts either the 1-based index or the literal choice string.
    Returns the chosen string, or ``None`` on EOF / aborted input.
    When stdin is not a TTY AND no explicit choice is made, falls
    back to *default* after echoing the menu (keeps scripted pipes
    working while still making the decision visible in the log).
    """
    if not choices:
        return None
    label = label_for or (lambda x: x)
    sys.stdout.write(f"\n{title}:\n")
    for i, c in enumerate(choices, start=1):
        marker = " (default)" if c == default else ""
        sys.stdout.write(f"  {i}. {label(c)}{marker}\n")
    sys.stdout.flush()

    if not sys.stdin.isatty():
        sys.stdout.write(
            f"(stdin is not a TTY — auto-selecting default: {default})\n")
        sys.stdout.flush()
        return default

    for _ in range(3):
        raw = _prompt("Pick one (number or name)", default=default)
        if raw is _PROMPT_EOF:
            return None
        pick = raw.strip()
        if not pick:
            return default
        if pick.isdigit():
            idx = int(pick)
            if 1 <= idx <= len(choices):
                return choices[idx - 1]
            sys.stdout.write(
                f"  ! out of range (1..{len(choices)}); try again.\n")
            continue
        if pick in choices:
            return pick
        sys.stdout.write(
            f"  ! '{pick}' is not one of: {', '.join(choices)}; try again.\n")
    sys.stderr.write(
        f"{title}: too many invalid attempts; aborting.\n")
    return None


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


def _task_suggest_parent(ctx: CodenookContext, args: list[str]) -> int:
    """Thin wrapper around `parent_suggester.suggest_parents()`.

    Exposes the kernel's existing Jaccard-based parent-suggestion lib
    (already used internally by router-agent during dispatch) as a CLI
    surface the conductor can call BEFORE `task new` to detect
    duplicate / sibling work and offer the user the choice to chain or
    resume instead of creating yet another orphan task. The library
    itself owns the ranking, threshold semantics, and audit trail —
    this wrapper only re-uses its argparse via `parent_suggester.cli_main`.
    """
    if args and args[0] in ("-h", "--help"):
        print(HELP_SUGGEST_PARENT)
        return 0

    # The library lives in skills/builtin/_lib/, which load_context()
    # has already prepended to sys.path; the import resolves at call
    # time to avoid an import-order coupling.
    import parent_suggester  # type: ignore[import-not-found]

    # Always pin the library's --workspace flag to the resolved CodeNook
    # workspace from this invocation; users supplying their own
    # --workspace get a clear error rather than two competing values.
    if any(a == "--workspace" for a in args):
        sys.stderr.write(
            "codenook task suggest-parent: --workspace is not accepted "
            "(the kernel pins it to the active workspace)\n")
        return 2

    forwarded = ["--workspace", str(ctx.workspace), *args]
    return parent_suggester.cli_main(forwarded)


# ---------------------------------------------------------------------------
# task list / task delete (v0.27.9)
# ---------------------------------------------------------------------------

def _split_csv_repeatable(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        for piece in str(v).split(","):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out


def _hitl_pending_for(workspace: Path, task_id: str) -> list[str]:
    """Return basenames of pending HITL queue files for *task_id*.

    A pending entry is any ``.json`` directly under
    ``.codenook/hitl-queue/`` whose JSON body has ``task_id == task_id``
    AND that has not been moved into the ``_consumed/`` sibling.

    The implementation reads each JSON to match by its ``task_id``
    field rather than by filename prefix. This avoids false positives
    when the workspace contains both ``T-1`` and ``T-10``: filename
    ``T-10-foo_signoff.json`` starts with ``T-1-`` lexically only when
    the writer uses zero-padded ids; relying on JSON content removes
    that fragility entirely.

    Files that fail to parse are skipped silently — they would also
    be invisible to ``codenook hitl list`` and so should not block
    delete / list either.
    """
    q = workspace / ".codenook" / "hitl-queue"
    if not q.is_dir():
        return []
    out: list[str] = []
    for entry in sorted(q.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".json"):
            continue
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("task_id") == task_id:
            out.append(entry.name)
    return out


def _collect_task_records(ctx: CodenookContext) -> list[dict]:
    """Walk active task dirs and return a list of summary dicts.

    Each dict has: task_id (state.json's task_id, falls back to dir
    name), dir_name, title, plugin, profile, phase, status,
    model_override, hitl_pending (list of queue basenames),
    updated_at.

    The HITL pending list is sourced by reading every queue JSON's
    ``task_id`` field (see ``_hitl_pending_for``), so two tasks whose
    dir names are prefixes of each other can never cross-pollute the
    list.
    """
    rows: list[dict] = []
    tasks_dir = ctx.workspace / ".codenook" / "tasks"
    for d in iter_active_task_dirs(tasks_dir):
        sf = d / "state.json"
        try:
            s = json.loads(sf.read_text(encoding="utf-8"))
        except Exception:
            s = {}
        canonical = s.get("task_id") or d.name
        rows.append({
            "task_id": canonical,
            "dir_name": d.name,
            "title": s.get("title") or "",
            "plugin": s.get("plugin") or "",
            "profile": s.get("profile") or "",
            "phase": s.get("phase") or "",
            "status": s.get("status") or "",
            "model_override": s.get("model_override") or "",
            "execution_mode": s.get("execution_mode") or "sub-agent",
            "updated_at": s.get("updated_at") or "",
            "parent_id": s.get("parent_id") or "",
            "hitl_pending": _hitl_pending_for(ctx.workspace, canonical),
        })
    return rows


# Status groups for the human table; everything else (incl. unknown
# strings) lands in "other".
_LIST_GROUPS = (
    ("in_progress", "In progress"),
    ("waiting",     "Waiting (HITL / blocked)"),
    ("done",        "Done"),
)


def _task_list(ctx: CodenookContext, args: list[str]) -> int:
    statuses: list[str] = []
    phases: list[str] = []
    plugin = ""
    include_done = False
    as_json = False
    as_tree = False

    it = iter(args)
    try:
        for a in it:
            if a in ("-h", "--help"):
                sys.stdout.write(HELP_LIST)
                return 0
            if a == "--status":
                statuses.append(next(it))
            elif a == "--phase":
                phases.append(next(it))
            elif a == "--plugin":
                plugin = next(it)
            elif a == "--include-done":
                include_done = True
            elif a == "--json":
                as_json = True
            elif a == "--tree":
                as_tree = True
            else:
                sys.stderr.write(f"codenook task list: unknown arg: {a}\n")
                sys.stderr.write(HELP_LIST)
                return 2
    except StopIteration:
        sys.stderr.write("codenook task list: missing value for last flag\n")
        return 2

    statuses = _split_csv_repeatable(statuses)
    phases = _split_csv_repeatable(phases)

    all_rows = _collect_task_records(ctx)
    rows = list(all_rows)
    if statuses:
        rows = [r for r in rows if r["status"] in statuses]
    if phases:
        rows = [r for r in rows if r["phase"] in phases]
    if plugin:
        rows = [r for r in rows if r["plugin"] == plugin]

    if as_json:
        sys.stdout.write(json.dumps(rows, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
        return 0

    if not rows:
        print("(no tasks)")
        return 0

    if as_tree:
        return _print_task_tree(ctx, all_rows, rows)

    by_group: dict[str, list[dict]] = {k: [] for k, _ in _LIST_GROUPS}
    by_group["other"] = []
    for r in rows:
        st = r["status"]
        if st in by_group:
            by_group[st].append(r)
        elif st == "done":
            by_group["done"].append(r)
        else:
            by_group["other"].append(r)

    print(f"Workspace: {ctx.workspace}")
    print(f"Total tasks: {len(rows)}")
    print("")

    pending_total = 0
    for key, label in _LIST_GROUPS:
        bucket = by_group.get(key, [])
        if key == "done" and not include_done and not statuses:
            continue
        if not bucket:
            continue
        print(f"{label} ({len(bucket)}):")
        for r in bucket:
            extras = []
            if r["plugin"]:
                extras.append(f"plugin={r['plugin']}")
            if r["profile"]:
                extras.append(f"profile={r['profile']}")
            if r["model_override"]:
                extras.append(f"model={r['model_override']}")
            extra_s = (" [" + " ".join(extras) + "]") if extras else ""
            hitl = r["hitl_pending"]
            hitl_s = f"  ⚠ HITL pending: {len(hitl)}" if hitl else ""
            pending_total += len(hitl)
            title = r["title"] or "(no title)"
            print(f"  {r['dir_name']}  phase={r['phase'] or '-'}  "
                  f"status={r['status'] or '-'}  — {title}{extra_s}{hitl_s}")
        print("")

    others = by_group.get("other", [])
    if others:
        print(f"Other ({len(others)}):")
        for r in others:
            print(f"  {r['dir_name']}  phase={r['phase'] or '-'}  "
                  f"status={r['status'] or '-'}  — {r['title'] or '(no title)'}")
        print("")

    if not include_done and not statuses:
        done_n = len(by_group.get("done", []))
        if done_n:
            print(f"(+{done_n} done — pass --include-done to show them)")

    if pending_total:
        print(f"⚠ {pending_total} HITL queue entr"
              f"{'y' if pending_total == 1 else 'ies'} pending review.")

    return 0


def _print_task_tree(ctx: CodenookContext,
                     all_rows: list[dict],
                     visible_rows: list[dict]) -> int:
    """Render tasks as a parent → child tree.

    *all_rows* is the unfiltered universe (so we can resolve parents
    that the filter dropped, surfaced as ``[filtered]`` placeholders);
    *visible_rows* is what the operator's filters kept.
    """
    by_id: dict[str, dict] = {}
    for r in all_rows:
        by_id[r["task_id"]] = r
        # Also index by dir_name so parent_id linking is forgiving:
        # the kernel may write either form depending on age.
        if r["dir_name"] != r["task_id"]:
            by_id[r["dir_name"]] = r

    visible_ids = {r["task_id"] for r in visible_rows}

    # Build children adjacency. Roots = visible tasks whose parent is
    # missing/unknown OR whose parent is invisible (so the visible
    # subtree still has somewhere to anchor).
    children: dict[str, list[dict]] = {}
    roots: list[dict] = []
    for r in visible_rows:
        pid = r["parent_id"]
        parent_row = by_id.get(pid) if pid else None
        if parent_row and parent_row["task_id"] in visible_ids:
            children.setdefault(parent_row["task_id"], []).append(r)
        else:
            roots.append(r)

    # Stable sort: roots and siblings alphabetised by dir_name.
    roots.sort(key=lambda r: r["dir_name"])
    for k in children:
        children[k].sort(key=lambda r: r["dir_name"])

    print(f"Workspace: {ctx.workspace}")
    print(f"Total tasks (visible): {len(visible_rows)}")
    print("")

    seen: set[str] = set()
    pending_total = 0

    def _emit(node: dict, depth: int) -> None:
        nonlocal pending_total
        if node["task_id"] in seen:
            print(f"{'  ' * depth}↻ {node['dir_name']}  (cycle)")
            return
        seen.add(node["task_id"])
        hitl = node["hitl_pending"]
        pending_total += len(hitl)
        hitl_s = f"  ⚠ HITL pending: {len(hitl)}" if hitl else ""
        title = node["title"] or "(no title)"
        prefix = "  " * depth + ("- " if depth else "")
        print(f"{prefix}{node['dir_name']}  "
              f"[{node['status'] or '-'}/{node['phase'] or '-'}]  "
              f"— {title}{hitl_s}")
        for child in children.get(node["task_id"], []):
            _emit(child, depth + 1)

    for root in roots:
        _emit(root, 0)

    leftover = [r for r in visible_rows if r["task_id"] not in seen]
    if leftover:
        print("")
        print("Unreachable (parent_id loop or stale link):")
        for r in leftover:
            print(f"  {r['dir_name']}  parent_id={r['parent_id'] or '-'}")

    if pending_total:
        print("")
        print(f"⚠ {pending_total} HITL queue entr"
              f"{'y' if pending_total == 1 else 'ies'} pending review.")
    return 0


# ── task show ────────────────────────────────────────────────────────────


HELP_SHOW = """\
Usage: codenook task show <T-NNN> [--json] [--history-limit N]

Print the full details of a single task — core identity fields,
current phase + status, 4-layer model resolution inputs, parent /
chain linkage, pending HITL gates, and an abbreviated history.

Options:
  --json                 emit the parsed state.json merged with
                         derived fields (pending_hitl, title, etc.)
                         as one JSON object on stdout
  --history-limit N      show only the most recent N history
                         entries (default: 5; use 0 to hide,
                         negative to show all)

Exit codes:
  0  task found and printed
  1  task not found (no dir under .codenook/tasks/<id>)
  2  usage error
"""


def _task_show(ctx: CodenookContext, args: list[str]) -> int:
    partial = ""
    as_json = False
    history_limit = 5
    it = iter(args)
    try:
        for a in it:
            if a in ("-h", "--help"):
                print(HELP_SHOW)
                return 0
            if a == "--json":
                as_json = True
            elif a == "--history-limit":
                try:
                    history_limit = int(next(it))
                except (StopIteration, ValueError):
                    sys.stderr.write(
                        "codenook task show: --history-limit expects "
                        "an integer\n")
                    return 2
            elif a.startswith("--"):
                sys.stderr.write(
                    f"codenook task show: unknown flag: {a}\n")
                return 2
            elif not partial:
                partial = a
            else:
                sys.stderr.write(
                    "codenook task show: only one task id allowed\n")
                return 2
    except StopIteration:
        pass

    if not partial:
        sys.stderr.write("codenook task show: <T-NNN> required\n")
        return 2

    resolved, rc = _resolve_or_error(ctx, partial, "show")
    if resolved is None:
        return rc

    sf = ctx.workspace / ".codenook" / "tasks" / resolved / "state.json"
    try:
        state = json.loads(sf.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(
            f"codenook task show: unable to read state.json: {exc}\n")
        return 1
    if not isinstance(state, dict):
        sys.stderr.write(
            f"codenook task show: state.json is not a JSON object\n")
        return 1

    pending = _hitl_pending_for(ctx.workspace, resolved)

    if as_json:
        out = dict(state)
        out["_resolved_task"] = resolved
        out["pending_hitl"] = pending
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    def _val(k: str, default: str = "—") -> str:
        v = state.get(k)
        if v is None or v == "":
            return default
        return str(v)

    print(f"Task: {resolved}")
    print(f"  title        : {_val('title')}")
    if state.get("summary"):
        print(f"  summary      : {state.get('summary')}")
    print(f"  plugin       : {_val('plugin')}")
    print(f"  profile      : {_val('profile', '(plugin default)')}")
    print(f"  phase        : {_val('phase')}")
    print(f"  status       : {_val('status')}")
    print(f"  priority     : {_val('priority', 'P2')}")
    print(f"  dual_mode    : {_val('dual_mode')}")
    exec_mode = state.get("execution_mode") or "sub-agent"
    print(f"  exec_mode    : {exec_mode}")
    print(f"  max_iter     : {_val('max_iterations')}")
    if state.get("model_override"):
        print(f"  model_over.  : {state.get('model_override')}")
    if state.get("parent_id"):
        print(f"  parent_id    : {state.get('parent_id')}")
    if state.get("chain_root"):
        print(f"  chain_root   : {state.get('chain_root')}")
    if state.get("target_dir"):
        print(f"  target_dir   : {state.get('target_dir')}")
    print(f"  schema_ver   : {_val('schema_version', '1')}")
    print(f"  created_at   : {_val('created_at')}")
    print(f"  updated_at   : {_val('updated_at')}")

    ifa = state.get("in_flight_agent") or {}
    if isinstance(ifa, dict) and ifa:
        print("")
        print("In-flight agent:")
        print(f"  role         : {ifa.get('role') or '—'}")
        print(f"  expected     : {ifa.get('expected_output') or '—'}")
        if ifa.get("dispatched_at"):
            print(f"  dispatched   : {ifa.get('dispatched_at')}")

    task_input = state.get("task_input") or ""
    if task_input:
        print("")
        print("Input:")
        for line in task_input.splitlines()[:10]:
            print(f"  {line}")
        extra = len(task_input.splitlines()) - 10
        if extra > 0:
            print(f"  … ({extra} more line{'s' if extra > 1 else ''})")

    if pending:
        print("")
        print(f"Pending HITL ({len(pending)}):")
        for gate in pending:
            print(f"  - {gate}")

    history = state.get("history") or []
    if history_limit == 0 or not isinstance(history, list):
        pass
    elif history:
        total = len(history)
        if history_limit < 0:
            shown = history
            hidden = 0
        else:
            shown = history[-history_limit:]
            hidden = total - len(shown)
        print("")
        title = (f"History (last {len(shown)} of {total}):"
                 if hidden else f"History ({total}):")
        print(title)
        for h in shown:
            if not isinstance(h, dict):
                print(f"  - {h}")
                continue
            ph = h.get("phase") or "?"
            verdict = h.get("verdict") or h.get("status") or "?"
            ts = h.get("ts") or h.get("at") or h.get("timestamp") or ""
            note = h.get("note") or h.get("_warning") or ""
            line = f"  - [{ts}] {ph:<10} → {verdict}"
            if note:
                line += f"  ({note})"
            print(line)
        if hidden:
            print(f"  … ({hidden} earlier entr"
                  f"{'y' if hidden == 1 else 'ies'} hidden)")
    return 0


def _task_delete(ctx: CodenookContext, args: list[str]) -> int:
    import shutil
    from datetime import datetime, timezone

    explicit_ids: list[str] = []
    bulk_status: list[str] = []
    purge = False
    force = False
    yes = False
    dry_run = False
    as_json = False

    it = iter(args)
    try:
        for a in it:
            if a in ("-h", "--help"):
                sys.stdout.write(HELP_DELETE)
                return 0
            if a == "--task":
                explicit_ids.append(next(it))
            elif a == "--status":
                bulk_status.append(next(it))
            elif a == "--purge":
                purge = True
            elif a == "--force":
                force = True
                yes = True  # --force implies skipping the y/N prompt
            elif a == "--yes":
                yes = True
            elif a == "--dry-run":
                dry_run = True
            elif a == "--json":
                as_json = True
            elif a.startswith("-"):
                sys.stderr.write(f"codenook task delete: unknown flag: {a}\n")
                sys.stderr.write(HELP_DELETE)
                return 2
            else:
                explicit_ids.append(a)
    except StopIteration:
        sys.stderr.write("codenook task delete: missing value for last flag\n")
        return 2

    bulk_status = _split_csv_repeatable(bulk_status)

    selected: dict[str, dict] = {}
    rc_resolve = 0

    for raw in explicit_ids:
        resolved, candidates = resolve_task_id(ctx.workspace, raw)
        if resolved is None:
            if candidates:
                sys.stderr.write(
                    f"codenook task delete: ambiguous id {raw}; "
                    f"candidates: {', '.join(candidates)}\n")
            else:
                sys.stderr.write(
                    f"codenook task delete: no such task: {raw}\n")
            rc_resolve = 1
            continue
        selected.setdefault(resolved, {"source": "explicit"})

    if bulk_status:
        for r in _collect_task_records(ctx):
            if r["status"] in bulk_status:
                selected.setdefault(r["dir_name"], {"source": "status"})

    if not selected:
        sys.stderr.write(
            "codenook task delete: no tasks selected — supply T-NNN ids "
            "and/or --status <s>\n")
        return 2 if rc_resolve == 0 else 1

    tasks_dir = ctx.workspace / ".codenook" / "tasks"
    queue_dir = ctx.workspace / ".codenook" / "hitl-queue"

    plan: list[dict] = []
    for tid in sorted(selected):
        sf = tasks_dir / tid / "state.json"
        status = ""
        canonical = tid
        try:
            s = json.loads(sf.read_text(encoding="utf-8"))
            status = s.get("status") or ""
            canonical = s.get("task_id") or tid
        except Exception:
            pass
        if status == "in_progress" and not force:
            sys.stderr.write(
                f"codenook task delete: refusing to delete {tid} "
                f"(status=in_progress) — pass --force to override\n")
            rc_resolve = 1
            continue
        # Match HITL queue entries by JSON ``task_id`` field — never by
        # filename prefix (would mis-claim T-10's files when deleting
        # T-1, etc).
        hitl_files = (
            _hitl_pending_for(ctx.workspace, canonical)
            if queue_dir.is_dir() else []
        )
        plan.append({
            "dir_name": tid,
            "task_id": canonical,
            "status": status,
            "hitl_pending": hitl_files,
        })

    if not plan:
        return rc_resolve or 1

    action_word = "purge (rm -rf)" if purge else "archive"
    if not yes and not dry_run:
        sys.stderr.write(
            f"About to {action_word} {len(plan)} task(s):\n")
        for p in plan:
            extra = (f" (+{len(p['hitl_pending'])} HITL queue files)"
                     if p["hitl_pending"] else "")
            sys.stderr.write(
                f"  - {p['dir_name']}  status={p['status'] or '-'}{extra}\n")
        sys.stderr.write("Proceed? [y/N] ")
        sys.stderr.flush()
        try:
            answer = sys.stdin.readline().strip().lower()
        except KeyboardInterrupt:
            sys.stderr.write("\naborted.\n")
            return 1
        if answer not in ("y", "yes"):
            sys.stderr.write("aborted.\n")
            return 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_root = tasks_dir / "_archive"
    consumed_root = queue_dir / "_consumed"

    results: list[dict] = []
    rc = rc_resolve
    for p in plan:
        tid = p["dir_name"]
        src = tasks_dir / tid
        moved_hitl: list[str] = []
        try:
            if dry_run:
                pass
            elif purge:
                if src.exists():
                    shutil.rmtree(src)
                for name in p["hitl_pending"]:
                    f = queue_dir / name
                    if f.exists():
                        f.unlink()
                # Sidecar .html companions: derive their names by
                # swapping the .json suffix on the matched entries.
                # This stays correctly scoped (no prefix matching).
                for name in p["hitl_pending"]:
                    side = queue_dir / (name[:-5] + ".html")
                    if side.is_file():
                        try:
                            side.unlink()
                        except OSError:
                            pass
            else:
                archive_root.mkdir(parents=True, exist_ok=True)
                dest = archive_root / f"{tid}-{ts}"
                if src.exists():
                    shutil.move(str(src), str(dest))
                if p["hitl_pending"]:
                    consumed_root.mkdir(parents=True, exist_ok=True)
                    for name in p["hitl_pending"]:
                        f = queue_dir / name
                        if f.exists():
                            shutil.move(str(f), str(consumed_root / name))
                            moved_hitl.append(name)
                        # Move .html sidecar too if present.
                        side = queue_dir / (name[:-5] + ".html")
                        if side.is_file():
                            shutil.move(
                                str(side),
                                str(consumed_root / side.name))
            results.append({
                "dir_name": tid,
                "task_id": p["task_id"],
                "action": "dry-run" if dry_run else (
                    "purged" if purge else "archived"),
                "hitl_files": p["hitl_pending"] if purge else moved_hitl,
                "archive_dest": (
                    None if (dry_run or purge)
                    else str((archive_root / f"{tid}-{ts}").relative_to(
                        ctx.workspace))
                ),
            })
        except Exception as exc:
            sys.stderr.write(
                f"codenook task delete: failed for {tid}: {exc}\n")
            rc = 1
            results.append({
                "dir_name": tid, "task_id": p["task_id"],
                "action": "error", "error": str(exc),
            })

    if as_json:
        sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        for r in results:
            if r["action"] == "error":
                continue
            extra = ""
            if r.get("archive_dest"):
                extra = f" → {r['archive_dest']}"
            hitl_n = len(r.get("hitl_files") or [])
            hitl_s = f" (+{hitl_n} HITL files)" if hitl_n else ""
            print(f"{r['action']}: {r['dir_name']}{extra}{hitl_s}")

    return rc


# ── task restore ─────────────────────────────────────────────────────────

HELP_RESTORE = """\
Usage: codenook task restore [<T-NNN> | <archived-name>] [options]

Restore a task previously archived by ``codenook task delete``. Each
archived entry lives at ``.codenook/tasks/_archive/<orig>-<UTC-ts>/``;
restore moves it back to ``.codenook/tasks/<orig>/`` and (best-effort)
moves any associated HITL queue entries from
``.codenook/hitl-queue/_consumed/`` back to ``.codenook/hitl-queue/``.

Selectors (one of):
  <T-NNN>           bare positional id; if multiple archived
                    snapshots match, ``--from`` is required to
                    disambiguate.
  --task <T-NNN>    same as bare positional (repeatable).
  --from <name>     full archived dir name under
                    ``_archive/`` (e.g.
                    ``T-007-...-20260423T020000Z``).
  --list            don't restore — just list everything in
                    ``_archive/`` (with timestamps), exit 0.

Options:
  --no-hitl-restore  skip moving HITL entries from _consumed/
                     back to the active queue.
  --yes              skip the y/N confirmation.
  --dry-run          print what would happen, change nothing.
  --json             emit one JSON object per processed entry.

Refuses to overwrite an existing active task dir; remove or rename
the active one first.
"""


def _archive_entries_for(workspace: Path, prefix: str) -> list[Path]:
    """Return archived snapshots whose name starts with ``<prefix>-``.

    *prefix* is typically a bare ``T-NNN`` or a slugged dir name.
    Snapshots are named ``<prefix>-YYYYMMDDTHHMMSSZ`` so the trailing
    timestamp uniquely identifies each restore candidate.
    """
    arc = workspace / ".codenook" / "tasks" / "_archive"
    if not arc.is_dir():
        return []
    out: list[Path] = []
    needle = prefix + "-"
    for d in sorted(arc.iterdir()):
        if d.is_dir() and d.name.startswith(needle):
            out.append(d)
    return out


def _task_restore(ctx: CodenookContext, args: list[str]) -> int:
    import shutil

    explicit_ids: list[str] = []
    explicit_archives: list[str] = []
    list_only = False
    no_hitl = False
    yes = False
    dry_run = False
    as_json = False

    it = iter(args)
    try:
        for a in it:
            if a in ("-h", "--help"):
                sys.stdout.write(HELP_RESTORE)
                return 0
            if a == "--task":
                explicit_ids.append(next(it))
            elif a == "--from":
                explicit_archives.append(next(it))
            elif a == "--list":
                list_only = True
            elif a == "--no-hitl-restore":
                no_hitl = True
            elif a == "--yes":
                yes = True
            elif a == "--dry-run":
                dry_run = True
            elif a == "--json":
                as_json = True
            elif a.startswith("-"):
                sys.stderr.write(f"codenook task restore: unknown flag: {a}\n")
                sys.stderr.write(HELP_RESTORE)
                return 2
            else:
                explicit_ids.append(a)
    except StopIteration:
        sys.stderr.write(
            "codenook task restore: missing value for last flag\n")
        return 2

    arc_root = ctx.workspace / ".codenook" / "tasks" / "_archive"
    tasks_dir = ctx.workspace / ".codenook" / "tasks"
    queue_dir = ctx.workspace / ".codenook" / "hitl-queue"
    consumed_dir = queue_dir / "_consumed"

    # --list mode: show everything under _archive/.
    if list_only:
        if not arc_root.is_dir():
            print("(_archive/ is empty)")
            return 0
        entries = sorted(p for p in arc_root.iterdir() if p.is_dir())
        if not entries:
            print("(_archive/ is empty)")
            return 0
        if as_json:
            payload = [{"name": p.name,
                        "path": str(p.relative_to(ctx.workspace))}
                       for p in entries]
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            sys.stdout.write("\n")
        else:
            print(f"Archived tasks ({len(entries)}):")
            for p in entries:
                print(f"  {p.name}")
        return 0

    # Resolve each --task / positional id to an archive snapshot.
    plan: list[dict] = []
    rc_resolve = 0
    for raw in explicit_ids:
        candidates = _archive_entries_for(ctx.workspace, raw)
        if not candidates:
            sys.stderr.write(
                f"codenook task restore: no archived snapshot matching "
                f"{raw}\n")
            rc_resolve = 1
            continue
        if len(candidates) > 1:
            sys.stderr.write(
                f"codenook task restore: ambiguous {raw}; "
                f"{len(candidates)} candidates — pass --from <name>:\n")
            for c in candidates:
                sys.stderr.write(f"  {c.name}\n")
            rc_resolve = 1
            continue
        plan.append({"src": candidates[0]})

    for arc_name in explicit_archives:
        # Validate arc_name is a single safe path component (no traversal,
        # no separators) before joining onto arc_root, then verify the
        # resolved path stays inside arc_root. Without these guards, an
        # operator typo or a hostile --from value (e.g. '../../etc') would
        # let `shutil.move` later relocate arbitrary directories into
        # tasks/.
        if (
            not arc_name
            or arc_name in (".", "..")
            or "/" in arc_name
            or "\\" in arc_name
            or "\x00" in arc_name
        ):
            sys.stderr.write(
                "codenook task restore: invalid --from value: "
                f"{arc_name!r} (must be a single archive entry name)\n")
            rc_resolve = 1
            continue
        src = arc_root / arc_name
        try:
            resolved = src.resolve(strict=False)
            arc_root_resolved = arc_root.resolve(strict=False)
            resolved.relative_to(arc_root_resolved)
        except (OSError, ValueError):
            sys.stderr.write(
                "codenook task restore: --from escapes archive root: "
                f"{arc_name!r}\n")
            rc_resolve = 1
            continue
        if not src.is_dir():
            sys.stderr.write(
                f"codenook task restore: not an archive entry: {arc_name}\n")
            rc_resolve = 1
            continue
        plan.append({"src": src})

    if not plan:
        sys.stderr.write(
            "codenook task restore: no entries selected — pass <T-NNN>, "
            "--task, --from, or --list\n")
        return 2 if rc_resolve == 0 else 1

    # Resolve original dir names + check destination collisions.
    for p in plan:
        src: Path = p["src"]
        # Snapshot name = <orig>-<YYYYMMDDTHHMMSSZ>; strip 17 chars
        # ("-YYYYMMDDTHHMMSSZ") to recover the original.
        name = src.name
        orig = name[:-17] if (
            len(name) > 17 and name[-1] == "Z" and name[-17] == "-"
        ) else name
        p["orig"] = orig
        p["dest"] = tasks_dir / orig
        # Best-effort canonical task_id from the snapshot's state.json.
        canonical = orig
        try:
            s = json.loads((src / "state.json").read_text(encoding="utf-8"))
            canonical = s.get("task_id") or orig
        except Exception:
            pass
        p["task_id"] = canonical
        p["hitl_consumed"] = []
        if not no_hitl and consumed_dir.is_dir():
            for entry in sorted(consumed_dir.iterdir()):
                if not entry.is_file() or not entry.name.endswith(".json"):
                    continue
                try:
                    payload = json.loads(entry.read_text(encoding="utf-8"))
                except Exception:
                    continue
                # Only restore entries that were NEVER decided —
                # decided ones already carry their verdict and should
                # stay in _consumed/ as audit history.
                if (payload.get("task_id") == canonical
                        and not payload.get("decision")):
                    p["hitl_consumed"].append(entry.name)

    if not yes and not dry_run:
        sys.stderr.write(f"About to restore {len(plan)} task(s):\n")
        for p in plan:
            extra = (f" (+{len(p['hitl_consumed'])} HITL entries)"
                     if p["hitl_consumed"] else "")
            collide = " ⚠ destination exists" if p["dest"].exists() else ""
            sys.stderr.write(
                f"  - {p['src'].name} → tasks/{p['orig']}{extra}{collide}\n")
        sys.stderr.write("Proceed? [y/N] ")
        sys.stderr.flush()
        try:
            answer = sys.stdin.readline().strip().lower()
        except KeyboardInterrupt:
            sys.stderr.write("\naborted.\n")
            return 1
        if answer not in ("y", "yes"):
            sys.stderr.write("aborted.\n")
            return 1

    results: list[dict] = []
    rc = rc_resolve
    for p in plan:
        src: Path = p["src"]
        dest: Path = p["dest"]
        try:
            if dest.exists():
                sys.stderr.write(
                    f"codenook task restore: destination exists, "
                    f"refusing to overwrite: {dest.relative_to(ctx.workspace)}\n")
                rc = 1
                results.append({
                    "snapshot": src.name, "task_id": p["task_id"],
                    "action": "error", "error": "destination_exists",
                })
                continue
            restored_hitl: list[str] = []
            if dry_run:
                pass
            else:
                shutil.move(str(src), str(dest))
                if p["hitl_consumed"]:
                    queue_dir.mkdir(parents=True, exist_ok=True)
                    for name in p["hitl_consumed"]:
                        f = consumed_dir / name
                        if f.exists():
                            shutil.move(str(f), str(queue_dir / name))
                            restored_hitl.append(name)
                        # html sidecar:
                        side = consumed_dir / (name[:-5] + ".html")
                        if side.is_file():
                            shutil.move(
                                str(side), str(queue_dir / side.name))
            results.append({
                "snapshot": src.name,
                "task_id": p["task_id"],
                "action": "dry-run" if dry_run else "restored",
                "destination": str(dest.relative_to(ctx.workspace)),
                "hitl_files": (
                    p["hitl_consumed"] if dry_run else restored_hitl),
            })
        except Exception as exc:
            sys.stderr.write(
                f"codenook task restore: failed for {src.name}: {exc}\n")
            rc = 1
            results.append({
                "snapshot": src.name, "task_id": p["task_id"],
                "action": "error", "error": str(exc),
            })

    if as_json:
        sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        for r in results:
            if r["action"] == "error":
                continue
            hitl_n = len(r.get("hitl_files") or [])
            hitl_s = f" (+{hitl_n} HITL files)" if hitl_n else ""
            print(f"{r['action']}: {r['snapshot']} → {r['destination']}{hitl_s}")

    return rc
