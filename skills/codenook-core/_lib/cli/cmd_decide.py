"""``codenook decide`` — resolve the pending HITL gate for a (task, phase)."""
from __future__ import annotations

import getpass
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import yaml  # type: ignore[import-untyped]

from . import _subproc
from .config import CodenookContext, is_safe_task_component, resolve_task_id


VALID_DECISIONS = ("approve", "reject", "needs_changes")


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    task = phase = decision = comment = ""
    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--phase":
                phase = next(it)
            elif a == "--decision":
                decision = next(it)
            elif a == "--comment":
                comment = next(it)
            else:
                sys.stderr.write(f"codenook decide: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook decide: missing value for last flag\n")
        return 2

    if not (task and phase and decision):
        sys.stderr.write(
            "codenook decide: --task, --phase, --decision required\n")
        return 2

    if decision not in VALID_DECISIONS:
        sys.stderr.write(
            f"codenook decide: invalid --decision '{decision}' "
            f"(allowed: {', '.join(VALID_DECISIONS)})\n")
        return 2

    if not is_safe_task_component(task):
        sys.stderr.write(
            f"codenook decide: invalid --task {task!r} "
            "(must be a single safe path component)\n")
        return 2

    resolved, candidates = resolve_task_id(ctx.workspace, task)
    if resolved is None:
        if candidates:
            sys.stderr.write(
                f"codenook decide: ambiguous --task {task}; candidates: "
                f"{', '.join(candidates)}\n")
        else:
            sys.stderr.write(f"codenook decide: no such task: {task}\n")
        return 1
    task = resolved
    state_p = ctx.workspace / ".codenook" / "tasks" / task / "state.json"
    if not state_p.is_file():
        sys.stderr.write(f"codenook decide: no such task: {task}\n")
        return 1
    try:
        plugin = json.loads(state_p.read_text(encoding="utf-8")).get(
            "plugin") or ""
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(
            f"codenook decide: corrupt state.json for task {task}: {exc}\n")
        return 1

    gate = phase
    phases_yaml = ctx.workspace / ".codenook" / "plugins" / plugin / "phases.yaml"
    if phases_yaml.is_file():
        try:
            phases_doc = (
                yaml.safe_load(phases_yaml.read_text(encoding="utf-8")) or {}
            )
            phases_raw = phases_doc.get("phases", []) or []
            if isinstance(phases_raw, dict):
                # v0.2.0+ catalogue (map keyed by phase id)
                spec = phases_raw.get(phase) or {}
                if isinstance(spec, dict):
                    gate = spec.get("gate") or phase
            elif isinstance(phases_raw, list):
                # v0.1 flat list
                for p in phases_raw:
                    if isinstance(p, dict) and p.get("id") == phase:
                        gate = p.get("gate") or phase
                        break
        except Exception:
            pass

    qdir = ctx.workspace / ".codenook" / "hitl-queue"
    entry_id = ""
    pending_gates: list[str] = []
    if qdir.is_dir():
        # First pass: try the resolved gate (phase-id mapping).
        for p in sorted(qdir.glob("*.json")):
            try:
                e = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if e.get("task_id") != task or e.get("decision"):
                continue
            g = e.get("gate") or ""
            if g and g not in pending_gates:
                pending_gates.append(g)
            if g == gate:
                entry_id = e.get("id") or ""
                break
        # Second pass: allow --phase to be the gate-id directly when the
        # phase-id lookup did not match (e.g. the conductor passed
        # ``--phase requirements_signoff`` instead of ``--phase clarify``).
        if not entry_id and phase != gate:
            for p in sorted(qdir.glob("*.json")):
                try:
                    e = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if (e.get("task_id") == task
                        and e.get("gate") == phase
                        and not e.get("decision")):
                    entry_id = e.get("id") or ""
                    gate = phase
                    break

    if not entry_id:
        if pending_gates:
            hint = f" (pending gates: {', '.join(pending_gates)})"
        else:
            hint = (" (no gate has been registered for this task yet — "
                    "run `codenook tick --task {task} --json` first; the "
                    "tick is what writes the gate JSON to "
                    ".codenook/hitl-queue/)").format(task=task)
        sys.stderr.write(
            f"codenook decide: no pending HITL entry for task={task} "
            f"phase={phase} (gate={gate}){hint}\n")
        return 1

    helper = ctx.kernel_dir / "hitl-adapter" / "_hitl.py"
    reviewer = os.environ.get("USER") or getpass.getuser() or "cli"
    extra = {
        "CN_SUBCMD": "decide",
        "CN_ID": entry_id,
        "CN_DECISION": decision,
        "CN_REVIEWER": reviewer,
        "CN_COMMENT": comment,
        "CN_WORKSPACE": str(ctx.workspace),
        "CN_JSON": "0",
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
    if cp.returncode != 0:
        return cp.returncode
    print(json.dumps({
        "id": entry_id, "task": task, "phase": phase,
        "gate": gate, "decision": decision,
    }), flush=True)
    return 0
