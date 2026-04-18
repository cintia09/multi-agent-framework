#!/usr/bin/env python3
"""router/bootstrap.sh implementation.

Self-bootstrap order (per architecture §4 / decision #44):
  1. agents/router.md           — own profile
  2. core/shell.md              — main session contract
  3. .codenook/state.json       — installed plugins + active tasks
  4. .codenook/plugins/<id>/plugin.yaml for each id
  5. config-resolve --plugin __router__ → must yield tier_strong literal
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from manifest_load import load_all  # noqa: E402


def fail(msg: str, missing: list[str] | None = None) -> int:
    print(f"bootstrap.sh: {msg}", file=sys.stderr)
    if missing:
        for m in missing:
            print(f"  - missing: {m}", file=sys.stderr)
    return 1


def main() -> int:
    user_input = os.environ["CN_USER_INPUT"]
    ws         = Path(os.environ["CN_WORKSPACE"]).resolve()
    task       = os.environ.get("CN_TASK", "")
    core_root  = Path(os.environ["CN_CORE_ROOT"]).resolve()
    default_core = Path(os.environ["CN_DEFAULT_CORE"]).resolve()

    # 1 + 2 — required core files
    profile = core_root / "agents" / "router.md"
    shell   = core_root / "core"   / "shell.md"
    missing = []
    if not profile.is_file(): missing.append(str(profile))
    if not shell.is_file():   missing.append(str(shell))
    if missing:
        return fail("required core files not found", missing)

    # 3 — workspace state
    state_path = ws / ".codenook" / "state.json"
    if not state_path.is_file():
        return fail("workspace state.json not found", [str(state_path)])
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return fail(f"state.json invalid JSON: {e}")

    # 4 — installed plugin manifests
    manifests = []
    for m in load_all(ws):
        entry = {
            "id":              m.get("id"),
            "version":         m.get("version"),
            "intent_patterns": m.get("intent_patterns") or [],
        }
        if "_error" in m:
            entry["_error"] = m["_error"]
        manifests.append(entry)

    # 5 — model preference via config-resolve (sentinel __router__).
    # Use the *default* core root for the resolver script — overriding
    # CN_CORE_ROOT must not break the kernel's own skill lookups.
    resolver = default_core / "skills" / "builtin" / "config-resolve" / "resolve.sh"
    model = None
    if resolver.is_file():
        try:
            res = subprocess.run(
                [str(resolver),
                 "--plugin", "__router__",
                 "--workspace", str(ws),
                 "--catalog", str(state_path)],
                capture_output=True, text=True, check=False,
            )
            if res.returncode == 0:
                merged = json.loads(res.stdout)
                model = (merged.get("models") or {}).get("router") \
                     or (merged.get("models") or {}).get("default")
        except (OSError, json.JSONDecodeError):
            model = None

    active_tasks = state.get("active_tasks") or []

    out = {
        "role": "router",
        "context": {
            "active_tasks":      active_tasks,
            "active_task":       task or None,
            "installed_plugins": manifests,
            "model":             model,
        },
        "ready": True,
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
