"""v0.29.3 — plugin entry-question fields are persistable + readable.

Covers the three blocks from the v0.29.3 P0 bug:

* Block 1 — `task-state.schema.json` must accept arbitrary keys
  inside `entry_answers`, while still rejecting unknown top-level
  fields.
* Block 2 — `codenook task set --field <plugin_field>` must
  auto-route plugin-defined entry-question fields under
  `state["entry_answers"]` instead of failing with "not writable".
* Compat  — `check_entry_questions` continues to honour fields
  written at the top level of state for back-compat.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

import _tick

from _cmd_task_helpers import KERNEL, make_ctx, write_state

# `_lib.cli.cmd_task` is importable thanks to _cmd_task_helpers
# putting KERNEL on sys.path.
from _lib.cli import cmd_task as ct  # type: ignore  # noqa: E402

# Vendored validator (shipped in skills/builtin/_lib).
sys.path.insert(0, str(KERNEL / "skills" / "builtin" / "_lib"))
import jsonschema_lite as jsl  # type: ignore  # noqa: E402


SCHEMA_PATH = KERNEL / "schemas" / "task-state.schema.json"


# ── unit: check_entry_questions reads entry_answers ───────────────────
def _write_eq(workspace: Path, plugin: str, body: str) -> None:
    pdir = workspace / ".codenook" / "plugins" / plugin
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "entry-questions.yaml").write_text(body)


def test_check_entry_questions_reads_entry_answers(workspace: Path):
    plugin = "prnook"
    _write_eq(workspace, plugin,
              "collect:\n  required: [issue_id, investigation_scope]\n")
    state = {"plugin": plugin,
             "entry_answers": {"issue_id": "PR000001",
                               "investigation_scope": "smoke"}}
    assert _tick.check_entry_questions(workspace, plugin, "collect", state) == []


def test_check_entry_questions_missing_when_blank(workspace: Path):
    plugin = "prnook"
    _write_eq(workspace, plugin,
              "collect:\n  required: [issue_id, investigation_scope]\n")
    state = {"plugin": plugin,
             "entry_answers": {"issue_id": "", "investigation_scope": None}}
    missing = _tick.check_entry_questions(workspace, plugin, "collect", state)
    assert set(missing) == {"issue_id", "investigation_scope"}


def test_check_entry_questions_top_level_back_compat(workspace: Path):
    """Pre-v0.29.3 callers may have written required fields at the
    top level of state; those must still satisfy the gate."""
    plugin = "prnook"
    _write_eq(workspace, plugin, "collect:\n  required: [issue_id]\n")
    state = {"plugin": plugin, "issue_id": "PR000002"}
    assert _tick.check_entry_questions(workspace, plugin, "collect", state) == []


def test_check_entry_questions_prefers_entry_answers_over_top_level(workspace: Path):
    plugin = "prnook"
    _write_eq(workspace, plugin, "collect:\n  required: [issue_id]\n")
    state = {"plugin": plugin, "issue_id": "",
             "entry_answers": {"issue_id": "PR000003"}}
    assert _tick.check_entry_questions(workspace, plugin, "collect", state) == []


# ── schema: entry_answers accepts arbitrary keys ──────────────────────
def _base_state(**extra) -> dict:
    s = {
        "schema_version": 1,
        "task_id": "T-001",
        "plugin": "prnook",
        "phase": "collect",
        "iteration": 0,
        "max_iterations": 3,
        "status": "pending",
        "history": [],
    }
    s.update(extra)
    return s


def test_schema_accepts_entry_answers_arbitrary_keys():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    state = _base_state(entry_answers={
        "issue_id": "PR000001",
        "investigation_scope": "smoke",
        "any_future_plugin_field": "free-form",
    })
    jsl.validate(state, schema)  # must not raise


def test_schema_still_rejects_unknown_top_level_field():
    """Top-level `additionalProperties: false` must be preserved —
    only the nested `entry_answers` map is unrestricted."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    state = _base_state(issue_id="PR000001")  # unknown top-level
    with pytest.raises(jsl.ValidationError):
        jsl.validate(state, schema)


