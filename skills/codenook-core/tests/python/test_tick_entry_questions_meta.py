"""E2E-006 — entry-questions blocked response carries allowed_values + recovery."""
from __future__ import annotations

from pathlib import Path

import _tick


def test_dual_mode_enum_via_schema_fallback(workspace: Path):
    plugin = "development"
    (workspace / ".codenook" / "plugins" / plugin).mkdir(parents=True, exist_ok=True)
    (workspace / ".codenook" / "plugins" / plugin / "entry-questions.yaml").write_text(
        "clarify:\n  required: [dual_mode]\n"
    )
    resp = _tick._missing_field_response(workspace, plugin, "clarify", ["dual_mode"])
    assert resp["status"] == "blocked"
    assert resp["missing"] == ["dual_mode"]
    assert resp["allowed_values"]["dual_mode"] == ["serial", "parallel"]
    assert "recovery" in resp
    assert "dual_mode" in resp["recovery"]
    assert "serial" in resp["recovery"]


def test_explicit_allowed_values_in_questions(workspace: Path):
    plugin = "development"
    (workspace / ".codenook" / "plugins" / plugin).mkdir(parents=True, exist_ok=True)
    (workspace / ".codenook" / "plugins" / plugin / "entry-questions.yaml").write_text(
        "design:\n"
        "  required: [strategy]\n"
        "  questions:\n"
        "    strategy:\n"
        "      allowed_values: [a, b, c]\n"
    )
    meta = _tick.entry_question_meta(workspace, plugin, "design", ["strategy"])
    assert meta["strategy"]["allowed_values"] == ["a", "b", "c"]
