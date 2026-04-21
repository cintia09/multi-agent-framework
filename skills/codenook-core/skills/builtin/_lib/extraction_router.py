"""extraction_router.py — single combined LLM call that ratifies the route
for the three extractor artefacts (knowledge, skill, config).

After the ``task_specific`` destination was removed, the only valid route
is ``cross_task`` (write to ``memory/``). The LLM call is retained so the
external contract (mocks, audit log, env-var passthrough) is unchanged,
but any unknown response is coerced to ``cross_task``. The call itself is
slated for removal in a follow-up refactor.

Public API::

    route_artefacts(workspace, task_id, phase, *, task_title="",
                    phase_summary="") -> tuple[dict, bool]
    # Returns (routes, route_fallback)
    # routes: {"knowledge": "cross_task",
    #           "skill":     "cross_task",
    #           "config":    "cross_task"}
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

VALID_ROUTES = frozenset({"cross_task"})
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
        "All extractor artefacts are written to the workspace memory layer\n"
        "(``cross_task``).  The per-task destination has been removed.\n\n"
        "Respond with ONLY strict JSON — no prose, no fences:\n"
        '{"knowledge":"cross_task","skill":"cross_task","config":"cross_task"}\n'
    )


def _parse_routes(raw: str) -> dict[str, str]:
    """Parse the LLM response. Any unknown value is coerced to ``cross_task``.

    Raises ``json.JSONDecodeError`` / ``ValueError`` only on a non-object
    payload — individual route values are never rejected now that
    ``cross_task`` is the only valid destination.
    """
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
        routes[t] = val if val in VALID_ROUTES else "cross_task"
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

    Since the ``task_specific`` destination was removed, ``cross_task``
    is the only legal route. The previous implementation still spawned
    an LLM subprocess on every ``after_phase`` tick to confirm a
    constant — pure overhead. Short-circuit to the fallback dict and
    skip the LLM entirely. ``route_fallback`` stays ``False`` because
    nothing actually failed; the audit log entries written by callers
    will look identical to a successful classification, which preserves
    the external contract.

    Workspace / task_id / phase / reason / task_title / phase_summary
    are accepted (and ignored) so existing call sites keep compiling
    when this module is later deleted entirely.
    """
    del workspace, task_id, phase, reason, task_title, phase_summary
    return dict(FALLBACK_ROUTES), False


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
