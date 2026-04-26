#!/usr/bin/env python3
"""orchestrator-tick/tick.py — Python entry equivalent to ``tick.sh``.

v0.24.0 — preferred on Windows hosts without bash on PATH. The .sh
wrapper is retained for Linux/Mac users who script against it and now
delegates to this script.

Usage::

    python tick.py --task T-NNN [--workspace WS] [--dry-run] [--json]
"""
from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _find_workspace(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / ".codenook").is_dir():
            return p
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tick", add_help=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--workspace")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ws_arg = args.workspace or os.environ.get("CODENOOK_WORKSPACE")
    workspace = Path(ws_arg) if ws_arg else _find_workspace(Path.cwd())
    if not workspace or not workspace.is_dir():
        print("tick.py: could not locate workspace (set --workspace or "
              "CODENOOK_WORKSPACE)", file=sys.stderr)
        return 2

    task_dir = workspace / ".codenook" / "tasks" / args.task
    if not task_dir.is_dir():
        print(f"tick.py: task not found: {args.task}", file=sys.stderr)
        return 2
    state_file = task_dir / "state.json"
    if not state_file.is_file():
        print(f"tick.py: state.json not found for task {args.task}",
              file=sys.stderr)
        return 2

    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["CN_TASK"] = args.task
    os.environ["CN_STATE_FILE"] = str(state_file)
    os.environ["CN_WORKSPACE"] = str(workspace)
    os.environ["CN_DRY_RUN"] = "1" if args.dry_run else "0"
    os.environ["CN_JSON"] = "1" if args.json else "0"
    os.environ.setdefault("CN_DISPATCH_CMD",
                          os.environ.get("CODENOOK_DISPATCH_CMD", ""))

    helper = HERE / "_tick.py"
    sys.argv = [str(helper)]
    try:
        runpy.run_path(str(helper), run_name="__main__")
    except SystemExit as e:
        code = e.code
        return int(code) if isinstance(code, int) else (0 if code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
