"""Pytest port of `tests/m2-plugin-id-validate.bats` (M2 Unit 3, gate G03).

Phase C2 batch 1: bats → pytest. The bats counterpart stays in
place during the transition.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
GATE_SH = (REPO / "skills" / "codenook-core" / "skills" / "builtin"
           / "plugin-id-validate" / "id-validate.sh")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(args, env=env, capture_output=True, text=True)


def _mk_src(tmp_path: Path, pid: str) -> Path:
    d = tmp_path / "p"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.yaml").write_text(
        f"id: {pid}\nversion: 0.1.0\n", encoding="utf-8")
    return d


def _mk_ws(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / ".codenook" / "plugins").mkdir(parents=True)
    return d


def test_gate_exists_and_executable():
    assert GATE_SH.is_file()
    assert os.access(GATE_SH, os.X_OK)


def test_missing_src_exits_2():
    cp = _run([str(GATE_SH)])
    assert cp.returncode == 2


def test_valid_id_exits_0(tmp_path):
    d = _mk_src(tmp_path, "foo-bar2")
    cp = _run([str(GATE_SH), "--src", str(d)])
    assert cp.returncode == 0, cp.stderr


@pytest.mark.parametrize("bad_id", ["FooBar", "1foo", "ab", "foo_bar"])
def test_invalid_id_exits_1(tmp_path, bad_id):
    d = _mk_src(tmp_path, bad_id)
    cp = _run([str(GATE_SH), "--src", str(d)])
    assert cp.returncode == 1


def test_reserved_id_core(tmp_path):
    d = _mk_src(tmp_path, "core")
    cp = _run([str(GATE_SH), "--src", str(d)])
    assert cp.returncode == 1
    assert "reserved" in cp.stderr.lower()


def test_generic_id_now_claimable(tmp_path):
    d = _mk_src(tmp_path, "generic")
    cp = _run([str(GATE_SH), "--src", str(d)])
    assert cp.returncode == 0


def test_reserved_id_codenook(tmp_path):
    d = _mk_src(tmp_path, "codenook")
    cp = _run([str(GATE_SH), "--src", str(d)])
    assert cp.returncode == 1


def test_already_installed_without_upgrade_fails(tmp_path):
    d = _mk_src(tmp_path, "foo")
    ws = _mk_ws(tmp_path)
    (ws / ".codenook" / "plugins" / "foo").mkdir()
    (ws / ".codenook" / "plugins" / "foo" / "plugin.yaml").write_text(
        "id: foo\nversion: 0.1.0\n", encoding="utf-8")
    cp = _run([str(GATE_SH), "--src", str(d), "--workspace", str(ws)])
    assert cp.returncode == 1
    assert "installed" in cp.stderr.lower()


def test_already_installed_with_upgrade_passes(tmp_path):
    d = _mk_src(tmp_path, "foo")
    ws = _mk_ws(tmp_path)
    (ws / ".codenook" / "plugins" / "foo").mkdir()
    (ws / ".codenook" / "plugins" / "foo" / "plugin.yaml").write_text(
        "id: foo\nversion: 0.1.0\n", encoding="utf-8")
    cp = _run([str(GATE_SH), "--src", str(d),
               "--workspace", str(ws), "--upgrade"])
    assert cp.returncode == 0


def test_json_envelope_on_failure(tmp_path):
    d = _mk_src(tmp_path, "BAD")
    cp = _run([str(GATE_SH), "--src", str(d), "--json"])
    assert cp.returncode == 1
    payload = json.loads(cp.stdout)
    assert payload["gate"] == "plugin-id-validate"
    assert payload["ok"] is False


def test_json_already_installed_code(tmp_path):
    d = _mk_src(tmp_path, "foo")
    ws = _mk_ws(tmp_path)
    (ws / ".codenook" / "plugins" / "foo").mkdir()
    (ws / ".codenook" / "plugins" / "foo" / "plugin.yaml").write_text(
        "id: foo\nversion: 0.1.0\n", encoding="utf-8")
    cp = _run([str(GATE_SH), "--src", str(d),
               "--workspace", str(ws), "--json"])
    assert cp.returncode == 1
    payload = json.loads(cp.stdout)
    assert payload["code"] == "already_installed"
    assert payload["ok"] is False


def test_json_g03_failure_no_already_installed_code(tmp_path):
    d = _mk_src(tmp_path, "BAD")
    cp = _run([str(GATE_SH), "--src", str(d), "--json"])
    assert cp.returncode == 1
    payload = json.loads(cp.stdout)
    assert payload.get("code") != "already_installed"
