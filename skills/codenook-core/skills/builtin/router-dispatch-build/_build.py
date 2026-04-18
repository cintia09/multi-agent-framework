#!/usr/bin/env python3
"""router-dispatch-build core. Invoked by build.sh.

Assembles a ≤500-char JSON envelope, truncates user_input to 200 chars
with an ellipsis if needed, then calls dispatch-audit emit.

Builtin-skill targets are recognised by the *absence* of a plugin
manifest at .codenook/plugins/<target>/plugin.yaml — and identified
positively by the existence of a sibling skills/builtin/<target>/
SKILL.md (or the in-package M3 hardcoded list for the small set we
ship at this milestone).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from manifest_load import load_manifest, ManifestError, plugins_dir  # noqa: E402

PAYLOAD_LIMIT  = 500
INPUT_HARD_CAP = 200
ELLIPSIS       = "..."

# Hardcoded builtin-skill names recognised by the M3 router. Future
# milestones can replace this with a directory scan of skills/builtin/.
BUILTIN_SKILLS = {"list-plugins", "show-config", "help"}


def truncate_input(s: str) -> str:
    if len(s) <= INPUT_HARD_CAP:
        return s
    return s[:INPUT_HARD_CAP] + ELLIPSIS


def envelope_size(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8"))


def main() -> int:
    target     = os.environ["CN_TARGET"]
    user_input = os.environ["CN_USER_INPUT"]
    task       = os.environ.get("CN_TASK", "")
    ws         = Path(os.environ["CN_WORKSPACE"]).resolve()
    emit_sh    = os.environ["CN_EMIT_SH"]

    # Reject path-traversal in --target before any filesystem access.
    if (not target
            or "/" in target
            or "\\" in target
            or ".." in target
            or target != Path(target).name):
        print(f"build.sh: invalid target name: {target!r}", file=sys.stderr)
        return 1

    plugin_manifest_path = plugins_dir(ws) / target / "plugin.yaml"
    is_plugin = plugin_manifest_path.is_file()

    if is_plugin:
        try:
            load_manifest(ws, target)
        except ManifestError as e:
            print(f"build.sh: target manifest invalid: {e}", file=sys.stderr)
            return 1
        role = "plugin-worker"
    else:
        if target not in BUILTIN_SKILLS:
            print(f"build.sh: target not found (no plugin manifest, "
                  f"not a known builtin): {target}", file=sys.stderr)
            return 1
        role = "builtin-skill"

    # Build context.plugins — list installed plugin ids only (compact).
    pdir = plugins_dir(ws)
    installed_ids = sorted(p.name for p in pdir.iterdir()
                           if p.is_dir() and (p / "plugin.yaml").is_file()) \
                    if pdir.is_dir() else []

    payload = {
        "role":       role,
        "target":     target,
        "user_input": truncate_input(user_input),
        "context":    {"plugins": installed_ids},
    }
    if task:
        payload["task"] = task

    size = envelope_size(payload)
    if size > PAYLOAD_LIMIT:
        # Try shrinking context.plugins (drop ids one-by-one from the end).
        while installed_ids and size > PAYLOAD_LIMIT:
            installed_ids.pop()
            payload["context"]["plugins"] = installed_ids
            size = envelope_size(payload)
    if size > PAYLOAD_LIMIT:
        print(f"build.sh: payload still too large ({size} > {PAYLOAD_LIMIT})",
              file=sys.stderr)
        return 1

    out = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    # Audit — must succeed; surface as exit 1 if it doesn't.
    try:
        res = subprocess.run(
            [emit_sh, "--role", role, "--payload", out, "--workspace", str(ws)],
            capture_output=True, text=True, check=False,
        )
        if res.returncode != 0:
            sys.stderr.write(res.stderr)
            print(f"build.sh: dispatch-audit emit failed (rc={res.returncode})",
                  file=sys.stderr)
            return 1
    except OSError as e:
        print(f"build.sh: cannot exec dispatch-audit: {e}", file=sys.stderr)
        return 1

    sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
