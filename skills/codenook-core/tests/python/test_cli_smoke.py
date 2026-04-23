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


def test_task_list_human_and_json(installed_workspace: Path) -> None:
    """`task list` should surface tasks created earlier in this module."""
    cp = _run(_bin_cmd(installed_workspace) + ["task", "list"])
    assert "Workspace:" in cp.stdout
    assert "Total tasks:" in cp.stdout
    cp = _run(_bin_cmd(installed_workspace) + ["task", "list", "--json"])
    payload = json.loads(cp.stdout)
    assert isinstance(payload, list)
    assert all("task_id" in r and "status" in r for r in payload)


def test_task_delete_archive_and_purge(installed_workspace: Path) -> None:
    ws = installed_workspace
    # Create two throwaway tasks first.
    a = _run(_bin_cmd(ws) + [
        "task", "new", "--title", "to-archive", "--accept-defaults",
    ]).stdout.strip().splitlines()[-1]
    b = _run(_bin_cmd(ws) + [
        "task", "new", "--title", "to-purge", "--accept-defaults",
    ]).stdout.strip().splitlines()[-1]
    a_dir = ws / ".codenook" / "tasks" / a
    b_dir = ws / ".codenook" / "tasks" / b
    assert a_dir.is_dir() and b_dir.is_dir()

    # Default = archive; --force needed because new tasks land in_progress.
    cp = _run(_bin_cmd(ws) + [
        "task", "delete", a, "--yes", "--force", "--json",
    ])
    payload = json.loads(cp.stdout)
    assert payload[0]["action"] == "archived"
    assert not a_dir.is_dir()
    archive_root = ws / ".codenook" / "tasks" / "_archive"
    assert any(p.name.startswith(a + "-") for p in archive_root.iterdir())

    # Purge irrecoverably.
    cp = _run(_bin_cmd(ws) + [
        "task", "delete", b, "--purge", "--yes", "--force", "--json",
    ])
    payload = json.loads(cp.stdout)
    assert payload[0]["action"] == "purged"
    assert not b_dir.is_dir()


def test_task_delete_unknown_task(installed_workspace: Path) -> None:
    cp = _run(
        _bin_cmd(installed_workspace) + [
            "task", "delete", "T-9999", "--yes",
        ],
        check=False,
    )
    assert cp.returncode == 1
    assert "no such task" in cp.stderr


def test_task_restore_round_trip(installed_workspace: Path) -> None:
    """delete (archive) then restore should round-trip the task dir."""
    ws = installed_workspace
    tid = _run(_bin_cmd(ws) + [
        "task", "new", "--title", "round-trip", "--accept-defaults",
    ]).stdout.strip().splitlines()[-1]
    task_dir = ws / ".codenook" / "tasks" / tid
    assert task_dir.is_dir()

    _run(_bin_cmd(ws) + [
        "task", "delete", tid, "--yes", "--force", "--json",
    ])
    assert not task_dir.is_dir()

    # --list should show the archived snapshot.
    cp = _run(_bin_cmd(ws) + ["task", "restore", "--list", "--json"])
    archived = json.loads(cp.stdout)
    assert any(p["name"].startswith(tid + "-") for p in archived)

    # Restore by bare T-NNN.
    cp = _run(_bin_cmd(ws) + [
        "task", "restore", tid, "--yes", "--json",
    ])
    payload = json.loads(cp.stdout)
    assert payload[0]["action"] == "restored"
    assert task_dir.is_dir()
    s = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
    assert s["title"] == "round-trip"


