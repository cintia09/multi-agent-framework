#!/usr/bin/env python3
"""extractor-batch core — pure-Python port of ``extractor-batch.sh``.

v0.24.0 — kernel-internal callers (orchestrator-tick.after_phase) call
:func:`run` directly so the kernel works on Windows hosts without bash
on PATH. ``extractor-batch.sh`` is preserved for Linux/Mac users who
script against it; it now delegates to this helper.

Behaviour parity (v0.23.x):
* Idempotency on (task_id, phase, reason) via ``.trigger-keys`` file.
* Initialise memory skeleton once before fan-out.
* Spawn knowledge-extractor / skill-extractor / config-extractor as
  detached subprocess of ``extract.py`` (NOT ``extract.sh``) so no bash
  is required.
* Emit ``{"enqueued_jobs":[...],"skipped":[...]}`` on stdout.
* Append events to ``.codenook/memory/history/extraction-log.jsonl``.
* Always exits 0 from :func:`run` unless argument validation fails.

The legacy LLM-driven route classification (``extraction_router.py``)
is retained as a best-effort lookup; failures fall back to
``cross_task`` for all three artefact kinds.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _append_log(log_path: Path, entry: dict) -> None:
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in entry.items() if v is not None},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def _classify_routes(task_id: str, workspace: Path, phase: str, reason: str,
                     lib_dir: Path) -> dict:
    """Best-effort routing via the legacy extraction_router.py. Always
    returns the four-key dict; defaults to cross_task on any failure."""
    # v0.26.0: post-router short-circuit (extraction_router.py since
    # v0.25.0 always emits route_fallback=False because the router
    # itself short-circuited the LLM call to a constant). Defaulting
    # to True here was a vestige from when the field carried meaning;
    # leave the field in the contract for forward-compat but reflect
    # current behaviour. To be removed in v0.27 along with the router.
    default = {
        "knowledge": "cross_task", "skill": "cross_task",
        "config": "cross_task", "route_fallback": False,
    }
    router_py = lib_dir / "extraction_router.py"
    if not router_py.is_file():
        return default
    try:
        proc = subprocess.run(
            [sys.executable, str(router_py),
             "--task-id", task_id, "--workspace", str(workspace),
             "--phase", phase, "--reason", reason],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "PYTHONPATH": str(lib_dir)},
        )
        if proc.returncode != 0:
            return default
        data = json.loads(proc.stdout or "{}")
        if not isinstance(data, dict):
            return default
        return {
            "knowledge": str(data.get("knowledge") or "cross_task"),
            "skill":     str(data.get("skill")     or "cross_task"),
            "config":    str(data.get("config")    or "cross_task"),
            "route_fallback": bool(data.get("route_fallback", False)),
        }
    except Exception:
        return default


def _init_memory_skeleton(lib_dir: Path, workspace: Path) -> None:
    """Best-effort memory layout init (mirrors the .sh inline PY heredoc)."""
    try:
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import memory_layer as ml  # type: ignore
        if not ml.has_memory(workspace):
            ml.init_memory_skeleton(workspace)
    except Exception as e:
        print(f"[extractor-batch] init_memory_skeleton best-effort failed: {e}",
              flush=True)


def _spawn_extractor(name: str, lookup_root: Path, task_id: str,
                     workspace: Path, phase: str, reason: str,
                     routes: dict, history_dir: Path) -> tuple[bool, str | None]:
    """Spawn one extractor as a detached subprocess of its extract.py.

    Returns (enqueued?, skip_reason_if_not).
    """
    extract_py = lookup_root / name / "extract.py"
    if not extract_py.is_file():
        # Mirror .sh: missing extractor is "not_present"
        extract_sh = lookup_root / name / "extract.sh"
        if extract_sh.is_file():
            # legacy-only dir without a .py sibling; we cannot safely
            # invoke the .sh here (Windows / no-bash hosts), so skip.
            return False, "not_executable"
        return False, "not_present"

    err_log = history_dir / f".extractor-{name}.err"
    env = os.environ.copy()
    env["CN_EXTRACTION_ROUTE_KNOWLEDGE"] = routes["knowledge"]
    env["CN_EXTRACTION_ROUTE_SKILL"]     = routes["skill"]
    env["CN_EXTRACTION_ROUTE_CONFIG"]    = routes["config"]
    cmd = [sys.executable, str(extract_py),
           "--task-id", task_id, "--workspace", str(workspace),
           "--phase", phase, "--reason", reason]
    try:
        # Detach: fire-and-forget. Stdout/stderr appended to the per-
        # extractor err log; no waiting, no propagation (FR-EXT-5).
        with err_log.open("a", encoding="utf-8") as logf:
            kwargs: dict = dict(stdout=logf, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env, cwd=str(workspace))
            if os.name == "nt":
                # Windows: detach into its own process group so the
                # parent (extractor-batch caller / tick) can return
                # immediately even if the extractor takes longer.
                DETACHED = 0x00000008  # DETACHED_PROCESS
                NEW_PG = 0x00000200    # CREATE_NEW_PROCESS_GROUP
                kwargs["creationflags"] = DETACHED | NEW_PG
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen(cmd, **kwargs)
    except OSError as e:
        return False, f"spawn_failed: {e}"
    return True, None


def run(*, task_id: str, reason: str, workspace: "str | Path",
        phase: str = "", lookup_root: "str | Path | None" = None) -> dict:
    """Programmatic entry. Returns ``{"enqueued_jobs":..., "skipped":...}``.

    Side effects: spawn extractor processes, write history log,
    record idempotency key. Best-effort; never raises (matches
    FR-EXT-5 / AC-TRG-4 from the .sh contract).
    """
    if not task_id:
        return {"enqueued_jobs": [], "skipped": [
            {"reason": "missing_task_id"}]}
    if not reason:
        return {"enqueued_jobs": [], "skipped": [
            {"reason": "missing_reason"}]}

    ws = Path(workspace).resolve()
    here = Path(__file__).resolve().parent
    lib_dir = (here.parent / "_lib").resolve()
    lookup = Path(lookup_root).resolve() if lookup_root else here.parent.resolve()

    history_dir = ws / ".codenook" / "memory" / "history"
    _ensure_dir(history_dir)
    trigger_keys = history_dir / ".trigger-keys"
    log_path = history_dir / "extraction-log.jsonl"

    key = _sha256(f"{task_id}|{phase}|{reason}")

    # Idempotency
    if trigger_keys.is_file():
        try:
            existing = trigger_keys.read_text(encoding="utf-8").splitlines()
            if key in existing:
                _append_log(log_path, {
                    "ts": _now_iso(), "task_id": task_id, "phase": phase,
                    "reason": reason, "event": "deduped", "key": key})
                return {"enqueued_jobs": [],
                        "skipped": [{"reason": "deduped", "key": key}],
                        "reason": "deduped"}
        except OSError:
            pass
    try:
        with trigger_keys.open("a", encoding="utf-8") as f:
            f.write(key + "\n")
    except OSError:
        pass

    routes = _classify_routes(task_id, ws, phase, reason, lib_dir)
    _init_memory_skeleton(lib_dir, ws)

    enqueued: list[str] = []
    skipped: list[dict] = []
    for name in ("knowledge-extractor", "skill-extractor", "config-extractor"):
        ok, skip_reason = _spawn_extractor(
            name, lookup, task_id, ws, phase, reason, routes, history_dir)
        if ok:
            enqueued.append(name)
            _append_log(log_path, {
                "ts": _now_iso(), "task_id": task_id, "phase": phase,
                "reason": reason, "event": "extractor_dispatched",
                "name": name, "key": key})
        else:
            skipped.append({"name": name, "reason": skip_reason})
            event = ("extractor_missing" if skip_reason == "not_present"
                     else "extractor_not_executable")
            _append_log(log_path, {
                "ts": _now_iso(), "task_id": task_id, "phase": phase,
                "reason": reason, "event": event,
                "name": name, "key": key})

    _append_log(log_path, {
        "ts": _now_iso(), "task_id": task_id, "phase": phase,
        "reason": reason, "event": "phase_complete", "key": key,
        "route": routes,
    })

    return {"enqueued_jobs": enqueued, "skipped": skipped}


def _find_workspace(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / ".codenook").is_dir():
            return p
    return None


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="extractor-batch")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--workspace", default=os.environ.get("CN_WORKSPACE")
                                       or os.environ.get("CODENOOK_WORKSPACE"))
    ap.add_argument("--phase", default="")
    args = ap.parse_args(argv)

    ws = Path(args.workspace) if args.workspace else _find_workspace(Path.cwd())
    if not ws or not ws.is_dir():
        print("extractor-batch: workspace not found", file=sys.stderr)
        return 2

    lookup = os.environ.get("CN_EXTRACTOR_LOOKUP_ROOT")
    out = run(task_id=args.task_id, reason=args.reason, workspace=ws,
              phase=args.phase, lookup_root=lookup)
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
