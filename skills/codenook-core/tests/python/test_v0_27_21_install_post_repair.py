"""Smoke test: ``install.py`` runs ``memory doctor --repair`` as a
post-install hook and prints a summary line. New in v0.27.21.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]


def test_install_prints_doctor_summary(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        [sys.executable, str(_REPO / "install.py"), "--target", str(ws), "--yes"],
        capture_output=True, text=True, env=env, cwd=str(_REPO),
        timeout=120, encoding="utf-8", errors="replace",
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "memory doctor" in combined


def test_install_check_skips_doctor(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [sys.executable, str(_REPO / "install.py"), "--target", str(ws), "--check"],
        capture_output=True, text=True, env=env, cwd=str(_REPO),
        timeout=60, encoding="utf-8", errors="replace",
    )
    combined = proc.stdout + proc.stderr
    # --check short-circuits before the doctor hook runs.
    assert "memory doctor" not in combined
