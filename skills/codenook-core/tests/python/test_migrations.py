"""Unit tests for `_lib/migrations` (v1 → v2 + walker contract)."""
from __future__ import annotations

import sys
from pathlib import Path

KERNEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KERNEL))

from _lib import migrations  # noqa: E402
from _lib.migrations import v1_to_v2  # noqa: E402


def test_v1_to_v2_fills_missing_priority_and_history():
    src = {"schema_version": 1, "task_id": "T-001-x",
           "plugin": "p", "phase": None, "iteration": 0,
           "max_iterations": 8, "status": "pending"}
    out = v1_to_v2.migrate(src)
    assert out["schema_version"] == 2
    assert out["priority"] == "P2"
    assert out["history"] == []
    # source untouched (we shallow-copy)
    assert "priority" not in src


def test_v1_to_v2_preserves_existing_priority():
    src = {"schema_version": 1, "priority": "P0", "history": [{"ts": "x", "phase": "p"}]}
    out = v1_to_v2.migrate(src)
    assert out["priority"] == "P0"
    assert out["history"] == [{"ts": "x", "phase": "p"}]
    assert out["schema_version"] == 2


def test_v1_to_v2_idempotent():
    src = {"schema_version": 2, "priority": "P1", "history": []}
    out = v1_to_v2.migrate(src)
    assert out == {"schema_version": 2, "priority": "P1", "history": []}


def test_upgrade_walks_chain_and_reports_applied():
    src = {"schema_version": 1, "task_id": "T-x"}
    out, applied = migrations.upgrade(src)
    assert out["schema_version"] == migrations.CURRENT_SCHEMA_VERSION
    assert applied == [1]


def test_upgrade_no_op_on_current():
    src = {"schema_version": migrations.CURRENT_SCHEMA_VERSION}
    out, applied = migrations.upgrade(src)
    assert applied == []
    assert out["schema_version"] == migrations.CURRENT_SCHEMA_VERSION


def test_upgrade_defaults_missing_schema_version_to_one():
    src = {"task_id": "T-y"}
    out, applied = migrations.upgrade(src)
    assert applied == [1]
    assert out["schema_version"] == migrations.CURRENT_SCHEMA_VERSION


def test_upgrade_handles_null_schema_version():
    """Regression: Phase C deep review found int(None) crash when
    state.json contains an explicit ``"schema_version": null``."""
    src = {"schema_version": None, "task_id": "T-x"}
    out, applied = migrations.upgrade(src)
    assert applied == [1]
    assert out["schema_version"] == migrations.CURRENT_SCHEMA_VERSION


def test_upgrade_handles_string_schema_version():
    """Regression: tolerate ``"schema_version": "1"`` (some migrations
    or hand-edits may stringify the int)."""
    src = {"schema_version": "1", "task_id": "T-x"}
    out, applied = migrations.upgrade(src)
    assert applied == [1]
    assert out["schema_version"] == migrations.CURRENT_SCHEMA_VERSION
