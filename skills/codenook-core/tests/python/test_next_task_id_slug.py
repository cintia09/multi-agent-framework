"""Tests for next_task_id slot reservation (v0.25.0).

Covers the coexistence rule from config.py: a slot ``N`` is occupied
when *either* ``T-NNN`` (legacy unsuffixed) *or* ``T-NNN-<slug>``
(v0.23+) exists. Without this both layouts would collide on disk.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

# config.py is at skills/codenook-core/_lib/cli/config.py — import via
# sys.path because the package layout uses implicit relative imports.
import sys
_HERE = Path(__file__).resolve()
_CORE = _HERE.parents[2]
sys.path.insert(0, str(_CORE / "_lib"))

from cli.config import next_task_id, compose_task_id, slugify  # type: ignore  # noqa: E402


def _mk(workspace: Path, name: str) -> None:
    (workspace / ".codenook" / "tasks" / name).mkdir(
        parents=True, exist_ok=True)


class TestNextTaskIdSlugCoexistence(unittest.TestCase):

    def test_empty_workspace_returns_1(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(next_task_id(Path(d)), 1)

    def test_legacy_unsuffixed_occupies_slot(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            _mk(ws, "T-001")
            self.assertEqual(next_task_id(ws), 2)

    def test_slugged_occupies_slot(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            _mk(ws, "T-001-blog-post")
            self.assertEqual(next_task_id(ws), 2)

    def test_cjk_slug_occupies_slot(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            _mk(ws, "T-001-写blog")
            self.assertEqual(next_task_id(ws), 2)

    def test_mixed_layouts_advance_correctly(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            _mk(ws, "T-001")
            _mk(ws, "T-002-写blog")
            _mk(ws, "T-003-make-site")
            self.assertEqual(next_task_id(ws), 4)

    def test_holes_are_filled(self):
        """Slot 2 is missing, so next_task_id returns 2 even when 3 exists."""
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            _mk(ws, "T-001-a")
            _mk(ws, "T-003-c")
            self.assertEqual(next_task_id(ws), 2)

    def test_compose_with_cjk_slug(self):
        self.assertEqual(compose_task_id(1, slugify("写blog")), "T-001-写blog")

    def test_compose_with_empty_slug(self):
        self.assertEqual(compose_task_id(7, ""), "T-007")


if __name__ == "__main__":
    unittest.main()
