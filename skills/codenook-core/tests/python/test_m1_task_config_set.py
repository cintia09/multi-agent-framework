"""Pytest port of `tests/m1-task-config-set.bats` (M1 Unit 10).

Phase C2 batch 1: migrating bats → pytest. Both files stay green
during the transition; the bats counterpart is kept in place until
the wider migration is finished.

The shell script under test (`task-config-set/set.sh`) is invoked as
a subprocess; we only assert observable contract:

* exit code (0 / 1 / 2)
* stderr contents on errors
* JSON shape of the resulting `state.json`

Why migrate this one first: it is one of the smallest CLI-only
gates (no LLM, no claude-md, no plugin install), so the port is
mechanical and serves as a template for follow-on batches.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
SET_SH = (REPO / "skills" / "codenook-core" / "skills" / "builtin"
          / "task-config-set" / "set.sh")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(args, env=env, capture_output=True, text=True)


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    (tmp_path / ".codenook" / "tasks").mkdir(parents=True)
    (tmp_path / ".codenook" / "history").mkdir(parents=True)
    return tmp_path


def _mk_task(ws: Path, tid: str) -> Path:
    tdir = ws / ".codenook" / "tasks" / tid
    tdir.mkdir(parents=True)
    (tdir / "state.json").write_text(json.dumps({
        "task_id": tid, "phase": "start", "iteration": 0,
        "config_overrides": {},
    }), encoding="utf-8")
    return tdir


def _state(ws: Path, tid: str) -> dict:
    return json.loads(
        (ws / ".codenook" / "tasks" / tid / "state.json").read_text(
            encoding="utf-8"))


def test_set_sh_exists_and_executable():
    assert SET_SH.is_file()
    assert os.access(SET_SH, os.X_OK)


def test_missing_args_exits_2(ws):
    cp = _run([str(SET_SH), "--workspace", str(ws)])
    assert cp.returncode == 2


def test_models_default_accepted(ws):
    _mk_task(ws, "T-001")
    cp = _run([str(SET_SH), "--task", "T-001",
               "--key", "models.default", "--value", "tier_strong",
               "--workspace", str(ws)])
    assert cp.returncode == 0, cp.stderr
    assert _state(ws, "T-001")["config_overrides"]["models"]["default"] == "tier_strong"


def test_models_role_variants_accepted(ws):
    _mk_task(ws, "T-002")
    cp = _run([str(SET_SH), "--task", "T-002",
               "--key", "models.reviewer", "--value", "tier_cheap",
               "--workspace", str(ws)])
    assert cp.returncode == 0
    assert _state(ws, "T-002")["config_overrides"]["models"]["reviewer"] == "tier_cheap"


def test_key_outside_allowlist_exits_1(ws):
    _mk_task(ws, "T-003")
    cp = _run([str(SET_SH), "--task", "T-003",
               "--key", "bad.key", "--value", "foo",
               "--workspace", str(ws)])
    assert cp.returncode == 1
    assert "allow" in cp.stderr.lower()


@pytest.mark.parametrize("tier", ["tier_strong", "tier_balanced", "tier_cheap"])
def test_value_tier_symbol_accepted(ws, tier):
    _mk_task(ws, "T-004")
    cp = _run([str(SET_SH), "--task", "T-004",
               "--key", "models.default", "--value", tier,
               "--workspace", str(ws)])
    assert cp.returncode == 0


def test_literal_model_id_no_spurious_warning(ws):
    _mk_task(ws, "T-005")
    cp = _run([str(SET_SH), "--task", "T-005",
               "--key", "models.executor", "--value", "unknown-model-xyz",
               "--workspace", str(ws)])
    assert cp.returncode == 0
    assert "unknown model" not in cp.stderr.lower()
    assert _state(ws, "T-005")["config_overrides"]["models"]["executor"] == "unknown-model-xyz"


def test_writes_under_correct_path(ws):
    _mk_task(ws, "T-006")
    cp = _run([str(SET_SH), "--task", "T-006",
               "--key", "models.planner", "--value", "tier_balanced",
               "--workspace", str(ws)])
    assert cp.returncode == 0
    assert _state(ws, "T-006")["config_overrides"]["models"]["planner"] == "tier_balanced"


def test_idempotent_re_set(ws):
    _mk_task(ws, "T-007")
    for _ in range(2):
        cp = _run([str(SET_SH), "--task", "T-007",
                   "--key", "models.default", "--value", "tier_strong",
                   "--workspace", str(ws)])
        assert cp.returncode == 0
    assert _state(ws, "T-007")["config_overrides"]["models"]["default"] == "tier_strong"


def test_unset_flag_removes_key(ws):
    _mk_task(ws, "T-008")
    cp = _run([str(SET_SH), "--task", "T-008",
               "--key", "models.reviewer", "--value", "tier_cheap",
               "--workspace", str(ws)])
    assert cp.returncode == 0
    cp = _run([str(SET_SH), "--task", "T-008",
               "--key", "models.reviewer", "--unset",
               "--workspace", str(ws)])
    assert cp.returncode == 0
    models = _state(ws, "T-008")["config_overrides"].get("models", {})
    assert "reviewer" not in models


def test_writes_nested_not_dotted(ws):
    _mk_task(ws, "T-100")
    cp = _run([str(SET_SH), "--task", "T-100",
               "--key", "models.reviewer", "--value", "tier_balanced",
               "--workspace", str(ws)])
    assert cp.returncode == 0
    co = _state(ws, "T-100")["config_overrides"]
    assert "models.reviewer" not in co
    assert co["models"]["reviewer"] == "tier_balanced"
