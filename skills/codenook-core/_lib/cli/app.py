"""codenook CLI front-end.

Subcommand surface mirrors the legacy ``codenook-wrapper.sh`` (v0.13.x)
1-for-1; see that file's header for user-facing docs. Each ``cmd_*``
module owns the argparse for its branch so this file stays a dispatcher.
"""
from __future__ import annotations

import sys
from typing import Sequence

from . import config


USAGE = """\
codenook — workspace CLI

Subcommands:
  task new --title "…" [--summary …] [--plugin <id>] [--profile <name>]
                       [--input <text>] [--input-file <path>] [--interactive]
                       [--target-dir <p>] [--dual-mode serial|parallel]
                       [--max-iterations N] [--parent T-X]
                       [--priority P0|P1|P2|P3] [--accept-defaults]
                       [--model <name>] [--exec sub-agent|inline]
  task list [--status <s>] [--phase <p>] [--plugin <id>]
            [--include-done] [--json]
  task delete <T-NNN> [T-NNN ...] [--task T-NNN] [--status <s>]
              [--purge] [--force] [--yes] [--dry-run] [--json]
  task restore [<T-NNN> | <archived-name>] [--task T-NNN] [--from <name>]
               [--list] [--no-hitl-restore] [--yes] [--dry-run] [--json]
  task set --task T-NNN --field <field> --value <val>
  task set-model   --task T-NNN (--model <name> | --clear)
  task set-exec    --task T-NNN --mode <sub-agent|inline>
  task set-profile --task T-NNN --profile <name>
  plugin info <id>     show profiles + phases summary for a plugin
  router   --task T-NNN [--user-turn "…" | --user-turn-file <p> | --confirm]
                       [DEPRECATED — slated for removal in a future release;
                        prefer the conductor-driven `task new --plugin <id>`
                        flow which avoids the extra LLM round-trip]
  tick     --task T-NNN [--json]
  decide   --task T-NNN --phase <id> --decision approve|reject|needs_changes
                                    [--comment "…"]
  hitl     <list|show|decide> [args...]
  extract  --task T-NNN --reason <reason> [--phase <phase>]
  status   [--task T-NNN]
  chain    link  --child T-X --parent T-Y [--force]
  chain    show  <task>
  chain    detach <task>
  knowledge reindex
  knowledge list [--plugin <id>] [--limit N]
  knowledge search <query> [--limit N]

Global flags:
  --workspace <dir>   override workspace root (else: derived from CWD or
                      installed bin location)
  --version           print kernel version
  -h, --help          show this help

Exit codes:
  0 ok | 1 runtime error | 2 entry-question / usage | 3 already attached / not modified
"""


def _print_version(args: Sequence[str]) -> int:
    workspace = config.resolve_workspace()
    ctx = config.load_context(workspace)
    print(ctx.kernel_version)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])

    workspace_override: str | None = None
    if argv and argv[0] == "--workspace":
        if len(argv) < 2:
            sys.stderr.write("codenook: --workspace needs a value\n")
            return 2
        workspace_override = argv[1]
        argv = argv[2:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    sub = argv[0]
    rest = argv[1:]

    if sub == "--version":
        ws = config.resolve_workspace(workspace_override)
        ctx = config.load_context(ws)
        print(ctx.kernel_version)
        return 0

    workspace = config.resolve_workspace(workspace_override)
    ctx = config.load_context(workspace)

    if sub == "task":
        from . import cmd_task
        return cmd_task.run(ctx, rest)
    if sub == "router":
        sys.stderr.write(
            "codenook: WARNING — the `router` subcommand is deprecated and "
            "will be removed in a future release. Prefer the conductor-driven "
            "`task new --plugin <id>` flow.\n"
        )
        from . import cmd_router
        return cmd_router.run(ctx, rest)
    if sub == "tick":
        from . import cmd_tick
        return cmd_tick.run(ctx, rest)
    if sub == "decide":
        from . import cmd_decide
        return cmd_decide.run(ctx, rest)
    if sub == "hitl":
        from . import cmd_hitl
        return cmd_hitl.run(ctx, rest)
    if sub == "extract":
        from . import cmd_extract
        return cmd_extract.run(ctx, rest)
    if sub == "status":
        from . import cmd_status
        return cmd_status.run(ctx, rest)
    if sub == "chain":
        from . import cmd_chain
        return cmd_chain.run(ctx, rest)
    if sub == "plugin":
        from . import cmd_plugin
        return cmd_plugin.run(ctx, rest)
    if sub == "knowledge":
        from . import cmd_knowledge
        return cmd_knowledge.run(ctx, rest)

    sys.stderr.write(f"codenook: unknown subcommand: {sub}\n")
    sys.stderr.write(USAGE)
    return 2
