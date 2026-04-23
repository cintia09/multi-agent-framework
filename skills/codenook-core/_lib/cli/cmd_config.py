"""``codenook config show`` — explain the 4-layer model resolution chain.

Resolves which model a given (task, phase) pair would use, showing
*every* layer's contribution, not just the winner. Useful when:

  * a task picked an unexpected model and you want to know which YAML
    file to edit;
  * you're auditing a workspace before promoting a plugin.

Order (highest priority first):
  C  task state.json :: model_override        ← codenook task set-model
  B  plugins/<id>/phases.yaml :: phases.<phase>.model
  A  plugins/<id>/plugin.yaml :: default_model
  D  .codenook/config.yaml :: default_model   ← the workspace fallback

(D is *lowest* priority despite living at the workspace level — it's the
"last resort" default, not an override.)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

from .config import CodenookContext, resolve_task_id


HELP = """\
Usage: codenook config show --task <T-NNN> [--phase <id>] [--json]

Show every layer's contribution to the model resolution chain for
*<task, phase>*. When --phase is omitted, uses the task's current
state.phase. JSON output via --json.

Options:
  --task <T-NNN>   required. Bare or slugged task id.
  --phase <id>     override which phase to inspect (default:
                   state.phase from the task's state.json).
  --json           emit a machine-readable JSON object on stdout.
"""


def _safe_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception:
        return {}
    if not path.is_file():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _phase_model(phases_doc: dict, phase_id: str) -> str | None:
    raw = phases_doc.get("phases")
    if isinstance(raw, dict):
        entry = raw.get(phase_id)
        if isinstance(entry, dict):
            v = entry.get("model")
            if isinstance(v, str) and v:
                return v
    elif isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict) and entry.get("id") == phase_id:
                v = entry.get("model")
                if isinstance(v, str) and v:
                    return v
    return None


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        print(HELP)
        return 0
    sub, rest = args[0], list(args[1:])
    if sub != "show":
        sys.stderr.write(f"codenook config: unknown subcommand: {sub}\n")
        sys.stderr.write(HELP)
        return 2

    task = ""
    phase_override = ""
    as_json = False
    it = iter(rest)
    try:
        for a in it:
            if a in ("-h", "--help"):
                print(HELP)
                return 0
            if a == "--task":
                task = next(it)
            elif a == "--phase":
                phase_override = next(it)
            elif a == "--json":
                as_json = True
            else:
                sys.stderr.write(f"codenook config show: unknown arg: {a}\n")
                sys.stderr.write(HELP)
                return 2
    except StopIteration:
        sys.stderr.write("codenook config show: missing value for last flag\n")
        return 2

    if not task:
        sys.stderr.write("codenook config show: --task required\n")
        return 2

    resolved, candidates = resolve_task_id(ctx.workspace, task)
    if resolved is None:
        if candidates:
            sys.stderr.write(
                f"codenook config show: ambiguous --task {task}; "
                f"candidates: {', '.join(candidates)}\n")
        else:
            sys.stderr.write(
                f"codenook config show: no such task: {task}\n")
        return 1

    sf = ctx.workspace / ".codenook" / "tasks" / resolved / "state.json"
    try:
        state = json.loads(sf.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(
            f"codenook config show: cannot read state.json: {exc}\n")
        return 1

    plugin = state.get("plugin") or ""
    phase = phase_override or state.get("phase") or ""

    plugin_dir = ctx.workspace / ".codenook" / "plugins" / plugin
    plugin_doc = _safe_yaml(plugin_dir / "plugin.yaml") if plugin else {}
    phases_doc = _safe_yaml(plugin_dir / "phases.yaml") if plugin else {}
    ws_doc = _safe_yaml(ctx.workspace / ".codenook" / "config.yaml")

    layers = []

    # C — task override (highest priority)
    c_val = state.get("model_override") if isinstance(state, dict) else None
    layers.append({
        "id": "C",
        "name": "task model_override",
        "source": f".codenook/tasks/{resolved}/state.json :: model_override",
        "value": c_val if isinstance(c_val, str) and c_val else None,
    })

    # B — phase default
    b_val = _phase_model(phases_doc, phase) if (plugin and phase) else None
    layers.append({
        "id": "B",
        "name": "phase model",
        "source": (
            f".codenook/plugins/{plugin}/phases.yaml :: phases.{phase}.model"
            if plugin and phase else
            "(skipped — no plugin or phase)"
        ),
        "value": b_val,
    })

    # A — plugin default
    a_val = plugin_doc.get("default_model") if plugin else None
    layers.append({
        "id": "A",
        "name": "plugin default_model",
        "source": (
            f".codenook/plugins/{plugin}/plugin.yaml :: default_model"
            if plugin else "(skipped — no plugin)"
        ),
        "value": a_val if isinstance(a_val, str) and a_val else None,
    })

    # D — workspace fallback (lowest priority)
    d_val = ws_doc.get("default_model")
    layers.append({
        "id": "D",
        "name": "workspace default_model",
        "source": ".codenook/config.yaml :: default_model",
        "value": d_val if isinstance(d_val, str) and d_val else None,
    })

    # The kernel's resolve_model() walks C → B → A → D and returns the
    # first non-empty hit. We mirror that here without re-importing it
    # so a corrupt models module doesn't take this debug command down.
    effective = None
    winner_id = None
    for layer in layers:
        if layer["value"]:
            effective = layer["value"]
            winner_id = layer["id"]
            break

    payload = {
        "task_id": resolved,
        "plugin": plugin,
        "phase": phase,
        "phase_source": "override" if phase_override else "state.phase",
        "layers": layers,
        "winner": winner_id,
        "effective": effective,
    }

    if as_json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
        return 0

    print(f"Task   : {resolved}")
    print(f"Plugin : {plugin or '(none)'}")
    print(f"Phase  : {phase or '(none)'}"
          f"{' [override]' if phase_override else ''}")
    print("")
    print("Resolution chain (first non-empty wins):")
    for layer in layers:
        marker = "  ✓" if layer["id"] == winner_id else "   "
        v = layer["value"] if layer["value"] is not None else "(unset)"
        print(f"{marker} {layer['id']}  {layer['name']:<24}  {v}")
        print(f"        {layer['source']}")
    print("")
    print(f"Effective model: {effective or '(none — host default)'}")
    return 0
