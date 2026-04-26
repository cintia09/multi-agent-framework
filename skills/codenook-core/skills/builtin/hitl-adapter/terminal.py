#!/usr/bin/env python3
"""hitl-adapter/terminal.py — Python entry equivalent to ``terminal.sh``.

v0.24.0 — preferred on Windows hosts without bash on PATH. The .sh
wrapper is retained for Linux/Mac users; it now delegates to this script.

Subcommands::

    list   [--json]
    decide --id ID --decision approve|reject|needs_changes
           --reviewer NAME [--comment TEXT]
    show   --id ID [--raw]
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
    ap = argparse.ArgumentParser(prog="terminal", add_help=True)
    ap.add_argument("subcommand", choices=("list", "decide", "show"))
    ap.add_argument("--id", default="")
    ap.add_argument("--decision", default="")
    ap.add_argument("--reviewer", default="")
    ap.add_argument("--comment", default="")
    ap.add_argument("--workspace")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--raw", action="store_true")
    args = ap.parse_args(argv)

    ws_arg = args.workspace or os.environ.get("CODENOOK_WORKSPACE")
    workspace = Path(ws_arg) if ws_arg else _find_workspace(Path.cwd())
    if not workspace or not workspace.is_dir():
        print("terminal.py: workspace not found (set --workspace or "
              "CODENOOK_WORKSPACE)", file=sys.stderr)
        return 2

    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["CN_SUBCMD"] = args.subcommand
    os.environ["CN_ID"] = args.id
    os.environ["CN_DECISION"] = args.decision
    os.environ["CN_REVIEWER"] = args.reviewer
    os.environ["CN_COMMENT"] = args.comment
    os.environ["CN_WORKSPACE"] = str(workspace)
    os.environ["CN_JSON"] = "1" if args.json else "0"
    os.environ["CN_RAW"] = "1" if args.raw else "0"

    helper = HERE / "_hitl.py"
    sys.argv = [str(helper)]
    try:
        runpy.run_path(str(helper), run_name="__main__")
    except SystemExit as e:
        code = e.code
        return int(code) if isinstance(code, int) else (0 if code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