def test_hitl_pending_uses_json_task_id_not_prefix(
    installed_workspace: Path, tmp_path,
) -> None:
    """Regression: a queue file whose name starts with another task's
    id prefix must NOT be claimed by ``task list`` / ``task delete``.

    We seed two HITL queue files manually — one belonging to T-AAA,
    one belonging to T-AAA-extra (whose dir name starts with T-AAA-).
    Calling ``_collect_task_records`` on a task whose canonical id is
    T-AAA must return only the first one.
    """
    ws = installed_workspace
    queue = ws / ".codenook" / "hitl-queue"
    queue.mkdir(parents=True, exist_ok=True)
    a = queue / "T-AAA-foo_signoff.json"
    b = queue / "T-AAA-extra-bar_signoff.json"
    a.write_text(json.dumps({"task_id": "T-AAA", "id": "T-AAA-foo"}),
                 encoding="utf-8")
    b.write_text(json.dumps({"task_id": "T-AAA-extra", "id": "T-AAA-extra-bar"}),
                 encoding="utf-8")

    # Invoke the helper directly via a bin shim subprocess so we exercise
    # the full installed kernel path (mirrors how `task list` would call it).
    code = (
        "import json,sys;"
        "sys.path.insert(0,'_BIN_PARENT_/codenook-core');"
        "from _lib.cli.cmd_task import _hitl_pending_for;"
        "from pathlib import Path;"
        "print(json.dumps(_hitl_pending_for(Path(sys.argv[1]), sys.argv[2])))"
    ).replace("_BIN_PARENT_", str(ws / ".codenook"))
    cp = _run([sys.executable, "-c", code, str(ws), "T-AAA"])
    found = json.loads(cp.stdout)
    assert found == ["T-AAA-foo_signoff.json"], found

    # Cleanup so other tests aren't polluted.
    a.unlink()
    b.unlink()


def test_config_show_human_and_json(installed_workspace: Path) -> None:
    """`config show` should walk all four layers."""
    ws = installed_workspace
    tid = _run(_bin_cmd(ws) + [
        "task", "new", "--title", "config-show-fixture",
        "--accept-defaults",
    ]).stdout.strip().splitlines()[-1]

    cp = _run(_bin_cmd(ws) + ["config", "show", "--task", tid])
    assert "Resolution chain" in cp.stdout
    assert "C  task model_override" in cp.stdout
    assert "D  workspace default_model" in cp.stdout

    cp = _run(_bin_cmd(ws) + ["config", "show", "--task", tid, "--json"])
    payload = json.loads(cp.stdout)
    assert payload["task_id"].startswith("T-")
    assert {l["id"] for l in payload["layers"]} == {"A", "B", "C", "D"}


def test_plugin_lint_clean_and_broken(
    installed_workspace: Path, tmp_path,
) -> None:
    """Lint should pass on the shipped development plugin and fail
    when we corrupt a referenced role."""
    ws = installed_workspace
    cp = _run(_bin_cmd(ws) + ["plugin", "lint", "development", "--json"])
    payload = json.loads(cp.stdout)
    assert payload["ok"] is True, payload

    # Corrupt: remove a roles/<role>.md and re-lint a copied plugin.
    bad = tmp_path / "broken-plugin"
    import shutil
    shutil.copytree(
        ws / ".codenook" / "plugins" / "development", bad)
    (bad / "roles" / "implementer.md").unlink()

    cp = _run(_bin_cmd(ws) + ["plugin", "lint", str(bad), "--json"],
              check=False)
    payload = json.loads(cp.stdout)
    assert payload["ok"] is False
    codes = [v["code"] for v in payload["violations"]]
    assert "E_ROLE_MISSING" in codes


def test_task_list_tree(installed_workspace: Path) -> None:
    """--tree should show parent/child indentation."""
    ws = installed_workspace
    parent = _run(_bin_cmd(ws) + [
        "task", "new", "--title", "tree-parent", "--accept-defaults",
    ]).stdout.strip().splitlines()[-1]
    child = _run(_bin_cmd(ws) + [
        "task", "new", "--title", "tree-child",
        "--parent", parent, "--accept-defaults",
    ]).stdout.strip().splitlines()[-1]

    cp = _run(_bin_cmd(ws) + ["task", "list", "--tree", "--include-done"])
    out = cp.stdout
    assert parent in out
    assert child in out
    p_pos = out.index(parent)
    c_pos = out.index(child)
    assert p_pos < c_pos
    # child line must start with indentation that the parent line lacks
    child_line = [ln for ln in out.splitlines() if child in ln][0]
    assert child_line.startswith("  "), child_line
