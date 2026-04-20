#!/usr/bin/env python3
"""preflight/_preflight.py — sanity check logic"""
import json
import os
import sys


def _discover_known_phases(workspace: str, state: dict) -> list[str]:
    """Return phase ids declared by the task's active plugin.

    Resolution order:
      1. ``state["plugin"]`` (modern field used by orchestrator-tick).
      2. The single entry in ``.codenook/state.json::installed_plugins``
         when there is exactly one — this matches the common single-plugin
         workspace.

    Reads ``.codenook/plugins/<id>/phases.yaml`` and extracts the ``id``
    of every entry under ``phases:``. Returns an empty list when nothing
    can be resolved (callers fall back to the legacy whitelist).
    """
    plugin_id = state.get("plugin") or ""
    if not plugin_id:
        try:
            ws_state_p = os.path.join(workspace, ".codenook", "state.json")
            with open(ws_state_p, "r", encoding="utf-8") as f:
                ws_state = json.load(f)
            installed = ws_state.get("installed_plugins", []) or []
            if len(installed) == 1 and isinstance(installed[0], dict):
                plugin_id = installed[0].get("id", "")
        except Exception:
            return []
    if not plugin_id:
        return []
    phases_yaml = os.path.join(
        workspace, ".codenook", "plugins", plugin_id, "phases.yaml"
    )
    if not os.path.isfile(phases_yaml):
        return []
    try:
        try:
            import yaml  # type: ignore
            with open(phases_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            phases = data.get("phases", []) or []
            if isinstance(phases, dict):
                # v0.2.0+ catalogue (map keyed by phase id)
                return [pid for pid in phases.keys() if isinstance(pid, str)]
            return [p["id"] for p in phases if isinstance(p, dict) and p.get("id")]
        except ImportError:
            # Minimal fallback parser: collect lines `  - id: <name>` (list)
            # and top-level `<id>:` keys (map).
            ids: list[str] = []
            with open(phases_yaml, "r", encoding="utf-8") as f:
                in_phases = False
                for line in f:
                    rstripped = line.rstrip("\n")
                    if rstripped.startswith("phases:"):
                        in_phases = True
                        continue
                    if in_phases:
                        if rstripped and not rstripped.startswith((" ", "\t", "#")):
                            in_phases = False
                            continue
                        s = rstripped.strip()
                        if s.startswith("- id:"):
                            ids.append(s.split(":", 1)[1].strip().strip('"\''))
                        elif (rstripped.startswith("  ")
                              and not rstripped.startswith("    ")
                              and ":" in s
                              and not s.startswith("-")):
                            key = s.split(":", 1)[0].strip()
                            if key and not any(c in key for c in " \t#"):
                                ids.append(key)
            return ids
    except Exception:
        return []


def main():
    task = os.environ["CN_TASK"]
    state_file = os.environ["CN_STATE_FILE"]
    workspace = os.environ["CN_WORKSPACE"]
    json_out = os.environ.get("CN_JSON", "0") == "1"
    
    reasons = []
    
    # Load state
    try:
        with open(state_file, 'r') as f:
            state = json.load(f)
    except Exception as e:
        reasons.append(f"invalid state.json: {e}")
        emit_result(task, None, reasons, json_out, exit_code=1)
        return
    
    phase = state.get("phase", "")
    total_iterations = state.get("total_iterations", 0)
    dual_mode = state.get("dual_mode")
    config_overrides = state.get("config_overrides", {})
    
    # Check 1: dual_mode required when task hasn't been told yet.
    # The intent (per design): tasks created without answering dual_mode
    # get blocked on first tick (iteration <= 1 / total_iterations <= 1)
    # so the question is asked before any work happens.
    if dual_mode is None and total_iterations <= 1:
        reasons.append("needs dual_mode")
    
    # Check 2: known phase
    # DR-008 (v0.11.2): the legacy preflight had a hard-coded
    # KNOWN_PHASES list that diverged from every shipped plugin's
    # phases.yaml. Now we read the active plugin's phase ids from
    # state["plugin"] (or state["installed_plugin"]); if that yields a
    # non-empty list we use it, otherwise we fall back to a generic
    # superset that includes both the historic legacy phases and the
    # development-plugin phases so existing callers remain green.
    LEGACY_FALLBACK_PHASES = [
        "start", "implement", "test", "review", "distill", "accept", "done",
        # Development plugin (covered explicitly so that plugin-less
        # callers running against a development-plugin task do not
        # see bogus unknown_phase errors — see DR-008).
        "clarify", "design", "plan", "validate", "ship",
    ]
    KNOWN_PHASES = _discover_known_phases(workspace, state) or LEGACY_FALLBACK_PHASES
    if phase not in KNOWN_PHASES:
        reasons.append(f"unknown_phase: {phase}")
    
    # Check 3: blocking HITL queue entry
    hitl_queue = os.path.join(workspace, ".codenook/queues/hitl.jsonl")
    if os.path.exists(hitl_queue):
        with open(hitl_queue, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("task") == task and entry.get("status") == "pending":
                        reasons.append("HITL gate blocking")
                        break
                except:
                    pass
    
    # Check 4: config overrides validation (whitelist from #45)
    ALLOWED_OVERRIDE_KEYS = {
        "models.default", "models.router", "models.planner", "models.executor",
        "models.reviewer", "models.distiller", "hitl.mode",
    }

    def walk_paths(node, prefix=""):
        if isinstance(node, dict):
            for k, v in node.items():
                child_prefix = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict) and v:
                    yield from walk_paths(v, child_prefix)
                else:
                    yield child_prefix
        else:
            if prefix:
                yield prefix

    for path in walk_paths(config_overrides):
        if path not in ALLOWED_OVERRIDE_KEYS:
            reasons.append(f"invalid config override key: {path}")
    
    # Sort and dedupe reasons
    reasons = sorted(list(set(reasons)))
    
    ok = len(reasons) == 0
    exit_code = 0 if ok else 1
    
    emit_result(task, phase, reasons, json_out, exit_code)

def emit_result(task, phase, reasons, json_out, exit_code):
    if json_out:
        result = {
            "ok": exit_code == 0,
            "task": task,
            "phase": phase,
            "reasons": reasons
        }
        print(json.dumps(result, ensure_ascii=False))
    else:
        if reasons:
            for r in reasons:
                print(r, file=sys.stderr)
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