# ── cmd_task: task set auto-routes plugin entry-question fields ───────
def _seed_task(workspace: Path, plugin: str, task_id: str = "T-001-eqt") -> Path:
    """Create a minimal but schema-valid task state.json."""
    state = _base_state(task_id=task_id, plugin=plugin, status="pending")
    return write_state(workspace, task_id, state)


def _eq_workspace(workspace: Path, plugin: str = "prnook") -> str:
    _write_eq(workspace, plugin,
              "collect:\n  required: [issue_id, investigation_scope]\n"
              "  questions:\n"
              "    issue_id:\n      description: PR or issue id\n")
    return _seed_task(workspace, plugin).parent.name


def test_task_set_routes_plugin_field_to_entry_answers(workspace: Path):
    plugin = "prnook"
    tid = _eq_workspace(workspace, plugin)
    ctx = make_ctx(workspace)

    out = io.StringIO()
    with redirect_stdout(out):
        rc = ct._task_set(ctx, ["--task", tid,
                                "--field", "issue_id",
                                "--value", "PR000042"])
    assert rc == 0
    payload = json.loads(out.getvalue())
    assert payload["field"] == "issue_id"
    assert payload["value"] == "PR000042"
    assert payload["stored_under"] == "entry_answers.issue_id"

    sf = workspace / ".codenook" / "tasks" / tid / "state.json"
    state = json.loads(sf.read_text(encoding="utf-8"))
    assert state["entry_answers"]["issue_id"] == "PR000042"

    # And the gate now passes.
    missing = _tick.check_entry_questions(workspace, plugin, "collect", state)
    assert missing == ["investigation_scope"]


def test_task_set_routes_questions_only_field(workspace: Path):
    """A field declared only under `questions:` (not `required:`)
    should also be auto-routed — plugins may use questions for
    optional answers that the next role still wants in state."""
    plugin = "prnook"
    _write_eq(workspace, plugin,
              "collect:\n  required: [issue_id]\n"
              "  questions:\n"
              "    optional_hint:\n      description: free text\n")
    tid = _seed_task(workspace, plugin, "T-002-eqt").parent.name
    ctx = make_ctx(workspace)

    with redirect_stdout(io.StringIO()):
        rc = ct._task_set(ctx, ["--task", tid,
                                "--field", "optional_hint",
                                "--value", "fyi"])
    assert rc == 0
    state = json.loads(
        (workspace / ".codenook" / "tasks" / tid / "state.json")
        .read_text(encoding="utf-8"))
    assert state["entry_answers"]["optional_hint"] == "fyi"


def test_task_set_unknown_field_still_rejected(workspace: Path):
    plugin = "prnook"
    tid = _eq_workspace(workspace, plugin)
    ctx = make_ctx(workspace)

    err = io.StringIO()
    with redirect_stderr(err), redirect_stdout(io.StringIO()):
        rc = ct._task_set(ctx, ["--task", tid,
                                "--field", "totally_bogus",
                                "--value", "x"])
    assert rc == 2
    assert "not writable" in err.getvalue()


def test_task_set_well_known_field_still_lands_top_level(workspace: Path):
    """A WRITABLE field (e.g. `priority`) must still be written to the
    top level of state, NOT into entry_answers."""
    plugin = "prnook"
    tid = _eq_workspace(workspace, plugin)
    ctx = make_ctx(workspace)

    with redirect_stdout(io.StringIO()):
        rc = ct._task_set(ctx, ["--task", tid,
                                "--field", "priority", "--value", "P0"])
    assert rc == 0
    state = json.loads(
        (workspace / ".codenook" / "tasks" / tid / "state.json")
        .read_text(encoding="utf-8"))
    assert state["priority"] == "P0"
    assert "priority" not in (state.get("entry_answers") or {})
