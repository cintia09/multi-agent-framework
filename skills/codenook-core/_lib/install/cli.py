"""Top-level installer entry: ``python install.py [...]``.

Surface mirrors the legacy ``install.sh``:

  python install.py [--target <dir>] [--upgrade] [--plugin <id|all>]
                    [--no-claude-md] [--yes] [--check] [--dry-run] [--help]

Exit codes:
  0  installed (or dry-run pass / check ok)
  1  any gate failed
  2  usage / IO error
  3  already installed (without --upgrade)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import seed_workspace, stage_kernel, stage_plugins


_HERE = Path(__file__).resolve()
_KERNEL_ROOT = _HERE.parent.parent.parent  # codenook-core/
try:
    VERSION = (_KERNEL_ROOT / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    VERSION = "0.0.0"
DEFAULT_PLUGIN = "all"


USAGE = f"""\
CodeNook installer v{VERSION}

Usage:
  python install.py [--target <workspace>] [--upgrade] [--plugin <id|all>]
                    [--no-claude-md] [--yes] [--check] [--dry-run] [--help]

When --target is omitted the current working directory is used.
"""


def _check_workspace(workspace: Path) -> int:
    print("━" * 38)
    print(f"🔍 CodeNook v{VERSION} — workspace status")
    print("━" * 38)
    print(f"  Workspace : {workspace}")
    state_file = workspace / ".codenook" / "state.json"
    if state_file.is_file():
        print(f"  ✓ .codenook/state.json present")
        for line in state_file.read_text(encoding="utf-8").splitlines():
            print(f"    {line}")
    else:
        print("  ⚠ no .codenook/state.json — workspace not initialised")
    cm = workspace / "CLAUDE.md"
    if cm.is_file() and "codenook:begin" in cm.read_text(encoding="utf-8", errors="ignore"):
        print("  ✓ CLAUDE.md has codenook bootloader block")
    else:
        print("  ⚠ CLAUDE.md has no codenook bootloader block")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="install.py", add_help=False,
        description=f"CodeNook installer v{VERSION}",
    )
    p.add_argument("--help", "-h", action="store_true")
    p.add_argument("--target")
    p.add_argument("--upgrade", action="store_true")
    p.add_argument("--plugin", default=DEFAULT_PLUGIN)
    p.add_argument("--no-claude-md", dest="claude_md", action="store_false",
                   default=True)
    p.add_argument("--yes", "-y", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    # Positional fallback (matches the bash form: ``install.sh <path>``).
    p.add_argument("positional", nargs="?")

    try:
        args = p.parse_args(argv if argv is not None else sys.argv[1:])
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 2

    if args.help:
        print(USAGE)
        return 0

    target = args.target or args.positional or "."
    workspace = Path(target).expanduser().resolve()
    if not workspace.is_dir():
        sys.stderr.write(f"install: workspace not found: {workspace}\n")
        return 2

    if args.check:
        return _check_workspace(workspace)

    repo_root = _repo_root()
    core_src = repo_root / "skills" / "codenook-core"
    if not core_src.is_dir():
        sys.stderr.write(f"install: source codenook-core not found: {core_src}\n")
        return 2

    plugin_arg = args.plugin
    if plugin_arg == "all":
        plugin_ids = stage_plugins.discover_plugins(repo_root)
        if not plugin_ids:
            sys.stderr.write(
                f"install: no installable plugins under {repo_root}/plugins\n")
            return 2
    else:
        plugin_ids = [plugin_arg]

    print("━" * 38)
    print(f"📦 CodeNook v{VERSION}")
    print("━" * 38)
    print(f"  Workspace : {workspace}")
    print(f"  Plugins   : {', '.join(plugin_ids)}")
    if args.dry_run:
        print(f"  Mode      : DRY-RUN")
    elif args.upgrade:
        print(f"  Mode      : UPGRADE")
    print()

    # 1) Stage kernel + memory skeleton (idempotent).
    staged = stage_kernel.stage_kernel(core_src, workspace)
    stage_kernel.init_memory_skeleton(workspace)
    print(f"  ✓ Kernel staged at {staged}")

    # 2) Per-plugin install (orchestrator pipeline).
    last_plugin = ""
    last_version = ""
    for pid in plugin_ids:
        version = stage_plugins.read_plugin_version(repo_root / "plugins" / pid)
        rc = stage_plugins.install_plugin(
            repo_root=repo_root,
            workspace=workspace,
            staged_kernel=staged,
            plugin_id=pid,
            version=version,
            upgrade=args.upgrade,
            dry_run=args.dry_run,
        )
        if rc != 0:
            sys.stderr.write(
                f"install: plugin '{pid}' failed (rc={rc})\n")
            return rc
        last_plugin = pid
        last_version = version
        print(f"  ✓ Plugin '{pid}' installed (v{version})")

    if args.dry_run:
        print("  [DRY-RUN] skipping CLAUDE.md / bin / schemas seeding")
        return 0

    # 3) CLAUDE.md augmentation (single-shot, last plugin wins as before).
    if args.claude_md:
        rc = seed_workspace.sync_claude_md(
            staged_kernel=staged,
            workspace=workspace,
            plugin_id=last_plugin,
            version=VERSION,
        )
        if rc == 0:
            print("  ✓ CLAUDE.md bootloader block synced")
        else:
            sys.stderr.write("install: CLAUDE.md sync failed\n")
            return rc
    else:
        print("  ⚠ skipped CLAUDE.md augmentation (--no-claude-md)")

    # 3b) v0.27.21 — run `memory doctor --repair` so any pre-existing
    # frontmatter damage (stray datetime.date values, non-list tags,
    # hex-literal ints) gets fixed before the workspace is used. Only
    # runs during a real install (skipped for --check / --dry-run).
    _run_post_install_doctor(staged, workspace)

    # 4) Schemas + memory + bin shim seeding.
    seed_workspace.seed_schemas(staged, workspace)
    seed_workspace.seed_memory(staged, workspace)
    seed_workspace.seed_config(workspace)
    seed_workspace.seed_bin(staged, workspace, python_exe=sys.executable)
    print("  ✓ Seeded .codenook/{schemas,memory,config.yaml,bin/codenook}")

    # 4b) v0.21.0 — populate memory/index.yaml with the recursive
    # plugin-knowledge scan so the conductor / phase agents see every
    # shipped baseline / case / fingerprint, not just top-level files.
    rc_idx, msg_idx = seed_workspace.reindex_knowledge(staged, workspace)
    if rc_idx == 0:
        print(f"  ✓ Reindexed knowledge ({msg_idx})")
    else:
        sys.stderr.write(
            f"install: knowledge reindex failed (rc={rc_idx}): {msg_idx}\n"
            f"         memory/index.yaml left as the empty stub.\n"
        )

    # 5) Post-install assertion: state.json.kernel_version matches VERSION.
    if not seed_workspace.assert_state_kernel_version(workspace, VERSION):
        sys.stderr.write(
            f"install: post-install assertion failed: "
            f"state.json.kernel_version != {VERSION}\n"
        )
        return 1

    print()
    print("  Quick start:")
    print(f"    cd \"{workspace}\"")
    if sys.platform == "win32":
        print("    .codenook\\bin\\codenook.cmd --help")
    else:
        print("    .codenook/bin/codenook --help")
    return 0


def _run_post_install_doctor(staged_kernel: Path, workspace: Path) -> None:
    """Best-effort ``memory doctor --repair`` as a post-install hook.

    Imports the doctor module off the staged kernel so the hook works
    even when the workspace does not yet have the bin shim on PATH.
    Never aborts install: prints a warning on any failure.
    """
    lib_dir = staged_kernel / "skills" / "builtin" / "_lib"
    if not lib_dir.is_dir():
        return
    import sys as _sys
    added = False
    if str(lib_dir) not in _sys.path:
        _sys.path.insert(0, str(lib_dir))
        added = True
    try:
        import memory_doctor  # type: ignore
        report = memory_doctor.diagnose(workspace, repair=True)
    except Exception as e:  # pragma: no cover — defensive
        sys.stderr.write(f"install: memory doctor skipped ({e})\n")
        return
    finally:
        if added:
            try:
                _sys.path.remove(str(lib_dir))
            except ValueError:
                pass

    repaired = report.get("repaired") or []
    ws_issues = report.get("workspace_issues") or []
    plug_issues = report.get("plugin_issues") or []
    unresolved = [
        d for d in ws_issues
        if not any(r["path"] == d["path"] for r in repaired)
    ]

    clean = report.get("workspace_clean", 0)
    if repaired:
        print(f"  ✓ memory doctor: repaired {len(repaired)} file(s) "
              f"({clean} already clean)")
        for r in repaired:
            rel = _short(workspace, r["path"])
            print(f"      · {rel}: {', '.join(r['actions'])}")
    elif ws_issues:
        print(f"  ⚠ memory doctor: {len(unresolved)} workspace issue(s) "
              f"needing manual review")
    else:
        print(f"  ✓ memory doctor: {clean} memory file(s) clean")

    if plug_issues:
        print(f"  ⚠ memory doctor: {len(plug_issues)} plugin file(s) "
              f"with frontmatter issues (read-only — report upstream):")
        for d in plug_issues[:5]:
            rel = _short(workspace, d["path"])
            pid = d.get("plugin", "?")
            print(f"      · [{pid}] {rel}")
        if len(plug_issues) > 5:
            print(f"      · … and {len(plug_issues) - 5} more")


def _short(workspace: Path, path: str) -> str:
    try:
        return str(Path(path).relative_to(workspace)).replace("\\", "/")
    except ValueError:
        return path


def _repo_root() -> Path:
    """Walk up from this file to find the repo root that contains
    ``skills/codenook-core/`` and ``plugins/``."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "skills" / "codenook-core").is_dir() and (parent / "plugins").is_dir():
            return parent
    # Fallback: walk up 6 levels (this file at
    # skills/codenook-core/_lib/install/cli.py).
    return here.parents[3]
