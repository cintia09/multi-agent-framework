"""v0.19 — per-task execution_mode tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CORE = REPO / "skills" / "codenook-core"
sys.path.insert(0, str(CORE))

from _lib import exec_mode  # noqa: E402
from _lib.cli import cmd_task, cmd_tick  # noqa: E402
from _lib.cli.config import CodenookContext  # noqa: E402


def _ws(tmp_path: Path, plugin: str = "demo") -> Path:
    (tmp_path / ".codenook" / "tasks").mkdir(parents=True)
    (tmp_path / ".codenook" / "plugins" / plugin).mkdir(parents=True)
    return tmp_path


def _ctx(ws: Path) -> CodenookContext:
    return CodenookContext(
        workspace=ws,
        state_file=ws / ".codenook" / "state.json",
        state={"installed_plugins": [{"id": "demo"}]},
        kernel_dir=CORE / "skills" / "builtin",
    )


# ── resolver ────────────────────────────────────────────────────────────

def test_resolve_default_when_field_absent():
    assert exec_mode.resolve_exec_mode({}) == "sub-agent"


def test_resolve_explicit_inline():
    assert exec_mode.resolve_exec_mode({"execution_mode": "inline"}) == "inline"


def test_resolve_explicit_sub_agent():
    assert exec_mode.resolve_exec_mode({"execution_mode": "sub-agent"}) == "sub-agent"


def test_resolve_unknown_value_falls_back_to_default():
    assert exec_mode.resolve_exec_mode({"execution_mode": "bogus"}) == "sub-agent"
    assert exec_mode.resolve_exec_mode({"execution_mode": ""}) == "sub-agent"
    assert exec_mode.resolve_exec_mode({"execution_mode": None}) == "sub-agent"


def test_resolve_handles_non_dict():
    assert exec_mode.resolve_exec_mode(None) == "sub-agent"  # type: ignore[arg-type]


# ── CLI: task new --exec ────────────────────────────────────────────────

def test_task_new_default_omits_execution_mode(tmp_path: Path):
    ws = _ws(tmp_path)
    rc = cmd_task.run(_ctx(ws), [
        "new", "--title", "T", "--accept-defaults", "--id", "T-200"])
    assert rc == 0
    state = json.loads(
        (ws / ".codenook" / "tasks" / "T-200" / "state.json").read_text())
    assert "execution_mode" not in state


def test_task_new_exec_inline_writes_field(tmp_path: Path):
    ws = _ws(tmp_path)
    rc = cmd_task.run(_ctx(ws), [
        "new", "--title", "T", "--accept-defaults",
        "--id", "T-201", "--exec", "inline"])
    assert rc == 0
    state = json.loads(
        (ws / ".codenook" / "tasks" / "T-201" / "state.json").read_text())
    assert state["execution_mode"] == "inline"


def test_task_new_exec_sub_agent_writes_field(tmp_path: Path):
    ws = _ws(tmp_path)
    rc = cmd_task.run(_ctx(ws), [
        "new", "--title", "T", "--accept-defaults",
        "--id", "T-202", "--exec", "sub-agent"])
    assert rc == 0
    state = json.loads(
        (ws / ".codenook" / "tasks" / "T-202" / "state.json").read_text())
    assert state["execution_mode"] == "sub-agent"


def test_task_new_invalid_exec_rejected(tmp_path: Path):
    ws = _ws(tmp_path)
    rc = cmd_task.run(_ctx(ws), [
        "new", "--title", "T", "--accept-defaults",
        "--id", "T-203", "--exec", "remote-agent"])
    assert rc == 2


def test_task_new_help_mentions_exec(capsys):
    rc = cmd_task.run(_ctx(Path.cwd()), ["new", "--help"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "--exec" in out


# ── CLI: task set-exec ──────────────────────────────────────────────────

def test_task_set_exec_flips_field(tmp_path: Path):
    ws = _ws(tmp_path)
    cmd_task.run(_ctx(ws), [
        "new", "--title", "T", "--accept-defaults", "--id", "T-210"])
    sf = ws / ".codenook" / "tasks" / "T-210" / "state.json"
    assert "execution_mode" not in json.loads(sf.read_text())

    rc = cmd_task.run(_ctx(ws), [
        "set-exec", "--task", "T-210", "--mode", "inline"])
    assert rc == 0
    assert json.loads(sf.read_text())["execution_mode"] == "inline"

    rc = cmd_task.run(_ctx(ws), [
        "set-exec", "--task", "T-210", "--mode", "sub-agent"])
    assert rc == 0
    assert json.loads(sf.read_text())["execution_mode"] == "sub-agent"


def test_task_set_exec_requires_mode(tmp_path: Path):
    ws = _ws(tmp_path)
    cmd_task.run(_ctx(ws), [
        "new", "--title", "T", "--accept-defaults", "--id", "T-211"])
    rc = cmd_task.run(_ctx(ws), ["set-exec", "--task", "T-211"])
    assert rc == 2


def test_task_set_exec_rejects_invalid_mode(tmp_path: Path):
    ws = _ws(tmp_path)
    cmd_task.run(_ctx(ws), [
        "new", "--title", "T", "--accept-defaults", "--id", "T-212"])
    rc = cmd_task.run(_ctx(ws), [
        "set-exec", "--task", "T-212", "--mode", "remote-agent"])
    assert rc == 2


def test_task_set_exec_unknown_task(tmp_path: Path):
    ws = _ws(tmp_path)
    rc = cmd_task.run(_ctx(ws), [
        "set-exec", "--task", "T-999", "--mode", "inline"])
    assert rc == 1


def test_task_set_exec_help(capsys):
    rc = cmd_task.run(_ctx(Path.cwd()), ["set-exec", "--help"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "--mode" in out and "inline" in out and "sub-agent" in out


# ── tick envelope action ───────────────────────────────────────────────

def _make_in_flight_state(
    task: str, *, execution_mode: str | None = None,
    model_override: str | None = None,
) -> dict:
    state: dict = {
        "schema_version": 1,
        "task_id": task,
        "plugin": "demo",
        "phase": "design",
        "iteration": 0,
        "max_iterations": 3,
        "status": "in_progress",
        "history": [],
        "in_flight_agent": {
            "agent_id": "ag1",
            "role": "designer",
            "dispatched_at": "2025-01-01T00:00:00Z",
            "expected_output": f".codenook/tasks/{task}/outputs/phase-1-designer.md",
        },
    }
    if execution_mode is not None:
        state["execution_mode"] = execution_mode
    if model_override is not None:
        state["model_override"] = model_override
    return state


def _augment(ws: Path, task: str, state: dict) -> dict:
    tdir = ws / ".codenook" / "tasks" / task
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    ctx = CodenookContext(
        workspace=ws,
        state_file=tdir / "state.json",
        state={},
        kernel_dir=CORE / "skills" / "builtin",
    )
    tick_out = json.dumps(
        {"status": "advanced", "next_action": "dispatched designer"})
    return json.loads(cmd_tick._augment_envelope(ctx, task, tick_out))


def test_envelope_default_mode_keeps_phase_prompt_action(tmp_path: Path):
    ws = _ws(tmp_path)
    summary = _augment(ws, "T-300", _make_in_flight_state("T-300"))
    env = summary["envelope"]
    assert env["action"] == "phase_prompt"
    assert "execution_mode" not in env
    assert "role_path" not in env
    assert "output_path" not in env


def test_envelope_sub_agent_explicit_keeps_phase_prompt(tmp_path: Path):
    ws = _ws(tmp_path)
    summary = _augment(
        ws, "T-301", _make_in_flight_state("T-301", execution_mode="sub-agent"))
    assert summary["envelope"]["action"] == "phase_prompt"


def test_envelope_inline_mode_emits_inline_dispatch(tmp_path: Path):
    ws = _ws(tmp_path)
    summary = _augment(
        ws, "T-302", _make_in_flight_state("T-302", execution_mode="inline"))
    env = summary["envelope"]
    assert env["action"] == "inline_dispatch"
    assert env["execution_mode"] == "inline"
    # Required path fields for inline operation
    assert env["role_path"].endswith("/roles/designer.md")
    assert env["output_path"].endswith("/outputs/phase-1-designer.md")
    # Also keeps the canonical fields
    assert env["system_prompt_path"] == env["role_path"]
    assert env["reply_path"] == env["output_path"]
    assert env["prompt_path"].endswith("phase-1-designer.md")
    assert env["task_id"] == "T-302"
    assert env["plugin"] == "demo"
    assert env["phase"] == "design"
    assert env["role"] == "designer"


def test_envelope_inline_carries_resolved_model(tmp_path: Path):
    ws = _ws(tmp_path)
    summary = _augment(
        ws, "T-303",
        _make_in_flight_state(
            "T-303", execution_mode="inline", model_override="opus-test"),
    )
    env = summary["envelope"]
    assert env["action"] == "inline_dispatch"
    assert env["model"] == "opus-test"


def test_envelope_inline_omits_model_when_unresolved(tmp_path: Path):
    ws = _ws(tmp_path)
    summary = _augment(
        ws, "T-304", _make_in_flight_state("T-304", execution_mode="inline"))
    assert "model" not in summary["envelope"]


def test_inline_then_output_written_then_next_tick_advances(tmp_path: Path):
    """Simulate: conductor receives inline_dispatch envelope, writes the
    output_path itself, then the next augment-after-tick has a clean state
    (no synthetic in-flight). We don't drive the full _tick.py here — that
    is exhaustively covered in the existing tick test suite — but we verify
    the envelope is well-formed and the output path is writable & readable.
    """
    ws = _ws(tmp_path)
    state = _make_in_flight_state("T-305", execution_mode="inline")
    summary = _augment(ws, "T-305", state)
    env = summary["envelope"]
    assert env["action"] == "inline_dispatch"

    out_rel = env["output_path"]
    out_abs = ws / out_rel
    out_abs.parent.mkdir(parents=True, exist_ok=True)
    out_abs.write_text(
        "---\nrole: designer\n---\n# Designer output (inline)\n",
        encoding="utf-8",
    )
    # Sanity: file exists and is non-empty — this is the contract the next
    # tick relies on to advance past the in-flight phase.
    assert out_abs.is_file()
    assert out_abs.stat().st_size > 0
