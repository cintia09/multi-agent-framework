"""``codenook hitl <list|show|render|decide>`` — thin dispatcher onto
``hitl-adapter/_hitl.py`` with the env-var protocol that script expects.
"""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from typing import Sequence

from . import _subproc
from .config import CodenookContext


HELP = """\
codenook hitl <subcmd> [args...]
  list    [--json]
  show    --id <hitl-entry-id> [--raw]
  prepare --id <hitl-entry-id>            (emit envelope for view-renderer)
  render  --id <hitl-entry-id> [--out <path>] [--open]
  decide  --id <id> --decision <approve|reject|needs_changes>
          [--reviewer <name>] [--comment "..."]
"""


def _parse_kvargs(args: list[str]) -> dict[str, object]:
    """Parse a flat list of ``--flag value`` pairs (and bare ``--json``).
    Returns a dict; unknown flags are written to stderr and we return ``{}``
    plus the caller falls back."""
    out: dict[str, object] = {}
    it = iter(args)
    for a in it:
        if a == "--json":
            out["__json__"] = True
            continue
        if a == "--open":
            out["open"] = True
            continue
        if a == "--raw":
            out["raw"] = True
            continue
        if a.startswith("--"):
            try:
                out[a[2:]] = next(it)
            except StopIteration:
                out[a[2:]] = ""
        else:
            out.setdefault("__pos__", []).append(a)  # type: ignore[attr-defined]
    return out


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        print(HELP)
        return 0

    sub = args[0]
    rest = list(args[1:])

    helper = ctx.kernel_dir / "hitl-adapter" / "_hitl.py"
    if not helper.is_file():
        sys.stderr.write(f"codenook hitl: helper missing: {helper}\n")
        return 1

    if sub == "list":
        kv = _parse_kvargs(rest)
        extra = {
            "CN_SUBCMD": "list",
            "CN_WORKSPACE": str(ctx.workspace),
            "CN_JSON": "1" if kv.get("__json__") else "0",
        }
        return _exec(ctx, helper, extra)

    if sub == "show":
        kv = _parse_kvargs(rest)
        eid = kv.get("id") or ""
        extra = {
            "CN_SUBCMD": "show",
            "CN_ID": str(eid),
            "CN_WORKSPACE": str(ctx.workspace),
            "CN_JSON": "0",
            "CN_RAW": "1" if kv.get("raw") else "0",
        }
        return _exec(ctx, helper, extra)

    if sub == "prepare":
        kv = _parse_kvargs(rest)
        eid = kv.get("id") or ""
        renderer = ctx.kernel_dir / "view-renderer" / "render.py"
        if not renderer.is_file():
            sys.stderr.write(f"codenook hitl: view-renderer missing: {renderer}\n")
            return 1
        return subprocess.call([
            sys.executable, str(renderer), "prepare",
            "--id", str(eid),
            "--workspace", str(ctx.workspace),
        ])

    if sub == "render":
        kv = _parse_kvargs(rest)
        extra = {
            "CN_SUBCMD": "render-html",
            "CN_ID": str(kv.get("id") or ""),
            "CN_OUT": str(kv.get("out") or ""),
            "CN_OPEN": "1" if kv.get("open") else "0",
            "CN_WORKSPACE": str(ctx.workspace),
        }
        return _exec(ctx, helper, extra)

    if sub == "decide":
        kv = _parse_kvargs(rest)
        reviewer = (
            kv.get("reviewer")
            or os.environ.get("USER")
            or getpass.getuser()
            or "cli"
        )
        extra = {
            "CN_SUBCMD": "decide",
            "CN_ID": str(kv.get("id") or ""),
            "CN_DECISION": str(kv.get("decision") or ""),
            "CN_REVIEWER": str(reviewer),
            "CN_COMMENT": str(kv.get("comment") or ""),
            "CN_WORKSPACE": str(ctx.workspace),
            "CN_JSON": "0",
        }
        return _exec(ctx, helper, extra)

    sys.stderr.write(f"codenook hitl: unknown subcommand: {sub}\n")
    return 2


def _exec(ctx: CodenookContext, helper, extra: dict) -> int:
    cp = subprocess.run(
        [sys.executable, str(helper)],
        env=_subproc.kernel_env(ctx, extra),
        text=True,
    )
    return cp.returncode
