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
    mem = workspace / ".codenook" / "memory"
    for sub in ("knowledge", "skills", "history", "_pending"):
        d = mem / sub
        d.mkdir(parents=True, exist_ok=True)
        gk = d / ".gitkeep"
        if not gk.is_file():
            gk.write_text("", encoding="utf-8")
    cfg = mem / "config.yaml"
    if not cfg.is_file():
        src_cfg = staged_kernel / "templates" / "memory-config.yaml"
        if src_cfg.is_file():
            shutil.copyfile(src_cfg, cfg)
    # v0.17.1 — seed an empty index.yaml so the conductor / kernel
    # surfaces that read it never face a missing file. Idempotent: if a
    # non-empty index already exists (e.g. populated by export_index_yaml)
    # we leave it alone.
    idx = mem / "index.yaml"
    if not idx.is_file():
        idx.write_text(
            "version: 1\n"
            "generated_at: null\n"
            "skills: []\n"
            "knowledge: []\n",
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
