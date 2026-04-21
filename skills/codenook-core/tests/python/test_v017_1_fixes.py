"""v0.17.1 — three kernel bugfixes.

Bug 1: install.py records sys.executable into bin shims.
Bug 2: seed_workspace creates memory/index.yaml.
Bug 3: cmd_status / iter_active_task_dirs skip dirs without state.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
KERNEL_ROOT = REPO_ROOT / "skills" / "codenook-core"

# Add the installer package to sys.path so we can import seed_workspace
# without going through subprocess.
sys.path.insert(0, str(KERNEL_ROOT))
sys.path.insert(0, str(KERNEL_ROOT / "_lib" / "cli"))

from _lib.install import seed_workspace  # noqa: E402
import config as cli_config  # noqa: E402


# ---------------------------------------------------------- Bug 1


def test_seed_bin_bakes_recorded_python_path(tmp_path: Path):
    """Bug 1 — both shims contain the recorded interpreter path."""
    workspace = tmp_path
    recorded = r"C:\Path With Spaces\python.exe"
    seed_workspace.seed_bin(KERNEL_ROOT, workspace, python_exe=recorded)

    cmd = (workspace / ".codenook" / "bin" / "codenook.cmd").read_text(
        encoding="utf-8")
    assert recorded in cmd
    assert "PY_EXE_RECORDED" in cmd
    # The PATH fallback must still be present.
    assert "where python" in cmd
    assert "py -3" in cmd

    posix = (workspace / ".codenook" / "bin" / "codenook").read_text(
        encoding="utf-8")
    # Shebang on the very first line.
    assert posix.splitlines()[0] == f"#!{recorded}"


def test_seed_bin_defaults_to_sys_executable(tmp_path: Path):
    """When ``python_exe`` is omitted, sys.executable is recorded."""
    seed_workspace.seed_bin(KERNEL_ROOT, tmp_path)
    cmd = (tmp_path / ".codenook" / "bin" / "codenook.cmd").read_text(
        encoding="utf-8")
    assert sys.executable in cmd


# ---------------------------------------------------------- Bug 2


def test_seed_memory_creates_index_yaml(tmp_path: Path):
    """Bug 2 — memory/index.yaml is seeded with the empty schema."""
    seed_workspace.seed_memory(KERNEL_ROOT, tmp_path)
    idx = tmp_path / ".codenook" / "memory" / "index.yaml"
    assert idx.is_file()
    text = idx.read_text(encoding="utf-8")
    assert "version: 1" in text
    assert "skills: []" in text
    assert "knowledge: []" in text


def test_seed_memory_index_yaml_is_idempotent(tmp_path: Path):
    """Existing non-empty index.yaml must not be overwritten."""
    mem = tmp_path / ".codenook" / "memory"
    mem.mkdir(parents=True)
    pre_existing = "version: 1\nskills:\n  - name: foo\n"
    (mem / "index.yaml").write_text(pre_existing, encoding="utf-8")

    seed_workspace.seed_memory(KERNEL_ROOT, tmp_path)

    assert (mem / "index.yaml").read_text(encoding="utf-8") == pre_existing


# ---------------------------------------------------------- Bug 3


def test_iter_active_task_dirs_skips_archive_dirs(tmp_path: Path):
    """Bug 3 — task discovery returns 0 entries for stray dirs."""
    tdir = tmp_path / ".codenook" / "tasks"
    tdir.mkdir(parents=True)
    # Three archive-style dirs without state.json.
    for name in ("T-101", "T-102", "T-103"):
        (tdir / name).mkdir()
        (tdir / name / "notes.md").write_text("legacy", encoding="utf-8")
    # And a few traps the helper must always reject.
    (tdir / ".gitignore").write_text("", encoding="utf-8")
    (tdir / "_pending").mkdir()
    (tdir / ".chain-snapshot.json").write_text("{}", encoding="utf-8")

    found = list(cli_config.iter_active_task_dirs(tdir))
    assert found == []


def test_iter_active_task_dirs_yields_real_tasks(tmp_path: Path):
    """A directory with state.json IS active."""
    tdir = tmp_path / ".codenook" / "tasks"
    (tdir / "T-001").mkdir(parents=True)
    (tdir / "T-001" / "state.json").write_text(
        json.dumps({"task_id": "T-001"}), encoding="utf-8")
    # And an archive sibling that should still be skipped.
    (tdir / "T-999").mkdir()

    found = [d.name for d in cli_config.iter_active_task_dirs(tdir)]
    assert found == ["T-001"]


def test_is_active_task_dir_rejects_files(tmp_path: Path):
    f = tmp_path / "not-a-dir"
    f.write_text("", encoding="utf-8")
    assert cli_config.is_active_task_dir(f) is False


def test_iter_active_task_dirs_handles_missing_dir(tmp_path: Path):
    """Returns nothing (no exception) when tasks/ does not exist."""
    assert list(cli_config.iter_active_task_dirs(tmp_path / "nope")) == []
