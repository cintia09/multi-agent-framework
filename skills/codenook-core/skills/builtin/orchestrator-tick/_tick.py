#!/usr/bin/env python3
"""orchestrator-tick/_tick.py — full M4 state-machine algorithm.

Implements implementation-v6.md §3.3 verbatim:
  read state.json → decide → execute one step → persist → return summary.

Two-mode dispatch
-----------------
  * M4 mode: state.json contains `plugin` (and the schema implied by
    M4.2). Full algorithm runs, reading phases.yaml + transitions.yaml
    + entry-questions.yaml from .codenook/plugins/<plugin>/ and writing
    queue/, hitl-queue/, history/dispatch.jsonl entries.
  * Legacy mode (no state.plugin): the original M1 stub behaviour
    (preflight + iteration++ + tick_log) is preserved so the M1 bats
    suite keeps passing without churn. See `_legacy_tick`.

Real Task-tool dispatch is M5+: dispatch_agent only writes a marker
file under outputs/<phase-N>-<role>.dispatched containing the rendered
manifest. The agent_id returned is deterministic
(`ag_<task>_<phase_idx>_<n>`) so test fixtures can reason about it.
The kernel that actually invokes Task() lives in main session and is
out of M4 scope — see SKILL.md "M4 scope" section.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from atomic import atomic_write_json  # noqa: E402


def _assert_under(p: Path, root: Path) -> Path:
    """Resolve `p` and ensure it stays under `root`. Exits 2 on escape (S3)."""
    try:
        rp = p.resolve()
        root_r = root.resolve()
        rp.relative_to(root_r)
    except (ValueError, OSError):
        print(f"_tick.py: path escapes task root: {p}", file=sys.stderr)
        sys.exit(2)
    return rp


def task_root(workspace: Path, task_id: str) -> Path:
    return workspace / ".codenook" / "tasks" / task_id


# ── Fix #5: task_id format guard (S4) ───────────────────────────────────
_TASK_ID_RE = re.compile(r"^T-[A-Za-z0-9_-]+$")


def _check_task_id(tid: str) -> None:
    if not isinstance(tid, str) or not _TASK_ID_RE.match(tid):
        print(f"_tick.py: invalid task_id format: {tid!r}", file=sys.stderr)
        sys.exit(2)

try:
    import yaml  # PyYAML
except ImportError as e:  # pragma: no cover
    print(f"_tick.py: PyYAML required ({e})", file=sys.stderr)
    sys.exit(2)


# ── small utilities ──────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_summary(payload: dict) -> None:
    """Write the ≤500-byte summary to stdout (json) for the caller."""
    s = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(s.encode("utf-8")) > 500:
        # Trim message_for_user/next_action progressively until fits.
        for k in ("message_for_user", "next_action"):
            if k in payload and isinstance(payload[k], str):
                payload[k] = payload[k][:80]
                s = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if len(s.encode("utf-8")) <= 500:
                    break
    print(s)


def read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ── frontmatter / verdict ────────────────────────────────────────────────
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def output_ready(workspace: Path, task_id: str, expected_output: str) -> bool:
    """File exists AND has frontmatter `verdict: <v>` matching enum."""
    root = task_root(workspace, task_id)
    p = _assert_under(root / expected_output, root)
    if not p.is_file():
        return False
    return read_verdict(workspace, task_id, expected_output) is not None


def read_verdict(workspace: Path, task_id: str, expected_output: str) -> str | None:
    root = task_root(workspace, task_id)
    p = _assert_under(root / expected_output, root)
    text = p.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    v = fm.get("verdict")
    if v in ("ok", "needs_revision", "blocked"):
        return v
    return None


# ── phase / transition lookup ────────────────────────────────────────────
def find_phase(phases: list[dict], pid: str) -> dict | None:
    for ph in phases:
        if ph.get("id") == pid:
            return ph
    return None


def lookup_transition(trans: dict, cur_id: str, verdict: str) -> str | None:
    table = trans.get("transitions", {}) or trans  # tolerant of either layout
    cur = table.get(cur_id, {}) or {}
    nxt = cur.get(verdict)
    return nxt


# ── manifest + audit + dispatch (stubbed for M4) ─────────────────────────
def render_manifest(state: dict, phase: dict) -> str:
    """Compose the ≤500-byte dispatch payload (kept tiny — full role
    template rendering is M5+)."""
    payload = {
        "execute": "agent",
        "task": state["task_id"],
        "plugin": state["plugin"],
        "phase": phase.get("id"),
        "role": phase.get("role"),
        "produces": phase.get("produces"),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def append_dispatch_log(workspace: Path, role: str, payload: str) -> None:
    audit_sh = Path(__file__).resolve().parent.parent / "dispatch-audit" / "emit.sh"
    if audit_sh.is_file():
        subprocess.run(
            [str(audit_sh), "--role", role, "--payload", payload,
             "--workspace", str(workspace)],
            check=False, capture_output=True,
        )


def dispatch_agent(workspace: Path, state: dict, phase: dict, n: int = 1) -> str:
    """Stub: write marker file with manifest + return deterministic agent_id.
    Real Task() invocation is M5+ kernel work."""
    pid = phase.get("id", "?")
    role = phase.get("role", "?")
    agent_id = f"ag_{state['task_id']}_{pid}_{n}"
    root = task_root(workspace, state["task_id"])
    marker = _assert_under(
        root / "outputs" / f"phase-{pid}-{role}.dispatched", root
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(render_manifest(state, phase) + "\n", encoding="utf-8")
    return agent_id


def dispatch_distiller(workspace: Path, task_id: str) -> None:
    pdir = workspace / ".codenook" / "memory" / "_pending"
    pdir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(pdir / f"{task_id}.json"),
                      {"task_id": task_id, "queued_at": now_iso()})


# ── post_validate (skip with _warning if missing) ────────────────────────
def run_post_validate(workspace: Path, plugin: str, script_rel: str,
                      state: dict) -> None:
    sp = workspace / ".codenook" / "plugins" / plugin / script_rel
    if not sp.is_file():
        last = state["history"][-1] if state["history"] else None
        if last is not None:
            last["_warning"] = f"post_validate script missing: {script_rel}"
        return
    subprocess.run([str(sp), state["task_id"]], cwd=str(workspace),
                   check=False, capture_output=True)


# ── HITL ────────────────────────────────────────────────────────────────
def hitl_required(state: dict, phase: dict, cfg: dict) -> bool:
    if phase.get("gate"):
        return True
    return bool(cfg.get("hitl_required", {}).get(phase.get("id")))


def write_hitl_entry(workspace: Path, state: dict, phase: dict,
                     verdict: str | None = None) -> Path:
    gate = phase.get("gate") or phase.get("id")
    qdir = workspace / ".codenook" / "hitl-queue"
    qdir.mkdir(parents=True, exist_ok=True)
    entry_id = f"{state['task_id']}-{gate}"
    path = qdir / f"{entry_id}.json"
    entry = {
        "id": entry_id,
        "task_id": state["task_id"],
        "plugin": state["plugin"],
        "gate": gate,
        "created_at": now_iso(),
        "context_path": f".codenook/tasks/{state['task_id']}/{phase.get('produces','')}",
        "decision": None,
        "decided_at": None,
        "reviewer": None,
        "comment": None,
        "verdict_at_gate": verdict,
    }
    atomic_write_json(str(path), entry)
    return path


# ── HITL decision consumer ──────────────────────────────────────────────
def hitl_check_resolved(ws: Path, state: dict, cur_phase: dict
                        ) -> tuple[str, str | None]:
    """Return (status, stored_verdict). Status is one of:
       "pending", "approve", "reject", "needs_changes", "not_found"."""
    gate = cur_phase.get("gate") or cur_phase.get("id")
    eid = f"{state['task_id']}-{gate}"
    p = ws / ".codenook" / "hitl-queue" / f"{eid}.json"
    if not p.is_file():
        return ("not_found", None)
    try:
        entry = read_json(p)
    except Exception:
        return ("not_found", None)
    decision = entry.get("decision")
    if decision in (None, ""):
        return ("pending", None)
    if decision == "approve":
        return ("approve", entry.get("verdict_at_gate"))
    if decision == "reject":
        return ("reject", None)
    if decision == "needs_changes":
        return ("needs_changes", None)
    return ("pending", None)


def hitl_consume_entry(ws: Path, state: dict, cur_phase: dict) -> None:
    gate = cur_phase.get("gate") or cur_phase.get("id")
    eid = f"{state['task_id']}-{gate}"
    src = ws / ".codenook" / "hitl-queue" / f"{eid}.json"
    if not src.is_file():
        return
    dst_dir = ws / ".codenook" / "hitl-queue" / "_consumed"
    dst_dir.mkdir(parents=True, exist_ok=True)
    os.replace(str(src), str(dst_dir / f"{eid}.json"))


# ── entry-questions ────────────────────────────────────────────────────
def check_entry_questions(workspace: Path, plugin: str, phase_id: str,
                          state: dict) -> list[str]:
    eq = read_yaml(workspace / ".codenook" / "plugins" / plugin / "entry-questions.yaml") or {}
    spec = eq.get(phase_id) or {}
    required = spec.get("required") or []
    missing = []
    for key in required:
        if key not in state or state.get(key) in (None, "", [], {}):
            missing.append(key)
    return missing


# ── seed_subtasks (fanout) ──────────────────────────────────────────────
def seed_subtasks(workspace: Path, state: dict, phase: dict) -> dict:
    parent = state["task_id"]
    _check_task_id(parent)
    units = state.get("subtasks") or [f"u{i+1}" for i in range(2)]
    queue_dir = workspace / ".codenook" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for i, _u in enumerate(units, 1):
        cid = f"{parent}-c{i}"
        _check_task_id(cid)
        cdir = workspace / ".codenook" / "tasks" / cid
        (cdir / "outputs").mkdir(parents=True, exist_ok=True)
        child_state = {
            "schema_version": 1,
            "task_id": cid,
            "plugin": state["plugin"],
            "phase": None,
            "iteration": 0,
            "max_iterations": state.get("max_iterations", 3),
            "dual_mode": state.get("dual_mode", "serial"),
            "status": "in_progress",
            "depends_on": [parent],
            "config_overrides": state.get("config_overrides", {}),
            "history": [],
        }
        atomic_write_json(str(cdir / "state.json"), child_state)
        atomic_write_json(str(queue_dir / f"{cid}.json"), {
            "task_id": cid,
            "plugin": state["plugin"],
            "priority": 5,
            "ready_at": now_iso(),
            "blocked_by": [],
            "next_action": f"dispatch_role:{phase.get('role','')}",
        })
        created.append(cid)
    return {
        "status": "advanced",
        "next_action": f"seeded {len(created)} subtasks",
    }


# ── dispatch parallel ────────────────────────────────────────────────────
def dispatch_parallel(workspace: Path, state: dict, phase: dict, cfg: dict) -> dict:
    n = int(cfg.get("parallel_n", 2))
    agent_ids = [dispatch_agent(workspace, state, phase, i + 1) for i in range(n)]
    state["in_flight_agent"] = {
        "agent_id": agent_ids,
        "role": phase.get("role"),
        "dispatched_at": now_iso(),
        "expected_output": phase.get("produces", ""),
    }
    state["phase"] = phase.get("id")
    state["phase_started_at"] = now_iso()
    payload = render_manifest(state, phase)
    append_dispatch_log(workspace, phase.get("role", "?"), payload)
    return {"status": "advanced",
            "next_action": f"dispatched {n} parallel {phase.get('role')}"}


# ── dispatch_role (single-role default branch) ───────────────────────────
def dispatch_role(workspace: Path, state: dict, phase: dict, cfg: dict) -> dict:
    missing = check_entry_questions(workspace, state["plugin"], phase.get("id"), state)
    if missing:
        return {
            "status": "blocked",
            "next_action": f"missing: {','.join(missing)}",
            "message_for_user": f"Please answer first: {', '.join(missing)}",
        }
    if phase.get("allows_fanout") and state.get("decomposed"):
        return seed_subtasks(workspace, state, phase)
    if phase.get("dual_mode_compatible") and (
        state.get("dual_mode") == "parallel"
        or cfg.get("dual_mode") == "parallel"
    ):
        return dispatch_parallel(workspace, state, phase, cfg)

    payload = render_manifest(state, phase)
    agent_id = dispatch_agent(workspace, state, phase, 1)
    state["in_flight_agent"] = {
        "agent_id": agent_id,
        "role": phase.get("role"),
        "dispatched_at": now_iso(),
        "expected_output": phase.get("produces", ""),
    }
    state["phase"] = phase.get("id")
    state["phase_started_at"] = now_iso()
    append_dispatch_log(workspace, phase.get("role", "?"), payload)
    return {
        "status": "advanced",
        "next_action": f"dispatched {phase.get('role')}",
        "dispatched_agent_id": agent_id,
    }


# ── tick (M4 algorithm) ─────────────────────────────────────────────────
def tick(workspace: Path, state_file: Path) -> tuple[dict, dict]:
    state = read_json(state_file)
    plugin = state["plugin"]
    pdir = workspace / ".codenook" / "plugins" / plugin
    phases_doc = read_yaml(pdir / "phases.yaml")
    trans_doc = read_yaml(pdir / "transitions.yaml")
    phases = phases_doc.get("phases", [])
    cfg = state.get("config_overrides", {})  # M5 will full-merge; M4 uses task-only

    state["last_tick_ts"] = now_iso()
    status_in = state.get("status")

    # ── 0. terminal / waiting short-circuit ──
    if status_in in ("done", "cancelled", "error"):
        del state["last_tick_ts"]
        return state, {"status": status_in, "next_action": "noop"}

    if status_in == "waiting":
        cur_w = find_phase(phases, state.get("phase")) if state.get("phase") else None
        decided = False
        if cur_w is not None and hitl_required(state, cur_w, cfg):
            res, _ = hitl_check_resolved(workspace, state, cur_w)
            if res in ("approve", "reject", "needs_changes"):
                decided = True
        if not decided:
            del state["last_tick_ts"]
            return state, {"status": "waiting", "next_action": "noop"}
        # else: fall through to step 3.5 via main flow.

    # ── 1. phase=null → dispatch first ──
    if state.get("phase") in (None, ""):
        if not phases:
            return state, {"status": "error", "next_action": "no phases defined"}
        first = phases[0]
        pre_check = check_entry_questions(workspace, plugin, first.get("id"), state)
        if pre_check:
            return state, {
                "status": "blocked",
                "next_action": f"missing: {','.join(pre_check)}",
                "message_for_user": f"Please answer first: {', '.join(pre_check)}",
            }
        result = dispatch_role(workspace, state, first, cfg)
        return state, result

    cur = find_phase(phases, state["phase"])
    if cur is None:
        return state, {"status": "error", "next_action": f"unknown phase {state['phase']}"}

    # ── 2. in_flight present ──
    in_flight = state.get("in_flight_agent")
    just_consumed_verdict: str | None = None
    if in_flight:
        expected = in_flight.get("expected_output", "")
        if not output_ready(workspace, state["task_id"], expected):
            del state["last_tick_ts"]
            return state, {
                "status": "waiting",
                "next_action": f"awaiting {in_flight.get('role')}",
            }
        just_consumed_verdict = read_verdict(workspace, state["task_id"], expected) or "ok"
        state["history"].append(
            {"ts": now_iso(), "phase": cur.get("id"), "verdict": just_consumed_verdict}
        )
        state["in_flight_agent"] = None
        if cur.get("post_validate"):
            run_post_validate(workspace, plugin, cur["post_validate"], state)
        # fall through to step 3.5

    # ── 3.5. HITL gate consumer ──
    verdict_for_transition = just_consumed_verdict
    if hitl_required(state, cur, cfg):
        resolution, stored = hitl_check_resolved(workspace, state, cur)
        if resolution == "approve":
            verdict_for_transition = stored or just_consumed_verdict or "ok"
            hitl_consume_entry(workspace, state, cur)
            state["status"] = "in_progress"
            state["history"].append(
                {"ts": now_iso(), "phase": cur.get("id"),
                 "_warning": "hitl_approved"}
            )
            # fall through to transition step 5
        elif resolution == "reject":
            state["status"] = "blocked"
            state["history"].append(
                {"ts": now_iso(), "phase": cur.get("id"),
                 "_warning": "hitl_rejected"}
            )
            return state, {"status": "blocked",
                           "next_action": "hitl_rejected"}
        elif resolution == "needs_changes":
            hitl_consume_entry(workspace, state, cur)
            state["iteration"] = state.get("iteration", 0) + 1
            if state["iteration"] > state.get("max_iterations", 0):
                state["status"] = "blocked"
                return state, {"status": "blocked",
                               "next_action": "max_iterations exceeded"}
            state["status"] = "in_progress"
            state["history"].append(
                {"ts": now_iso(), "phase": cur.get("id"),
                 "_warning": "hitl_needs_changes"}
            )
            return state, dispatch_role(workspace, state, cur, cfg)
        else:
            # pending or not_found
            if just_consumed_verdict is not None:
                write_hitl_entry(workspace, state, cur, just_consumed_verdict)
                state["status"] = "waiting"
                return state, {
                    "status": "waiting",
                    "next_action": f"hitl:{cur.get('gate') or cur.get('id')}",
                }
            # waiting + still pending → noop
            del state["last_tick_ts"]
            return state, {"status": "waiting", "next_action": "noop"}

    # ── 5. transition (only when we have a verdict to act on) ──
    if verdict_for_transition is not None:
        nxt = lookup_transition(trans_doc, cur.get("id"), verdict_for_transition)
        if nxt is None:
            return state, {"status": "error",
                           "next_action": f"no transition from {cur.get('id')}/{verdict_for_transition}"}
        if nxt == "complete":
            state["status"] = "done"
            state["phase"] = "complete"
            dispatch_distiller(workspace, state["task_id"])
            return state, {"status": "done", "next_action": "noop"}
        if nxt == cur.get("id"):
            state["iteration"] = state.get("iteration", 0) + 1
            if state["iteration"] > state.get("max_iterations", 0):
                state["status"] = "blocked"
                return state, {"status": "blocked",
                               "next_action": "max_iterations exceeded"}
            return state, dispatch_role(workspace, state, cur, cfg)
        nxt_phase = find_phase(phases, nxt)
        if nxt_phase is None:
            return state, {"status": "error",
                           "next_action": f"transition target unknown: {nxt}"}
        return state, dispatch_role(workspace, state, nxt_phase, cfg)

    # ── 6. recovery (only when status==in_progress + phase set + no in_flight) ──
    if state.get("status") == "in_progress":
        state["history"].append(
            {"ts": now_iso(), "phase": cur.get("id"),
             "_warning": "recover: re-dispatch (no in_flight)"}
        )
        return state, dispatch_role(workspace, state, cur, cfg)

    # Default: nothing to do (e.g., status=blocked + phase set + no in_flight).
    del state["last_tick_ts"]
    return state, {"status": state.get("status", "noop"), "next_action": "noop"}


# ── legacy stub mode (M1) ────────────────────────────────────────────────
def _legacy_tick(workspace: Path, state_file: Path, dry_run: bool,
                 dispatch_cmd: str, task: str) -> int:
    """Original M1 behaviour: preflight + dispatch + iteration++.
    Activated when state.json lacks the M4 `plugin` field."""
    import tempfile

    with state_file.open("r") as f:
        state = json.load(f)

    phase = state.get("phase", "")
    iteration = state.get("iteration", 0)
    total = state.get("total_iterations", 0)
    core_root = _find_core_root()

    if phase == "done":
        print("tick.sh: task at terminal phase 'done'", file=sys.stderr)
        return 3
    if iteration >= total:
        print(f"tick.sh: iteration limit reached ({iteration}/{total})", file=sys.stderr)
        _legacy_log(state, "preflight", "blocked: iteration limit")
        if not dry_run:
            atomic_write_json(str(state_file), state)
        return 1

    preflight = os.path.join(core_root, "skills/builtin/preflight/preflight.sh")
    res = subprocess.run(
        [preflight, "--task", task, "--workspace", str(workspace), "--json"],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        reasons: list[str] = []
        try:
            reasons = json.loads(res.stdout).get("reasons", [])
        except Exception:
            pass
        _legacy_log(state, "preflight",
                    f"blocked: {', '.join(reasons) if reasons else 'failed'}")
        if not dry_run:
            atomic_write_json(str(state_file), state)
        for line in (res.stderr or "").strip().split("\n"):
            if line:
                print(line, file=sys.stderr)
        return 1

    if dry_run:
        print("tick.sh: dry-run mode, not dispatching", file=sys.stderr)
        return 0

    payload = json.dumps({"task": state.get("task_id"), "phase": phase,
                          "iteration": iteration}, ensure_ascii=False)
    if len(payload) > 500:
        payload = payload[:497] + "..."

    audit = os.path.join(core_root, "skills/builtin/dispatch-audit/emit.sh")
    if os.path.exists(audit):
        subprocess.run([audit, "--role", "executor", "--payload", payload,
                        "--workspace", str(workspace)], check=False)

    if dispatch_cmd:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as fp:
            sf = fp.name
        try:
            env = os.environ.copy()
            env["CODENOOK_DISPATCH_PAYLOAD"] = payload
            env["CODENOOK_DISPATCH_SUMMARY"] = sf
            r = subprocess.run([dispatch_cmd], env=env, capture_output=True, text=True)
            ok = r.returncode == 0
        finally:
            if os.path.exists(sf):
                os.unlink(sf)
        if not ok:
            print("tick.sh: dispatch failed", file=sys.stderr)
            _legacy_log(state, "dispatch", "failed")
            atomic_write_json(str(state_file), state)
            return 1

    state["iteration"] = iteration + 1
    _legacy_log(state, "dispatch", "success")
    atomic_write_json(str(state_file), state)
    return 0


def _legacy_log(state: dict, action: str, result: str) -> None:
    state.setdefault("tick_log", []).append(
        {"ts": now_iso(), "action": action, "result": result}
    )


def _find_core_root() -> str:
    cur = os.path.dirname(os.path.abspath(__file__))
    while cur != "/":
        if os.path.exists(os.path.join(cur, "skills", "builtin", "preflight")):
            return cur
        cur = os.path.dirname(cur)
    return os.environ.get("CORE_ROOT", "")


# ── entry point ─────────────────────────────────────────────────────────
def main() -> None:
    task = os.environ["CN_TASK"]
    state_file = Path(os.environ["CN_STATE_FILE"])
    workspace = Path(os.environ["CN_WORKSPACE"])
    dry_run = os.environ.get("CN_DRY_RUN", "0") == "1"
    json_mode = os.environ.get("CN_JSON", "0") == "1"
    dispatch_cmd = os.environ.get("CN_DISPATCH_CMD", "")

    state = read_json(state_file)

    # Mode select.
    if "plugin" not in state:
        sys.exit(_legacy_tick(workspace, state_file, dry_run, dispatch_cmd, task))

    if dry_run:
        # M4 dry-run: don't persist or dispatch; just compute.
        new_state, summary = tick(workspace, state_file)
        if json_mode:
            emit_summary(summary)
        sys.exit(_exit_for(summary))

    prior_state = read_json(state_file)
    new_state, summary = tick(workspace, state_file)
    # Skip persist for pure observers (no progress made):
    waiting_noop = (summary.get("status") == "waiting"
                    and summary.get("next_action", "").startswith("awaiting"))
    inert_noop = (summary.get("next_action") == "noop"
                  and prior_state.get("status") in
                  ("done", "cancelled", "error", "blocked", "waiting"))
    if not (waiting_noop or inert_noop):
        new_state["updated_at"] = now_iso()
        atomic_write_json(str(state_file), new_state)
    if json_mode:
        emit_summary(summary)
    sys.exit(_exit_for(summary))


def _exit_for(summary: dict) -> int:
    s = summary.get("status")
    if s in ("advanced", "done", "waiting"):
        return 0
    if s == "blocked":
        return 1
    if s in ("cancelled", "error"):
        return 1
    return 0


if __name__ == "__main__":
    main()
