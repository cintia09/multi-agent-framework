"""extraction_router.py — single combined LLM call that classifies the three
extractor artefacts (knowledge, skill, config) as either ``task_specific``
(write to tasks/<T>/extracted/) or ``cross_task`` (write to memory/).

Called synchronously from extractor-batch.sh BEFORE the extractors are
dispatched.  Returns immediately with a fallback dict on any LLM error so
the dispatch path is never blocked.

Public API::

    route_artefacts(workspace, task_id, phase, *, task_title="",
                    phase_summary="") -> tuple[dict, bool]
    # Returns (routes, route_fallback)
    # routes: {"knowledge": "task_specific"|"cross_task",
    #           "skill":     "task_specific"|"cross_task",
    #           "config":    "task_specific"|"cross_task"}
    # route_fallback: True when the LLM call failed or the JSON was unparseable.

CLI (invoked by extractor-batch.sh)::

    python3 extraction_router.py \\
        --task-id T-001 --workspace /ws --phase clarify --reason after_phase
    # Prints one JSON line on stdout: {"knowledge":..,"skill":..,"config":..,"route_fallback":false}
    # Always exits 0 (best-effort).

Mock support (same conventions as llm_call.py):
    call_name = "extraction_route"
    → $CN_LLM_MOCK_EXTRACTION_ROUTE env var or CN_LLM_MOCK_DIR/extraction_route.json
    → $CN_LLM_MOCK_RESPONSE
    → $CN_LLM_MOCK_ERROR_EXTRACTION_ROUTE triggers fallback
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from llm_call import call_llm  # noqa: E402

VALID_ROUTES = frozenset({"task_specific", "cross_task"})
ARTEFACT_TYPES = ("knowledge", "skill", "config")
FALLBACK_ROUTES: dict[str, str] = {t: "cross_task" for t in ARTEFACT_TYPES}
CALL_NAME = "extraction_route"


def _read_task_summary(workspace: Path, task_id: str) -> str:
    """Best-effort: read the last 20 lines of task.log or the state.json title."""
    task_dir = workspace / ".codenook" / "tasks" / task_id
    state_path = task_dir / "state.json"
    if state_path.is_file():
        try:
            import json as _json
            state = _json.loads(state_path.read_text(encoding="utf-8"))
            title = str(state.get("title") or "")
            summary = str(state.get("summary") or "")
            return (title + " " + summary).strip()[:300]
        except Exception:
            pass
    log = task_dir / "task.log"
    if log.is_file():
        try:
            lines = log.read_text(encoding="utf-8").splitlines()
            return "\n".join(lines[-20:])[:300]
        except Exception:
            pass
    return ""


def _memory_index_digest(workspace: Path) -> str:
    """Return a short digest of the current workspace memory index."""
    mem = workspace / ".codenook" / "memory"
    k_dir = mem / "knowledge"
    s_dir = mem / "skills"
    k_count = len(list(k_dir.glob("*.md"))) if k_dir.is_dir() else 0
    s_count = len(list(s_dir.iterdir())) if s_dir.is_dir() else 0
    return f"knowledge:{k_count} skills:{s_count}"


def _build_route_prompt(
    task_id: str,
    phase: str,
    reason: str,
    task_summary: str,
    memory_digest: str,
) -> str:
    return (
        "You are CodeNook's extraction router.\n"
        f"Task: {task_id}  Phase: {phase}  Reason: {reason}\n"
        f"Task summary: {task_summary or '(none)'}\n"
        f"Memory state: {memory_digest}\n\n"
        "Classify each extractor artefact (knowledge note, skill skeleton,\n"
        "config entry) produced during this phase as:\n"
        "  'task_specific' — artefact is only relevant to this specific task\n"
        "                    (e.g. one-off notes, task-scoped config)\n"
        "  'cross_task'    — artefact is reusable across tasks\n"
        "                    (e.g. a general algorithm, a shared config value)\n\n"
        "Respond with ONLY strict JSON — no prose, no fences:\n"
        '{"knowledge":"task_specific"|"cross_task",'
        '"skill":"task_specific"|"cross_task",'
        '"config":"task_specific"|"cross_task"}\n'
    )


def _parse_routes(raw: str) -> dict[str, str]:
    """Parse and validate the LLM response. Raises on bad shape."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        first_nl = raw.find("\n")
        last_fence = raw.rfind("```")
        if first_nl >= 0 and last_fence > first_nl:
            raw = raw[first_nl + 1 : last_fence].strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    routes: dict[str, str] = {}
    for t in ARTEFACT_TYPES:
        val = data.get(t, "cross_task")
        if val not in VALID_ROUTES:
            raise ValueError(f"invalid route for {t!r}: {val!r}")
        routes[t] = val
    return routes


def route_artefacts(
    workspace: Path,
    task_id: str,
    phase: str,
    *,
    reason: str = "",
    task_title: str = "",
    phase_summary: str = "",
) -> tuple[dict[str, str], bool]:
    """Classify the three artefact types for this (task, phase).

    Returns (routes_dict, route_fallback).
    Never raises — on any error falls back to {"knowledge": "cross_task", ...}.
    """
    task_summary = task_title or phase_summary or _read_task_summary(workspace, task_id)
    memory_digest = _memory_index_digest(workspace)
    prompt = _build_route_prompt(task_id, phase, reason, task_summary, memory_digest)
    try:
        raw = call_llm(prompt, call_name=CALL_NAME)
        routes = _parse_routes(raw)
        return routes, False
    except Exception:
        return dict(FALLBACK_ROUTES), True


def main(argv: list[str] | None = None) -> int:
    """CLI entry: print one JSON line, always exit 0."""
    p = argparse.ArgumentParser(prog="extraction_router")
    p.add_argument("--task-id", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--phase", default="")
    p.add_argument("--reason", default="")
    p.add_argument("--task-title", default="")
    args = p.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    routes, fallback = route_artefacts(
        workspace,
        args.task_id,
        args.phase,
        reason=args.reason,
        task_title=args.task_title,
    )
    out = dict(routes)
    out["route_fallback"] = fallback
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
