"""Seed ``<ws>/.codenook/{schemas,memory,bin}`` and run claude_md_sync."""
from __future__ import annotations

import os
import shutil
import subprocess
import stat
import sys
from pathlib import Path


_SCHEMA_FILES = (
    "task-state.schema.json",
    "hitl-entry.schema.json",
    "queue-entry.schema.json",
    "locks-entry.schema.json",
    "installed.schema.json",
)


def seed_schemas(staged_kernel: Path, workspace: Path) -> None:
    src = staged_kernel / "schemas"
    dst = workspace / ".codenook" / "schemas"
    dst.mkdir(parents=True, exist_ok=True)
    for name in _SCHEMA_FILES:
        s = src / name
        if s.is_file():
            shutil.copyfile(s, dst / name)
    example = staged_kernel / "templates" / "state.example.md"
    if example.is_file():
        shutil.copyfile(example, dst / "state.example.md")
    legacy = workspace / ".codenook" / "state.example.md"
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass


def seed_memory(staged_kernel: Path, workspace: Path) -> None:
    """Seed only the three remaining memory subdirs (v0.29.0+).

    The legacy ``_pending/`` staging area, ``config.yaml`` (memory
    knobs) and auto-rebuilt ``index.yaml`` are gone — manual knowledge
    is dropped directly into ``knowledge/<slug>/`` or
    ``skills/<slug>/``, and ``codenook knowledge search`` walks the
    disk live (no index file). The ``staged_kernel`` parameter is kept
    for signature stability with prior install hooks.
    """
    del staged_kernel  # unused since v0.29.0
    mem = workspace / ".codenook" / "memory"
    for sub in ("knowledge", "skills", "history"):
        d = mem / sub
        d.mkdir(parents=True, exist_ok=True)
        gk = d / ".gitkeep"
        if not gk.is_file():
            gk.write_text("", encoding="utf-8")


def seed_config(workspace: Path) -> None:
    """Seed ``<ws>/.codenook/config.yaml`` with a commented model hint.

    Idempotent: never overwrite an existing config.yaml.
    """
    cfg = workspace / ".codenook" / "config.yaml"
    if cfg.is_file():
        return
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        "# CodeNook workspace config\n"
        "#\n"
        "# default_model: claude-sonnet-4.6   # uncomment to set workspace default\n"
        "#\n"
        "# Lowest-priority layer (D) in the model resolution chain. Higher\n"
        "# layers (in order): plugin.yaml :: default_model (A),\n"
        "# phases.yaml :: phases[*].model (B), task state.json :: model_override (C).\n",
        encoding="utf-8",
    )


def seed_bin(staged_kernel: Path, workspace: Path,
             python_exe: str | None = None) -> None:
    """Render the bin shims with the recorded python interpreter path.

    *python_exe* is the absolute path of whatever python ran the
    installer (typically ``sys.executable``). It is baked into both the
    POSIX shebang and the Windows ``%PY_EXE_RECORDED%`` variable so the
    shims work even when ``python`` / ``python3`` is not on ``PATH``.
    """
    bin_dir = workspace / ".codenook" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    py_exe = python_exe or sys.executable or ""

    posix_src = staged_kernel / "templates" / "codenook-bin"
    if posix_src.is_file():
        dst = bin_dir / "codenook"
        text = posix_src.read_text(encoding="utf-8").replace(
            "{{PY_EXE}}", py_exe or "/usr/bin/env python3"
        )
        dst.write_text(text, encoding="utf-8")
        try:
            mode = dst.stat().st_mode
            dst.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass

    win_src = staged_kernel / "templates" / "codenook-bin.cmd"
    if win_src.is_file():
        text = win_src.read_text(encoding="utf-8").replace(
            "{{PY_EXE}}", py_exe
        )
        (bin_dir / "codenook.cmd").write_text(text, encoding="utf-8")


def sync_claude_md(
    *,
    staged_kernel: Path,
    workspace: Path,
    plugin_id: str,
    version: str,
) -> int:
    helper = (
        staged_kernel / "skills" / "builtin" / "_lib" / "claude_md_sync.py"
    )
    if not helper.is_file():
        sys.stderr.write(f"install: claude_md_sync.py missing: {helper}\n")
        return 1
    cp = subprocess.run(
        [sys.executable, str(helper),
         "--workspace", str(workspace),
         "--version", version,
         "--plugin", plugin_id],
        env=_kernel_env(staged_kernel),
        text=True,
    )
    return cp.returncode


def _kernel_env(staged_kernel: Path) -> dict:
    env = os.environ.copy()
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(staged_kernel / "skills" / "builtin" / "_lib")
        + (os.pathsep + pp if pp else "")
    )
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def assert_state_kernel_version(workspace: Path, version: str) -> bool:
    """Post-install assertion: state.json.kernel_version == VERSION."""
    import json
    sf = workspace / ".codenook" / "state.json"
    if not sf.is_file():
        return False
    try:
        d = json.loads(sf.read_text(encoding="utf-8"))
    except Exception:
        return False
    return d.get("kernel_version") == version


def reindex_knowledge(staged_kernel: Path, workspace: Path) -> tuple[int, str]:
    """Deprecated since v0.29.0 — knowledge index is no longer materialised.

    ``codenook knowledge search`` walks the disk directly. Kept as a
    no-op so older callers in ``_lib/install/cli.py`` (or out-of-tree
    installer scripts) don't crash.
    """
    del staged_kernel, workspace
    return 0, "deprecated (v0.29.0): no on-disk index.yaml; live disk scan only"
