#!/usr/bin/env python3
"""router-agent context-prep + handoff helper.

Invoked by spawn.sh. Acquires the per-task fcntl lock for the entire
duration, then either:

  * (default)   prepares context, renders the system prompt to
                ``tasks/<tid>/.router-prompt.md``, and emits an
                ``action: prompt`` envelope on stdout.
  * (--confirm) validates the existing draft-config, materialises
                ``state.json``, runs one ``orchestrator-tick``, and
                emits an ``action: handoff`` envelope.

All domain knowledge lives in ``prompt.md`` (the subagent's system
prompt). This script is deterministic file I/O only.

Path conventions (per docs/architecture.md and tick.sh):

    <workspace>/.codenook/tasks/<T-NNN>/      # router state + state.json
    <workspace>/.codenook/plugins/<id>/       # plugin manifests
    <workspace>/.codenook/user-overlay/       # workspace overlay (M8.9)

The plugin / role / knowledge indexes scan ``<root>/plugins/`` so we
pass ``<workspace>/.codenook`` as their workspace_root. The overlay
helper expects the project root and adds ``.codenook/user-overlay/``
itself, so it gets ``<workspace>`` directly.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_LIB = _HERE.parent / "_lib"
sys.path.insert(0, str(_LIB))

import chain_summarize as cs    # noqa: E402  (M10.5 - {{TASK_CHAIN}} slot)
import draft_config as dc          # noqa: E402
import extract_audit as ea         # noqa: E402  (v0.11 MINOR-04 / MINOR-06)
import knowledge_index as ki       # noqa: E402  (kept for prompt-side reference)
import memory_layer as ml          # noqa: E402  (M9.6 — match_entries_for_task)
import parent_suggester as ps      # noqa: E402  (M10.3 — top-3 candidates)
import plugin_manifest_index as pmi  # noqa: E402
import role_index as ri            # noqa: E402
import router_context as rc        # noqa: E402
import task_chain as tc            # noqa: E402  (M10.3 — set_parent on confirm)
import task_lock as tl             # noqa: E402
import workspace_overlay as wo     # noqa: E402
from atomic import atomic_write_json  # noqa: E402

PROMPT_PATH = _HERE / "prompt.md"


# ---------------------------------------------------------------- helpers


def _emit(envelope: dict) -> None:
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _render_plugins(plugins_summary: list[dict],
                    roles_by_plugin: dict[str, list[dict]]) -> str:
    if not plugins_summary:
        return "_(no plugins installed)_"
    out: list[str] = []
    for p in plugins_summary:
        name = p["name"]
        roles = roles_by_plugin.get(name, [])
        if roles:
            role_lines = "\n".join(
                f"    - **{r.get('role', '?')}** "
                f"(phase={r.get('phase', '?')}): "
                f"{r.get('one_line_job', '') or '(no one-line job)'}"
                for r in roles
            )
        else:
            role_lines = "    _(no roles declared)_"
        keywords = ", ".join(p.get("keywords") or []) or "_(none)_"
        applies_to = ", ".join(p.get("applies_to") or []) or "_(none)_"
        out.append(
            f"### `{name}` (priority {p.get('priority')})\n"
            f"{p.get('description') or '_(no description)_'}\n"
            f"- keywords: {keywords}\n"
            f"- applies_to: {applies_to}\n"
            f"- roles:\n{role_lines}"
        )
    return "\n\n".join(out)


def _render_roles_index(roles_by_plugin: dict[str, list[dict]]) -> str:
    rows: list[str] = []
    for plugin, roles in sorted(roles_by_plugin.items()):
        for r in roles:
            rows.append(
                f"- `{plugin}` / `{r.get('role', '?')}` "
                f"(phase={r.get('phase', '?')}): "
                f"{r.get('one_line_job', '') or '(no one-line job)'}"
            )
    return "\n".join(rows) or "_(no roles discovered)_"


def _render_overlay(overlay: dict) -> str:
    if not overlay.get("present"):
        return "_(no workspace user-overlay present)_"
    desc = (overlay.get("description") or "").strip() or "(empty)"
    skills = overlay.get("skills") or []
    knowl = overlay.get("knowledge") or []
    skill_names = ", ".join(s.get("name", "?") for s in skills) or "(none)"
    knowl_titles = ", ".join(
        (k.get("title") or k.get("path", "?")) for k in knowl
    ) or "(none)"
    return (
        f"present: yes\n\n"
        f"**description.md**:\n```\n{desc}\n```\n\n"
        f"- overlay-skills: {skill_names}\n"
        f"- overlay-knowledge: {knowl_titles}"
    )


def _build_task_brief(ctx: dict, user_turn: str) -> str:
    """Concatenate every user-authored snippet so far so the matcher
    has the broadest possible token set (M9.6)."""
    parts: list[str] = []
    if user_turn:
        parts.append(user_turn)
    for t in ctx.get("turns", []):
        if t.get("role") == "user":
            parts.append(str(t.get("content") or ""))
    return " ".join(p for p in parts if p)


def _render_memory_index(matches: list[dict]) -> str:
    """Render the M9.6 MEMORY_INDEX block (one line per matched entry).

    Empty match set yields an explicit ``empty`` marker so the LLM
    knows we *checked* and found nothing (vs the section being omitted
    by accident)."""
    if not matches:
        return (
            "## MEMORY_INDEX (M9.6): empty\n"
            "_(no memory entries matched this task brief)_"
        )
    header = (
        "## MEMORY_INDEX (M9.6)\n"
        "The following memory entries match this task brief "
        "(applies_when ∩ brief tokens). Cite by `path` when applying.\n"
    )
    lines: list[str] = []
    for m in matches:
        aw = m.get("applies_when") or "always"
        path = m.get("path", "?")
        title = m.get("title") or m.get("key") or path
        summary = (m.get("summary") or "").strip()
        suffix = f" — {summary}" if summary else ""
        lines.append(
            f"- [{m['asset_type']}] {path} "
            f"(title: {title}, applies_when: {aw}){suffix}"
        )
    return header + "\n".join(lines)


def _render_parent_suggestions(suggestions: list) -> str:
    """Render the M10.3 parent-suggestion menu.

    ``suggestions`` is the list returned by ``parent_suggester.suggest_parents``
    (NamedTuples with task_id/title/score/reason). Always includes the
    ``0. independent (no parent)`` sentinel as the last menu line.
    """
    header = "## Suggested parents"
    if not suggestions:
        return (
            f"{header}\n\n_(none above threshold)_\n\n"
            "0. independent (no parent)"
        )
    lines = [header, ""]
    for idx, s in enumerate(suggestions[:3], start=1):
        score = getattr(s, "score", 0.0)
        reason = getattr(s, "reason", "") or ""
        lines.append(
            f"{idx}. {s.task_id} (score={score:.2f}) — {reason}"
        )
    lines.append("")
    lines.append("0. independent (no parent)")
    return "\n".join(lines)


def _render_turns(turns: list[dict]) -> str:
    if not turns:
        return "_(no turns recorded yet)_"
    blocks: list[str] = []
    for t in turns:
        blocks.append(
            f"### {t.get('role', '?')} ({t.get('timestamp', '')})\n\n"
            f"{t.get('content', '')}"
        )
    return "\n\n".join(blocks)


def _render_task_chain(workspace: Path, task_id: str, state: dict) -> str:
    """M10.5 - render the {{TASK_CHAIN}} slot.

    Spec: docs/task-chains.md section 7.2. Returns "" when the task is
    a chain root (no parent_id) or when state is missing/empty (first
    spawn before state.json exists). Any unhandled cs.summarize error
    is swallowed (cs.summarize itself audits internal failures).
    """
    if not state or state.get("parent_id") is None:
        return ""
    try:
        return cs.summarize(workspace, task_id)
    except Exception:
        return ""


def _render_task_context(workspace: Path, task_id: str) -> str:
    """Render the {{TASK_CONTEXT}} slot using task-extracted artefacts."""
    try:
        return ml.build_task_context(workspace, task_id)
    except Exception:
        return ""


def render_prompt(*, task_id: str, workspace: Path,
                  codenook_root: Path, ctx: dict,
                  user_turn: str,
                  parent_suggestions: list | None = None,
                  state: dict | None = None) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    plugins = pmi.discover_plugins(codenook_root)
    plugins_summary = pmi.summary_for_router(plugins)
    roles_by_plugin = ri.aggregate_roles(codenook_root)
    overlay = wo.overlay_bundle(workspace)

    # M9.6 — deterministic applies_when matcher (no LLM inline).
    task_brief = _build_task_brief(ctx, user_turn)
    try:
        memory_matches = ml.match_entries_for_task(
            workspace, task_brief, source_task=task_id,
        )
    except Exception:
        memory_matches = []

    fm_yaml = yaml.safe_dump(
        ctx["frontmatter"], sort_keys=False, allow_unicode=True
    ).rstrip()

    user_block = user_turn.strip() if user_turn else \
        "(no new user turn this spawn)"

    subs = {
        "{{TASK_ID}}": task_id,
        "{{WORKSPACE}}": str(workspace),
        "{{PLUGINS_SUMMARY}}": _render_plugins(
            plugins_summary, roles_by_plugin
        ),
        "{{ROLES}}": _render_roles_index(roles_by_plugin),
        "{{OVERLAY}}": _render_overlay(overlay),
        "{{TASK_CHAIN}}": _render_task_chain(workspace, task_id, state or {}),
        "{{TASK_CONTEXT}}": _render_task_context(workspace, task_id),
        "{{MEMORY_INDEX}}": _render_memory_index(memory_matches),
        "{{PARENT_SUGGESTIONS}}": _render_parent_suggestions(
            parent_suggestions or []
        ),
        "{{CONTEXT_FRONTMATTER}}": fm_yaml,
        "{{CONTEXT}}": _render_turns(ctx["turns"]),
        "{{USER_TURN}}": user_block,
    }
    out = template
    for k, v in subs.items():
        out = out.replace(k, v)

    # v0.11 MINOR-04 — guard against substitution-recursion edge case:
    # if any slot value re-introduced a literal `{{...}}` token, emit a
    # diagnostic so operators can spot accidental double-templating.
    # Single-pass substitution is intentional (no shell expansion); the
    # diagnostic merely surfaces the residual rather than blocking.
    if "{{" in out and "}}" in out:
        try:
            _emit_render_residual_diag(workspace, task_id, out)
        except Exception:
            pass

    return out


_RESIDUAL_RE = __import__("re").compile(r"\{\{([A-Z_]+)\}\}")


def _emit_render_residual_diag(workspace: Path, task_id: str,
                                rendered: str) -> None:
    """Emit a `chain_render_residual_slot` diagnostic when a rendered
    prompt still contains a `{{SLOT}}` token after substitution
    (v0.11 MINOR-04). Best-effort; never raises."""
    matches = _RESIDUAL_RE.findall(rendered or "")
    if not matches:
        return
    rec = {
        "asset_type": "chain",
        "candidate_hash": "",
        "existing_path": None,
        "outcome": "diagnostic",
        "reason": ",".join(sorted(set(matches))[:5]),
        "source_task": task_id,
        "timestamp": ea._now_iso(),
        "verdict": "noop",
        "kind": "chain_render_residual_slot",
    }
    ml.append_audit(workspace, rec)


def _maybe_audit_stale_parent(workspace: Path, child_task_id: str,
                               parent_id: str) -> None:
    """v0.11 MINOR-06 — emit `chain_parent_stale` diagnostic when the
    confirmed parent transitioned to done/cancelled between prepare
    and confirm. Best-effort; never raises."""
    state_path = (
        Path(workspace) / ".codenook" / "tasks" / parent_id / "state.json"
    )
    if not state_path.is_file():
        return
    try:
        with state_path.open("r", encoding="utf-8") as f:
            parent_state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    status = parent_state.get("status")
    if status not in ("done", "cancelled"):
        return
    rec = {
        "asset_type": "chain",
        "candidate_hash": "",
        "existing_path": None,
        "outcome": "diagnostic",
        "reason": f"parent={parent_id},parent_status={status}",
        "source_task": child_task_id,
        "timestamp": ea._now_iso(),
        "verdict": "noop",
        "kind": "chain_parent_stale",
    }
    ml.append_audit(workspace, rec)


# ---------------------------------------------------------------- modes


def _read_user_turn(args: argparse.Namespace) -> str:
    if args.user_turn and args.user_turn_file:
        raise SystemExit(
            "router-agent: --user-turn and --user-turn-file are mutually "
            "exclusive"
        )
    if args.user_turn_file:
        return Path(args.user_turn_file).read_text(encoding="utf-8")
    return args.user_turn or ""


def cmd_prepare(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    codenook = workspace / ".codenook"
    task_dir = codenook / "tasks" / args.task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    ctx_path = task_dir / "router-context.md"
    draft_path = task_dir / "draft-config.yaml"
    reply_path = task_dir / "router-reply.md"
    prompt_path = task_dir / ".router-prompt.md"

    user_turn = _read_user_turn(args)

    if not ctx_path.exists():
        seed = user_turn or "(no initial input — awaiting user)"
        fm, turns = rc.initial_context(args.task_id, seed)
        rc.write_context(task_dir, fm, turns)
        if not draft_path.exists():
            draft_path.write_text("", encoding="utf-8")
    else:
        if user_turn.strip():
            rc.append_turn(task_dir, "user", user_turn)

    ctx = rc.read_context(task_dir)

    # M10.5 - load state.json if present so {{TASK_CHAIN}} can decide
    # whether to invoke chain_summarize. First-spawn case: file does
    # not yet exist -> state={} -> slot renders empty.
    state_path = task_dir / "state.json"
    state: dict = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}

    # M10.3 — surface top-3 parent candidates. Failures here MUST not
    # break prepare; suggester already audits its own errors.
    child_brief = _build_task_brief(ctx, user_turn)
    parent_suggestions: list = []
    if child_brief.strip():
        try:
            parent_suggestions = ps.suggest_parents(
                workspace=workspace,
                child_brief=child_brief,
                top_k=3,
                threshold=0.15,
                exclude_task_ids={args.task_id},
            )
        except Exception:
            parent_suggestions = []

    rendered = render_prompt(
        task_id=args.task_id,
        workspace=workspace,
        codenook_root=codenook,
        ctx=ctx,
        user_turn=user_turn,
        parent_suggestions=parent_suggestions,
        state=state,
    )
    prompt_path.write_text(rendered, encoding="utf-8")

    _emit({
        "action": "prompt",
        "task_id": args.task_id,
        "prompt_path": _rel(prompt_path, workspace),
        "context_path": _rel(ctx_path, workspace),
        "reply_path": _rel(reply_path, workspace),
    })
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    codenook = workspace / ".codenook"
    task_dir = codenook / "tasks" / args.task_id
    draft_path = task_dir / "draft-config.yaml"
    state_path = task_dir / "state.json"

    if not task_dir.is_dir():
        _emit({
            "action": "error",
            "task_id": args.task_id,
            "code": "task_missing",
            "errors": [f"task directory not found: {task_dir}"],
        })
        return 4

    user_turn = _read_user_turn(args)
    if user_turn.strip() and (task_dir / "router-context.md").exists():
        rc.append_turn(task_dir, "user", user_turn)

    if not draft_path.exists() or draft_path.stat().st_size == 0:
        _emit({
            "action": "error",
            "task_id": args.task_id,
            "code": "draft_missing",
            "errors": ["draft-config.yaml is missing or empty"],
        })
        return 4

    try:
        draft = dc.read_draft(draft_path)
    except Exception as e:
        _emit({
            "action": "error",
            "task_id": args.task_id,
            "code": "draft_invalid",
            "errors": [f"{type(e).__name__}: {e}"],
        })
        return 4

    plugin = draft.get("plugin")
    if not plugin and isinstance(draft.get("selected_plugins"), list) \
            and draft["selected_plugins"]:
        plugin = draft["selected_plugins"][0]
    if not plugin:
        _emit({
            "action": "error",
            "task_id": args.task_id,
            "code": "draft_invalid",
            "errors": ["plugin (or selected_plugins) is required"],
        })
        return 4

    try:
        state = dc.freeze_to_state_json(
            draft, plugin=plugin, task_id=args.task_id
        )
    except Exception as e:
        _emit({
            "action": "error",
            "task_id": args.task_id,
            "code": "draft_invalid",
            "errors": [f"{type(e).__name__}: {e}"],
        })
        return 4

    state["status"] = "pending"
    state.setdefault("config_overrides", {})

    # Two-phase write (M10.3 MEDIUM-03): persist the seeded state with
    # status=pending FIRST so that if set_parent below raises, the
    # state.json on disk reflects the un-committed status. cmd_confirm
    # only flips status=in_progress after parent attachment succeeds
    # (or is no-op).
    atomic_write_json(str(state_path), state)

    # M10.3 — apply user-confirmed parent_id (if any) AFTER the state
    # seed exists. Cycle / not-found / already-attached are surfaced as
    # exit 4 so the caller can re-prompt the user. set_parent emits the
    # chain_attached / chain_attach_failed audit itself.
    parent_id = draft.get("parent_id")
    if isinstance(parent_id, str) and parent_id:
        # v0.11 MINOR-06 — confirm-side stale-parent check. Suggestions
        # are computed at cmd_prepare time; if the candidate transitioned
        # to done/cancelled between prepare and confirm, emit a
        # `chain_parent_stale` diagnostic before attempting attach.
        # Behaviour stays permissive (no exit 4) to match existing
        # "stale suggestion" semantics elsewhere in the router.
        try:
            _maybe_audit_stale_parent(workspace, args.task_id, parent_id)
        except Exception:
            pass
        try:
            tc.set_parent(workspace, args.task_id, parent_id)
        except (
            tc.AlreadyAttachedError,
            tc.CycleError,
            tc.CorruptChainError,
            tc.TaskNotFoundError,
            ValueError,
        ) as e:
            _emit({
                "action": "error",
                "task_id": args.task_id,
                "code": "parent_attach_failed",
                "errors": [f"{type(e).__name__}: {e}"],
            })
            return 4

    # Phase 2 of MEDIUM-03: now that parent attachment (if any) has
    # succeeded, re-load + flip to in_progress. Reading the file back
    # picks up parent_id/chain_root that set_parent wrote.
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        pass  # leave the in-memory state and proceed
    state["status"] = "in_progress"
    atomic_write_json(str(state_path), state)

    if (task_dir / "router-context.md").exists():
        rc.update_frontmatter(
            task_dir, state="confirmed", last_router_action="handoff"
        )

    tick_sh = _HERE.parent / "orchestrator-tick" / "tick.sh"
    tick_status = "unknown"
    tick_stderr = ""
    if tick_sh.is_file():
        try:
            proc = subprocess.run(
                [
                    "bash", str(tick_sh),
                    "--task", args.task_id,
                    "--workspace", str(workspace),
                    "--json",
                ],
                capture_output=True, text=True, timeout=60,
            )
            tick_stderr = proc.stderr
            try:
                tick_json = json.loads(proc.stdout.strip().splitlines()[-1])
                tick_status = tick_json.get("status", "unknown")
            except Exception:
                tick_status = (
                    "ok" if proc.returncode == 0 else f"rc={proc.returncode}"
                )
        except Exception as e:
            tick_status = f"error: {type(e).__name__}: {e}"
    else:
        tick_status = "tick_missing"

    out: dict = {
        "action": "handoff",
        "task_id": args.task_id,
        "first_tick_status": tick_status,
    }
    if tick_stderr:
        out["tick_stderr"] = tick_stderr.strip().splitlines()[-1][:200]
    _emit(out)
    return 0


# ---------------------------------------------------------------- main


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="router-agent", add_help=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--user-turn", default=None)
    p.add_argument("--user-turn-file", default=None)
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--lock-timeout", type=float, default=30.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not args.task_id.startswith("T-"):
        _emit({
            "action": "error",
            "task_id": args.task_id,
            "code": "bad_task_id",
            "errors": ["task id must match T-NNN"],
        })
        return 2

    workspace = Path(args.workspace)
    if not workspace.is_dir():
        _emit({
            "action": "error",
            "task_id": args.task_id,
            "code": "bad_workspace",
            "errors": [f"workspace not found: {workspace}"],
        })
        return 2

    task_dir = workspace.resolve() / ".codenook" / "tasks" / args.task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tl.acquire(task_dir, timeout=args.lock_timeout):
            if args.confirm:
                return cmd_confirm(args)
            return cmd_prepare(args)
    except tl.LockTimeout as e:
        _emit({
            "action": "busy",
            "task_id": args.task_id,
            "message": str(e),
        })
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
