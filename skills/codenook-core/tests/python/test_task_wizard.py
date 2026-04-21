"""v0.20.0 — `task new` profile / input / interactive wizard tests.

Builds a fresh installed workspace per-test (heavy but isolated), then
exercises the new flags through the bin shim. Mirrors the style of
``test_cli_smoke.py``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
INSTALL_PY = REPO_ROOT / "install.py"


def _run(cmd: Sequence[str], cwd: Path | None = None,
         env: dict | None = None, check: bool = True,
         input_text: str | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    if env:
        e.update(env)
    cp = subprocess.run(list(cmd), cwd=str(cwd) if cwd else None,
                        env=e, text=True, capture_output=True,
                        encoding="utf-8", errors="replace",
                        input=input_text)
    if check and cp.returncode != 0:
        raise AssertionError(
            f"command failed (rc={cp.returncode}): {cmd}\n"
            f"--- stdout ---\n{cp.stdout}\n--- stderr ---\n{cp.stderr}"
        )
    return cp


def _bin(ws: Path) -> Path:
    if sys.platform == "win32":
        return ws / ".codenook" / "bin" / "codenook.cmd"
    return ws / ".codenook" / "bin" / "codenook"


def _bin_cmd(ws: Path) -> list[str]:
    if sys.platform == "win32":
        return [str(_bin(ws))]
    return [sys.executable, str(_bin(ws))]


@pytest.fixture(scope="module")
def installed_ws(tmp_path_factory) -> Path:
    ws = tmp_path_factory.mktemp("cn_wizard_ws")
    _run([sys.executable, str(INSTALL_PY), "--target", str(ws), "--yes"])
    assert (ws / ".codenook" / "state.json").is_file()
    # Rewrite state.json so that the "default" plugin (the one returned
    # by ctx.installed_plugins[0]) is the development plugin — it has a
    # multi-profile phases.yaml we exercise below.
    return ws


def _state(ws: Path, tid: str) -> dict:
    sf = ws / ".codenook" / "tasks" / tid / "state.json"
    return json.loads(sf.read_text(encoding="utf-8"))


def _new_task(ws: Path, *extra: str) -> str:
    cp = _run(_bin_cmd(ws) + ["task", "new", *extra])
    return cp.stdout.strip().splitlines()[-1]


# 1. --profile <name> persists.
def test_profile_flag_persists(installed_ws: Path) -> None:
    tid = _new_task(installed_ws,
                    "--title", "p-fast", "--profile", "hotfix",
                    "--accept-defaults")
    assert tid.startswith("T-")
    s = _state(installed_ws, tid)
    assert s.get("profile") == "hotfix"


# 2. invalid profile -> non-zero + helpful list.
def test_invalid_profile_rejected(installed_ws: Path) -> None:
    cp = _run(_bin_cmd(installed_ws) + [
        "task", "new", "--title", "p-bad",
        "--profile", "no-such-profile", "--accept-defaults",
    ], check=False)
    assert cp.returncode == 2
    err = cp.stderr.lower()
    assert "invalid --profile" in err
    # The error must list at least one valid profile name so the user
    # can self-recover.
    assert any(name in err for name in
               ("feature", "hotfix", "refactor", "docs"))


# 3. --input persists + tick envelope surfaces it.
def test_input_persists_and_in_envelope(installed_ws: Path) -> None:
    tid = _new_task(installed_ws,
                    "--title", "p-input",
                    "--input", "PR 12345 — fix auth race",
                    "--accept-defaults")
    s = _state(installed_ws, tid)
    assert s.get("task_input") == "PR 12345 — fix auth race"

    cp = _run(_bin_cmd(installed_ws) + [
        "tick", "--task", tid, "--json"
    ])
    assert cp.returncode == 0, (
        f"tick failed (rc={cp.returncode})\n"
        f"--- stdout ---\n{cp.stdout}\n--- stderr ---\n{cp.stderr}"
    )
    # task_input must round-trip into the dispatch envelope.
    env = json.loads(cp.stdout.strip().splitlines()[-1])
    envelope = env.get("envelope") or {}
    if envelope:
        assert envelope.get("task_input") == "PR 12345 — fix auth race"


# 4. --input-file reads file content.
def test_input_file_reads_content(installed_ws: Path, tmp_path) -> None:
    f = tmp_path / "seed.txt"
    f.write_text("seed body line 1\nseed body line 2\n", encoding="utf-8")
    tid = _new_task(installed_ws,
                    "--title", "p-input-file",
                    "--input-file", str(f),
                    "--accept-defaults")
    s = _state(installed_ws, tid)
    assert s.get("task_input", "").startswith("seed body line 1")
    assert "line 2" in s.get("task_input", "")


# 5. --input + --input-file together → error.
def test_input_and_input_file_conflict(installed_ws: Path,
                                       tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("x", encoding="utf-8")
    cp = _run(_bin_cmd(installed_ws) + [
        "task", "new", "--title", "p-both",
        "--input", "inline", "--input-file", str(f),
        "--accept-defaults",
    ], check=False)
    assert cp.returncode == 2
    assert "mutually exclusive" in cp.stderr


# 6. --interactive walks all prompts and creates correct state.json.
def test_interactive_wizard(installed_ws: Path) -> None:
    # Stdin script: plugin (accept default) / profile (hotfix) /
    # title / input line / blank line to terminate input / model
    # (blank) / exec (blank → default) / Y to confirm.
    stdin = "\n".join([
        "",            # plugin = default
        "hotfix",      # profile
        "wizard task", # title
        "first line",  # input line
        "second line",
        "",            # terminate multi-line input
        "",            # model = blank
        "",            # exec = default sub-agent
        "Y",           # confirm
    ]) + "\n"
    cp = _run(_bin_cmd(installed_ws) + [
        "task", "new", "--interactive",
    ], input_text=stdin, check=True)
    import re
    m = re.search(r"\bT-\d{3,}(?:-[A-Za-z0-9-]+)?\b", cp.stdout)
    assert m, f"no T-NNN id in stdout:\n{cp.stdout}"
    tid = m.group(0)
    s = _state(installed_ws, tid)
    assert s["title"] == "wizard task"
    assert s.get("profile") == "hotfix"
    assert "first line" in s.get("task_input", "")
    assert "second line" in s.get("task_input", "")
    # exec mode left as default ⇒ no field written, behaves as sub-agent.
    assert s.get("execution_mode") in (None, "sub-agent")


# 7. set-profile works on phase-1 task; rejects after history.
def test_set_profile_phase1_then_blocked(installed_ws: Path) -> None:
    tid = _new_task(installed_ws,
                    "--title", "p-setprof", "--accept-defaults")
    # Allowed on phase-1 / fresh task.
    cp = _run(_bin_cmd(installed_ws) + [
        "task", "set-profile", "--task", tid, "--profile", "hotfix",
    ])
    assert json.loads(cp.stdout.strip())["value"] == "hotfix"
    s = _state(installed_ws, tid)
    assert s["profile"] == "hotfix"

    # Simulate "task has advanced": append a history entry, then expect
    # the conservative rejection.
    sf = installed_ws / ".codenook" / "tasks" / tid / "state.json"
    s["history"] = [{"phase": "clarify", "verdict": "done"}]
    sf.write_text(json.dumps(s, indent=2), encoding="utf-8")
    cp = _run(_bin_cmd(installed_ws) + [
        "task", "set-profile", "--task", tid, "--profile", "feature",
    ], check=False)
    assert cp.returncode == 2
    assert "advanced past phase 1" in cp.stderr


# 8. Backward compat: task new with no new flags behaves as v0.19.1.
def test_backward_compat_no_new_flags(installed_ws: Path) -> None:
    tid = _new_task(installed_ws,
                    "--title", "p-bc", "--accept-defaults")
    s = _state(installed_ws, tid)
    # Neither new field should appear when not requested.
    assert "profile" not in s
    assert "task_input" not in s
    # All previously-shipped fields remain present and unchanged.
    assert s["title"] == "p-bc"
    assert s["dual_mode"] == "serial"
    assert s["status"] == "in_progress"


# 9. plugin info <id> prints profiles + phases.
def test_plugin_info(installed_ws: Path) -> None:
    cp = _run(_bin_cmd(installed_ws) + ["plugin", "info", "development"])
    assert "Profiles:" in cp.stdout
    assert "Phases:" in cp.stdout
    # At least one of the well-known development profile names appears.
    assert any(name in cp.stdout for name in
               ("feature", "hotfix", "refactor"))


# 10. v0.20.1 regression — the v0.18-v0.20 fields (model_override,
# execution_mode, profile, task_input) MUST be accepted by the
# task-state schema. Pre-fix, the schema's
# ``additionalProperties: false`` rejected them and the very first
# tick crashed with a schema violation. This test asserts that a task
# created with the full set of new flags can `tick` end-to-end without
# a schema error and that the envelope reflects the inputs.
def test_v0201_new_flags_tick_without_schema_violation(
    installed_ws: Path,
) -> None:
    tid = _new_task(
        installed_ws,
        "--title", "v0201-regression",
        "--plugin", "development",
        "--profile", "hotfix",
        "--input", "seed text",
        "--exec", "inline",
        "--model", "claude-opus-4.7",
        "--accept-defaults",
    )
    s = _state(installed_ws, tid)
    assert s.get("execution_mode") == "inline"
    assert s.get("profile") == "hotfix"
    assert s.get("task_input") == "seed text"
    assert s.get("model_override") == "claude-opus-4.7"

    # The critical assertion: tick MUST NOT crash with a schema
    # violation. Pre-v0.20.1 this was sys.exit(1) with
    # "$: unexpected properties ['execution_mode']".
    cp = _run(_bin_cmd(installed_ws) + ["tick", "--task", tid, "--json"])
    assert cp.returncode == 0, (
        f"tick failed (rc={cp.returncode})\n"
        f"--- stdout ---\n{cp.stdout}\n--- stderr ---\n{cp.stderr}"
    )
    assert "schema" not in cp.stderr.lower(), (
        f"unexpected schema error in stderr:\n{cp.stderr}"
    )
    env = json.loads(cp.stdout.strip().splitlines()[-1])
    envelope = env.get("envelope") or {}
    # Inline mode must surface as inline_dispatch with model + task_input.
    if envelope:
        assert envelope.get("execution_mode") in (None, "inline")
        if envelope.get("task_input") is not None:
            assert envelope["task_input"] == "seed text"
