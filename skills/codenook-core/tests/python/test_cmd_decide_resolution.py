"""Tests for cmd_decide's two-pass gate resolution (v0.25.0).

The bootloader documents that `--phase` may be either the phase id
(e.g. `clarify`) or the gate id (e.g. `requirements_signoff`).
cmd_decide first tries the phase->gate mapping from the plugin manifest;
if that misses, it does a second pass treating --phase as the gate-id
directly. Without this fallback the conductor's documented surface
breaks for any phase whose gate has a different id.
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


_REPO = Path(__file__).resolve().parents[4]
_INSTALLER = _REPO / "install.py"


def _bootstrap_workspace(plugin: str = "writing") -> Path:
    ws = Path(tempfile.mkdtemp(prefix="cn_decide_test_"))
    cp = subprocess.run(
        [sys.executable, str(_INSTALLER),
         "--target", str(ws), "--plugin", plugin, "--yes"],
        capture_output=True, text=True,
    )
    if cp.returncode != 0:
        raise RuntimeError(
            f"installer failed: rc={cp.returncode} stderr={cp.stderr}")
    return ws


def _write_pending_gate(ws: Path, *, eid: str, task_id: str,
                        gate: str, phase: str = "clarify") -> Path:
    qdir = ws / ".codenook" / "hitl-queue"
    qdir.mkdir(parents=True, exist_ok=True)
    p = qdir / f"{eid}.json"
    p.write_text(json.dumps({
        "id": eid,
        "task_id": task_id,
        "plugin": "writing",
        "gate": gate,
        "created_at": "2026-04-21T00:00:00Z",
        "context_path": "",
        "decision": None,
        "decided_at": None,
        "reviewer": None,
        "comment": None,
        "prompt": "approve?",
    }), encoding="utf-8")
    return p


def _run(ws: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(ws / ".codenook" / "bin" / "codenook"), *args],
        cwd=str(ws), capture_output=True, text=True,
    )


class TestCmdDecideResolution(unittest.TestCase):

    def test_decide_via_gate_id_fallback(self):
        """`--phase <gate_id>` should resolve when phase-id lookup misses."""
        ws = _bootstrap_workspace()
        try:
            # Create the task so its dir exists.
            cp = _run(ws, "task", "new",
                      "--title", "t1", "--plugin", "writing",
                      "--accept-defaults")
            self.assertEqual(cp.returncode, 0, cp.stderr)
            task_id = cp.stdout.strip()
            self.assertTrue(task_id.startswith("T-001"))

            # Plant a pending HITL gate whose `gate` id differs from the
            # phase id (mimics the writing/development pattern).
            _write_pending_gate(ws, eid=f"{task_id}-rsign",
                                task_id=task_id,
                                gate="requirements_signoff",
                                phase="clarify")

            # Conductor passes --phase requirements_signoff (gate id).
            cp = _run(ws, "decide",
                      "--task", task_id,
                      "--phase", "requirements_signoff",
                      "--decision", "approve")
            self.assertEqual(cp.returncode, 0,
                             f"stderr={cp.stderr}\nstdout={cp.stdout}")

            # Verify the entry was actually decided.
            entry_path = (ws / ".codenook" / "hitl-queue"
                          / f"{task_id}-rsign.json")
            entry = json.loads(entry_path.read_text(encoding="utf-8"))
            self.assertEqual(entry["decision"], "approve")
        finally:
            import shutil
            shutil.rmtree(ws, ignore_errors=True)

    def test_decide_unknown_phase_returns_helpful_error(self):
        """Decide with no matching gate must list pending gates in stderr."""
        ws = _bootstrap_workspace()
        try:
            cp = _run(ws, "task", "new",
                      "--title", "t2", "--plugin", "writing",
                      "--accept-defaults")
            task_id = cp.stdout.strip()
            _write_pending_gate(ws, eid=f"{task_id}-g",
                                task_id=task_id, gate="some_gate")

            cp = _run(ws, "decide",
                      "--task", task_id,
                      "--phase", "totally_made_up",
                      "--decision", "approve")
            self.assertNotEqual(cp.returncode, 0)
            self.assertIn("some_gate", cp.stderr)
        finally:
            import shutil
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
