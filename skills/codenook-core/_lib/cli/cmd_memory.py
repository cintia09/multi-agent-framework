"""``codenook memory`` — workspace-memory utilities.

Subcommands:
  doctor [--repair] [--json]    diagnose (and optionally auto-repair)
                                frontmatter issues in
                                ``<ws>/.codenook/memory/knowledge/*.md``
                                and ``skills/<name>/SKILL.md``. Plugin
                                files are scanned read-only.

The actual scan / repair logic lives in
``skills/builtin/_lib/memory_doctor.py`` so it can be unit-tested
without spinning up the CLI.
"""
from __future__ import annotations

import json
import sys
from typing import Sequence

from .config import CodenookContext


USAGE = """\
codenook memory — workspace memory utilities

Subcommands:
  memory doctor [--repair] [--json]
                                  diagnose frontmatter issues in
                                  .codenook/memory/{knowledge,skills};
                                  --repair auto-fixes workspace files
                                  (backups under .repair-backup/).
"""


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0

    sub = args[0]
    rest = list(args[1:])

    if sub == "doctor":
        return _cmd_doctor(ctx, rest)

    sys.stderr.write(f"codenook memory: unknown subcommand: {sub}\n")
    sys.stderr.write(USAGE)
    return 2


def _cmd_doctor(ctx: CodenookContext, args: list[str]) -> int:
    repair = False
    as_json = False
    for a in args:
        if a == "--repair":
            repair = True
        elif a == "--json":
            as_json = True
        elif a in ("-h", "--help"):
            sys.stdout.write(
                "codenook memory doctor [--repair] [--json]\n"
                "  --repair  auto-fix workspace memory files "
                "(backups under .repair-backup/)\n"
                "  --json    emit the report as JSON\n"
            )
            return 0
        else:
            sys.stderr.write(f"codenook memory doctor: unknown arg: {a}\n")
            return 2

    import memory_doctor  # type: ignore  # kernel lib on sys.path via config.load_context

    report = memory_doctor.diagnose(ctx.workspace, repair=repair)

    if as_json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(memory_doctor.render_report(report, repaired=repair))

    has_issues = bool(report.get("workspace_issues") or report.get("plugin_issues"))
    if repair:
        # After repair, only unfixed issues (workspace entries with
        # no `fixes` — e.g. missing frontmatter — plus plugin-side
        # issues) count as "problems remaining".
        unresolved = [
            d for d in (report.get("workspace_issues") or [])
            if not any(r["path"] == d["path"] for r in report.get("repaired") or [])
        ]
        if unresolved or report.get("plugin_issues"):
            return 1
        return 0
    return 1 if has_issues else 0
