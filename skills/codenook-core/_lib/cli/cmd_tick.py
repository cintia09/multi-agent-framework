"""``codenook tick`` — runs orchestrator-tick/_tick.py and post-augments
the JSON envelope with ``prompt_path`` / ``reply_path`` when a phase
agent dispatch is in flight (parity with the bash wrapper)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from . import _subproc
from .config import CodenookContext, is_safe_task_component, resolve_task_id
from .. import models
from .. import exec_mode as _exec_mode


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    task = ""
    json_flag = False
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--json":
                json_flag = True
            else:
                sys.stderr.write(f"codenook tick: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook tick: missing value for last flag\n")
        return 2

    if not task:
        sys.stderr.write("codenook tick: --task required\n")
        return 2

    if not is_safe_task_component(task):
        sys.stderr.write(
            f"codenook tick: invalid --task {task!r} "
            "(must be a single safe path component)\n")
        return 2

    resolved, candidates = resolve_task_id(ctx.workspace, task)
    if resolved is None:
        if candidates:
            sys.stderr.write(
                f"codenook tick: ambiguous --task {task}; candidates: "
                f"{', '.join(candidates)}\n")
        else:
            sys.stderr.write(
                f"codenook tick: state.json not found for task {task}\n")
        return 2
    task = resolved

    state_file = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
    if not state_file.is_file():
        sys.stderr.write(f"codenook tick: state.json not found for task {task}\n")
        return 2

    helper = ctx.kernel_dir / "orchestrator-tick" / "_tick.py"
    if not helper.is_file():
        sys.stderr.write(f"codenook tick: helper missing: {helper}\n")
        return 1

    extra = {
        "CN_TASK": task,
        "CN_STATE_FILE": str(state_file),
        "CN_WORKSPACE": str(ctx.workspace),
        "CN_DRY_RUN": "0",
        "CN_JSON": "1" if json_flag else "0",
    }
    cp = subprocess.run(
        [sys.executable, str(helper)],
        env=_subproc.kernel_env(ctx, extra),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    sys.stderr.write(cp.stderr)
    tick_out = cp.stdout

    if not json_flag or cp.returncode != 0:
        sys.stdout.write(tick_out)
        if not tick_out.endswith("\n"):
            sys.stdout.write("\n")
        return cp.returncode

    augmented = _augment_envelope(ctx, task, tick_out)
    sys.stdout.write(augmented)
    if not augmented.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def _augment_envelope(ctx: CodenookContext, task: str, tick_out: str) -> str:
    """Replicate the bash wrapper's envelope-augmentation pass."""
    text = tick_out.strip()
    if not text:
        return tick_out

    try:
        summary = json.loads(text)
    except Exception:
        return tick_out

    state_p = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
    if not state_p.is_file():
        return tick_out
    try:
        state = json.loads(state_p.read_text(encoding="utf-8"))
    except Exception:
        # Corrupt state.json — degrade gracefully and emit the raw
        # tick output so the operator can still see what happened.
        return tick_out
    if not isinstance(state, dict):
        return tick_out
    ifa = state.get("in_flight_agent") or {}
    plugin = state.get("plugin") or ""
    phase = state.get("phase") or ""
    role = ifa.get("role") or ""
    expected = ifa.get("expected_output") or ""
    if not (plugin and phase and role and expected):
        return tick_out

    phase_idx = None
    template = None
    prompt_basename = None

    if expected:
        # Canonical source: derive from the expected_output (i.e. the
        # phase's `produces:` artifact). Works for both v0.1 list and
        # v0.2 map phases.yaml layouts.
        produced_basename = Path(expected).name
        if produced_basename:
            prompt_basename = produced_basename
            m = re.match(r"^phase-(\d+)-", produced_basename)
            if m:
                phase_idx = int(m.group(1))

    if phase_idx is None:
        # Fallback: parse phases.yaml — handle both list and map layout.
        phases_yaml = ctx.workspace / ".codenook" / "plugins" / plugin / "phases.yaml"
        if phases_yaml.is_file():
            try:
                import yaml as _yaml  # type: ignore[import-untyped]
                doc = _yaml.safe_load(phases_yaml.read_text(encoding="utf-8")) or {}
                phases_raw = doc.get("phases", [])
                if isinstance(phases_raw, dict):
                    seq = list(phases_raw.keys())
                else:
                    seq = [
                        p.get("id") for p in phases_raw
                        if isinstance(p, dict) and p.get("id")
                    ]
                if phase in seq:
                    phase_idx = seq.index(phase) + 1
            except Exception:
                pass
    if phase_idx is None:
        m = re.match(r"^(\d+)", str(phase))
        phase_idx = int(m.group(1)) if m else 1

    if prompt_basename is None:
        prompt_basename = f"phase-{phase_idx}-{role}.md"

    mt_dir = ctx.workspace / ".codenook" / "plugins" / plugin / "manifest-templates"
    candidates = [
        mt_dir / prompt_basename,
        mt_dir / f"phase-{phase_idx}-{role}.md",
        mt_dir / f"phase-{phase}-{role}.md",
    ]
    template = next((p for p in candidates if p.is_file()), None)

    prompts_dir = ctx.workspace / ".codenook" / "tasks" / task / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompt_p = prompts_dir / prompt_basename

    if template is not None:
        body = template.read_text(encoding="utf-8")
        subs = {
            "task_id": task,
            "iteration": str(state.get("iteration", 0)),
            "target_dir": state.get("target_dir", "src/"),
            "prior_summary_path": "",
            "criteria_path": "",
        }
        for k, v in subs.items():
            body = body.replace("{" + k + "}", v)
        # M10+ slot (parity with orchestrator-tick._tick._render_phase_prompt)
        try:
            _lib = ctx.kernel_dir / "_lib"
            sys.path.insert(0, str(_lib))
            import memory_layer as _ml  # type: ignore[import-not-found]
            task_ctx = _ml.build_task_context(ctx.workspace, task)
        except Exception:
            task_ctx = ""
        body = body.replace("{{TASK_CONTEXT}}", task_ctx)
        # v0.22.0 — auto-inject {{KNOWLEDGE_HITS}} via find_relevant.
        try:
            _lib = ctx.kernel_dir / "_lib"
            sys.path.insert(0, str(_lib))
            import knowledge_query as _kq  # type: ignore[import-not-found]
            query_parts: list[str] = []
            ti = state.get("task_input")
            if isinstance(ti, str) and ti.strip():
                query_parts.append(ti.strip())
            # state["keywords"] is intentionally not consulted: nothing
            # writes it and the schema bans extra props.
            query = " ".join(query_parts)
            top_n = _kq.resolve_top_n(ctx.workspace, default=8)
            body = _kq.substitute_placeholder(
                body,
                ctx.workspace,
                query=query,
                role=role,
                phase_id=str(phase),
                plugin=plugin,
                top_n=top_n,
            )
            # v0.28.3 — single-brace {KNOWLEDGE_HITS} (top-5, empty on
            # zero hits). Used by new phase templates; co-exists with
            # the legacy double-brace substitution above.
            body = _kq.substitute_single_placeholder(
                body,
                ctx.workspace,
                query=query,
                role=role,
                phase_id=str(phase),
                plugin=plugin,
            )
        except Exception:
            # Backward-compat: never fail dispatch on retrieval errors.
            # Leave any unsubstituted placeholder literal so a later run
            # (post-fix) can still inject hits.
            pass
        prompt_p.write_text(body, encoding="utf-8")
    elif not prompt_p.is_file():
        prompt_p.write_text(
            f"# {role} dispatch (no manifest template found)\n\n"
            f"Task: {task}\nPhase: {phase}\nRole: {role}\n"
            f"Read `.codenook/plugins/{plugin}/roles/{role}.md` for your operating contract.\n"
            f"Write your output to `{expected}` per that contract.\n",
            encoding="utf-8",
        )

    reply_rel = (
        expected if expected.startswith(".codenook")
        else f".codenook/tasks/{task}/{expected}"
    )
    prompt_rel = f".codenook/tasks/{task}/prompts/{prompt_p.name}"
    # T-004 unified layout: roles/<role>/role.md preferred; flat legacy fallback.
    _role_subdir = ctx.workspace / ".codenook" / "plugins" / plugin / "roles" / role / "role.md"
    if _role_subdir.is_file():
        system_rel = f".codenook/plugins/{plugin}/roles/{role}/role.md"
    else:
        system_rel = f".codenook/plugins/{plugin}/roles/{role}.md"

    # v0.19 — per-task execution_mode picks the dispatch action.
    # Tasks without the field behave exactly as v0.18.x (sub-agent).
    mode = _exec_mode.resolve_exec_mode(state)
    if mode == "inline":
        action = "inline_dispatch"
    else:
        action = "phase_prompt"

    envelope = {
        "action": action,
        "task_id": task,
        "plugin": plugin,
        "phase": phase,
        "role": role,
        "system_prompt_path": system_rel,
        "prompt_path": prompt_rel,
        "reply_path": reply_rel,
    }
    if mode == "inline":
        # Inline-mode envelopes carry an explicit role_path / output_path
        # pair so the conductor has every path it needs to do the work
        # without re-querying the kernel. system_prompt_path / reply_path
        # remain for backward parity with sub-agent envelopes.
        envelope["execution_mode"] = "inline"
        envelope["role_path"] = system_rel
        envelope["output_path"] = reply_rel
    # v0.18 — resolve model via C/B/A/D chain; omit key entirely when None
    # so the conductor falls back to its platform default (backward compat).
    # In inline mode the field is informational only — the conductor cannot
    # swap models mid-conversation — but we still surface it for symmetry
    # and for future extensions that may dispatch across processes.
    resolved = models.resolve_model(ctx.workspace, plugin, phase, state)
    if resolved:
        envelope["model"] = resolved
    # v0.20 — surface seed task_input (set via `task new --input` /
    # --input-file) so phase agents and the inline conductor can use it
    # as additional context without a separate clarify round. Omit the
    # key entirely when empty for byte-for-byte parity with v0.19.
    seeded_input = state.get("task_input")
    if seeded_input:
        envelope["task_input"] = seeded_input
    summary["envelope"] = envelope
    return json.dumps(summary, ensure_ascii=False)
