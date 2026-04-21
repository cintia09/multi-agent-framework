"""Subprocess smoke tests for the Python CLI + installer.

These tests build a fresh workspace under ``tmp_path``, run the new
``install.py`` against it, then exercise a few representative codenook
subcommands through the installed bin shim.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
INSTALL_PY = REPO_ROOT / "install.py"
EXPECTED_VERSION = (REPO_ROOT / "skills" / "codenook-core" / "VERSION").read_text(encoding="utf-8").strip()


def _run(cmd: list[str], cwd: Path | None = None,
         env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    if env:
        e.update(env)
    cp = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                        env=e, text=True, capture_output=True,
                        encoding="utf-8", errors="replace")
    if check and cp.returncode != 0:
        raise AssertionError(
            f"command failed (rc={cp.returncode}): {cmd}\n"
            f"--- stdout ---\n{cp.stdout}\n--- stderr ---\n{cp.stderr}"
        )
    return cp


@pytest.fixture(scope="module")
def installed_workspace(tmp_path_factory) -> Path:
    """Install CodeNook into a fresh workspace once per test module."""
    ws = tmp_path_factory.mktemp("cn_smoke_ws")
    cp = _run([sys.executable, str(INSTALL_PY), "--target", str(ws), "--yes"])
    assert "Kernel staged" in cp.stdout
    assert (ws / ".codenook" / "state.json").is_file()
    return ws


def _bin(ws: Path) -> Path:
    if sys.platform == "win32":
        return ws / ".codenook" / "bin" / "codenook.cmd"
    return ws / ".codenook" / "bin" / "codenook"


def _bin_cmd(ws: Path) -> list[str]:
    if sys.platform == "win32":
        return [str(_bin(ws))]
    return [sys.executable, str(_bin(ws))]


def test_install_creates_state_and_bin(installed_workspace: Path) -> None:
    ws = installed_workspace
    assert (ws / ".codenook" / "codenook-core" / "_lib" / "cli" / "__main__.py").is_file()
    assert _bin(ws).is_file()
    state = json.loads((ws / ".codenook" / "state.json").read_text(encoding="utf-8"))
    assert state.get("kernel_version") == EXPECTED_VERSION
    assert state.get("kernel_dir")


def test_version(installed_workspace: Path) -> None:
    cp = _run(_bin_cmd(installed_workspace) + ["--version"])
    assert cp.stdout.strip() == EXPECTED_VERSION


def test_help(installed_workspace: Path) -> None:
    cp = _run(_bin_cmd(installed_workspace) + ["--help"])
    assert "codenook" in cp.stdout
    assert "task new" in cp.stdout
    assert "tick" in cp.stdout


def test_status(installed_workspace: Path) -> None:
    cp = _run(_bin_cmd(installed_workspace) + ["status"])
    assert "Workspace:" in cp.stdout
    assert "kernel_version" in cp.stdout


def test_task_new_accept_defaults(installed_workspace: Path, tmp_path) -> None:
    """task new --accept-defaults should print the new T-NNN id and
    create a per-task state.json."""
    cp = _run(_bin_cmd(installed_workspace) + [
        "task", "new", "--title", "smoke",
        "--accept-defaults",
    ])
    tid = cp.stdout.strip().splitlines()[-1]
    assert tid.startswith("T-")
    sf = installed_workspace / ".codenook" / "tasks" / tid / "state.json"
    assert sf.is_file()
    s = json.loads(sf.read_text(encoding="utf-8"))
    assert s["title"] == "smoke"
    assert s["dual_mode"] == "serial"
    assert s["status"] == "in_progress"


def test_task_new_entry_question_without_dual_mode(installed_workspace: Path) -> None:
    cp = _run(
        _bin_cmd(installed_workspace) + [
            "task", "new", "--title", "needs-question",
        ],
        check=False,
    )
    assert cp.returncode == 2
    payload = json.loads(cp.stdout.strip().splitlines()[-1])
    assert payload["action"] == "entry_question"
    assert payload["field"] == "dual_mode"
