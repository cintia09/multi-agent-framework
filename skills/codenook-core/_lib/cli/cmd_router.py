"""``codenook router`` — passthrough to router-agent/render_prompt.py.

Accepts every flag render_prompt.py understands so the main session never
needs to invoke the underlying bash spawn.sh directly. Supported modes:

  codenook router --task T-NNN
      First dispatch (no user input yet).

  codenook router --task T-NNN --user-turn "..."
      Inline follow-up turn.

  codenook router --task T-NNN --user-turn-file <path>
      Follow-up turn read from a file (preserves multi-line / quoting).

  codenook router --task T-NNN --confirm
      Operator confirmation; freezes the draft and runs the first tick.
"""
from __future__ import annotations

import sys
from typing import Sequence

from . import _subproc
from .config import CodenookContext


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    task = ""
    user_turn: str | None = None
    user_turn_file: str | None = None
    confirm = False
    lock_timeout: str | None = None

    it = iter(args)
    try:
        for a in it:
            if a == "--task":
                task = next(it)
            elif a == "--user-turn":
                user_turn = next(it)
            elif a == "--user-turn-file":
                user_turn_file = next(it)
            elif a == "--confirm":
                confirm = True
            elif a == "--lock-timeout":
                lock_timeout = next(it)
            else:
                sys.stderr.write(f"codenook router: unknown arg: {a}\n")
                return 2
    except StopIteration:
        sys.stderr.write("codenook router: missing value for last flag\n")
        return 2

    if not task:
        sys.stderr.write("codenook router: --task required\n")
        return 2

    helper = ctx.kernel_dir / "router-agent" / "render_prompt.py"
    if not helper.is_file():
        sys.stderr.write(f"codenook router: helper missing: {helper}\n")
        return 1

    helper_args = ["--task-id", task, "--workspace", str(ctx.workspace)]
    if user_turn is not None:
        helper_args += ["--user-turn", user_turn]
    if user_turn_file is not None:
        helper_args += ["--user-turn-file", user_turn_file]
    if confirm:
        helper_args += ["--confirm"]
    if lock_timeout is not None:
        helper_args += ["--lock-timeout", lock_timeout]

    cp = _subproc.run_helper(ctx, helper, args=helper_args)
    return cp.returncode
