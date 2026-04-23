"""Implementation of ``codenook upgrade``.

Walks every active task under ``.codenook/tasks/`` and migrates each
``state.json`` to the current schema_version. Idempotent — running it
twice is a no-op.

Layout:

    codenook upgrade [--dry-run] [--task T-NNN] [--json] [--yes]

* ``--dry-run`` : report what would change without writing.
* ``--task``    : restrict to one task (resolved via the same
                  ``resolve_task_id`` ladder as other subcommands).
* ``--json``    : machine-readable summary on stdout.
* ``--yes``     : suppress the interactive confirm when not in dry-run.

Exit codes:
    0 — every selected task is at the current schema_version (after
        migration if needed).
    1 — at least one migration failed (other tasks still attempted).
    2 — usage error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

from . import config as cli_config
from .config import CodenookContext


HELP = """\
codenook upgrade — migrate task state.json to the current schema_version

Usage:
  codenook upgrade [--task T-NNN] [--dry-run] [--yes] [--json]

Options:
  --task T-NNN   restrict to a single task
  --dry-run      print the plan without modifying any state.json
  --yes          skip confirmation prompt
  --json         emit a machine-readable summary on stdout

Each migration is registered under ``_lib/migrations/`` and is required
to be idempotent. Re-running ``upgrade`` with no pending migrations
exits 0 and prints "no migrations needed".
"""


def _load_state(sf: Path) -> dict | None:
    try:
        return json.loads(sf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _persist(sf: Path, state: dict) -> None:
    # Reuse the same atomic + schema-validated writer as cmd_task so
    # we never half-write a state.json on SIGINT.
    from . import cmd_task
    cmd_task._persist_state(sf, state)


def run(ctx: CodenookContext, argv: Sequence[str]) -> int:
    if argv and argv[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0

    only_task: str | None = None
    dry_run = False
    as_json = False
    auto_yes = False

    it = iter(argv)
    for tok in it:
        if tok == "--task":
            only_task = next(it, None)
            if not only_task:
                sys.stderr.write("codenook upgrade: --task needs a value\n")
                return 2
        elif tok == "--dry-run":
            dry_run = True
        elif tok == "--json":
            as_json = True
        elif tok in ("--yes", "-y"):
            auto_yes = True
        else:
            sys.stderr.write(f"codenook upgrade: unknown arg: {tok}\n")
            sys.stderr.write(HELP)
            return 2

    tasks_dir = ctx.workspace / ".codenook" / "tasks"
    if not tasks_dir.is_dir():
        if as_json:
            print(json.dumps({"upgraded": [], "skipped": [],
                              "errors": [], "current_schema": _current()}))
        else:
            print("codenook upgrade: no tasks directory; nothing to do")
        return 0

    from .config import resolve_task_id

    selected: list[Path] = []
    only_resolved: str | None = None
    if only_task:
        only_resolved, _cands = resolve_task_id(ctx.workspace, only_task)
        if only_resolved is None:
            sys.stderr.write(
                f"codenook upgrade: --task {only_task} did not match "
                f"any active task\n")
            return 2

    for d in cli_config.iter_active_task_dirs(tasks_dir):
        if only_resolved and d.name != only_resolved:
            continue
        selected.append(d)

    from .. import migrations as migrations_proxy
    upgraded: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []

    for tdir in selected:
        sf = tdir / "state.json"
        st = _load_state(sf)
        if st is None:
            errors.append({"task": tdir.name,
                           "error": "could not read state.json"})
            continue
        cur_raw = st.get("schema_version", 1)
        cur = int(cur_raw) if cur_raw is not None else 1
        try:
            new_state, applied = migrations_proxy.upgrade(st)
        except Exception as exc:  # noqa: BLE001
            errors.append({"task": tdir.name, "error": str(exc),
                           "from_version": cur})
            continue

        if not applied:
            skipped.append({"task": tdir.name, "schema_version": cur})
            continue

        target = int(new_state["schema_version"])
        record = {"task": tdir.name, "from_version": cur,
                  "to_version": target, "migrations_applied": applied}
        if dry_run:
            upgraded.append({**record, "dry_run": True})
            continue

        if not auto_yes and sys.stdin.isatty():
            ans = input(
                f"upgrade {tdir.name}: v{cur} → v{target} "
                f"({len(applied)} migration(s)) [y/N]? ").strip().lower()
            if ans not in ("y", "yes"):
                skipped.append({**record, "reason": "user_declined"})
                continue
            auto_yes = True  # only ask once per invocation

        try:
            _persist(sf, new_state)
        except Exception as exc:  # noqa: BLE001
            errors.append({"task": tdir.name, "error": str(exc),
                           "from_version": cur})
            continue
        upgraded.append(record)

    summary = {
        "current_schema": _current(),
        "upgraded": upgraded,
        "skipped": skipped,
        "errors": errors,
    }

    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        if not upgraded and not errors:
            print(f"no migrations needed "
                  f"(all {len(selected)} task(s) at "
                  f"schema_version {_current()})")
        else:
            for u in upgraded:
                tag = " (dry-run)" if u.get("dry_run") else ""
                print(f"  upgraded {u['task']}: v{u['from_version']} → "
                      f"v{u['to_version']}{tag}")
            for s in skipped:
                if "reason" in s:
                    print(f"  skipped  {s['task']}: {s['reason']}")
            for e in errors:
                print(f"  ERROR    {e['task']}: {e['error']}")

    return 1 if errors else 0


def _current() -> int:
    from .. import migrations as migrations_proxy
    return migrations_proxy.CURRENT_SCHEMA_VERSION
