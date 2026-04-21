#!/usr/bin/env python3
"""view-renderer/render.py — Windows-friendly CLI entry for view-renderer.

Usage:
    python render.py prepare --id <entry-id> [--workspace <dir>]

This is the primary entry point. ``render.sh`` and ``render.cmd`` are thin
shims that exec this script. ``_render.py`` is the helper module with the
actual ``cmd_prepare`` logic; it is kept separate for backwards compatibility
with any callers that still invoke it via environment variables.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure _render is importable when this file is run directly from any CWD.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _find_workspace(cwd: Path) -> Path | None:
    cur = cwd
    while True:
        if (cur / ".codenook").is_dir():
            return cur
        parent = cur.parent
        if parent == cur:
            return None
        cur = parent


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="render.py",
        description="view-renderer CLI — emit HITL prepare envelopes.",
    )
    sub = p.add_subparsers(dest="subcmd")

    prep_p = sub.add_parser("prepare", help="emit JSON envelope for one HITL entry")
    prep_p.add_argument("--id", required=True, dest="eid", metavar="ENTRY_ID",
                        help="HITL queue entry id (filename without .json)")
    prep_p.add_argument("--workspace", metavar="DIR",
                        help="workspace root (default: auto-detect from CWD)")

    args = p.parse_args(argv)

    if not args.subcmd:
        p.print_help(sys.stderr)
        return 2

    if args.subcmd == "prepare":
        from _render import cmd_prepare  # noqa: PLC0415

        if args.workspace:
            ws = Path(args.workspace).resolve()
        else:
            ws = _find_workspace(Path.cwd())
            if ws is None:
                sys.stderr.write(
                    "render.py: cannot find .codenook upwards; pass --workspace\n"
                )
                return 2

        if not ws.is_dir():
            sys.stderr.write(f"render.py: workspace not a directory: {ws}\n")
            return 2

        return cmd_prepare(ws, args.eid)

    sys.stderr.write(f"render.py: unknown subcommand: {args.subcmd!r}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
