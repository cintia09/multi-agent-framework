"""v0.19 — per-task execution mode resolution.

Two execution modes per task (v0.19.0):

  * ``sub-agent`` (default) — each phase is dispatched as a separate
    sub-agent via the conductor's task tool. The historical v0.17/v0.18
    behaviour. Best for heavy / parallelisable / context-isolated work.
  * ``inline`` — the conductor itself reads the role.md, produces the
    phase output file in its own session, then calls ``tick`` again to
    advance. No sub-agent spawn. Best for short / chatty / serial
    phases (clarifier-style, doc review).

The mode is recorded in the per-task ``state.json`` under the
``execution_mode`` key. Tasks created before v0.19 (no field present)
behave exactly as v0.18.x — they default to ``sub-agent``.

Future extension hook: ``resolve_exec_mode`` currently inspects only
the task state. A later release may extend it to fall through to a
plugin default (``plugins/<id>/plugin.yaml :: default_exec_mode``)
and a workspace default (``.codenook/config.yaml :: default_exec_mode``).
v0.19.0 keeps the resolution chain task-only for simplicity.
"""
from __future__ import annotations

from typing import Iterable

VALID_MODES: tuple[str, ...] = ("sub-agent", "inline")
DEFAULT_MODE = "sub-agent"


def resolve_exec_mode(task_state: dict) -> str:
    """Returns ``'sub-agent'`` or ``'inline'``. Defaults to ``'sub-agent'``.

    Anything other than the two valid mode strings (including ``None``,
    empty string, or unknown values) is coerced to the default. This
    matches the backward-compat contract: a state file without the
    field — or with a field the kernel does not recognise — must keep
    the v0.18.x sub-agent behaviour.
    """
    if not isinstance(task_state, dict):
        return DEFAULT_MODE
    mode = task_state.get("execution_mode")
    if isinstance(mode, str) and mode in VALID_MODES:
        return mode
    return DEFAULT_MODE


def is_valid_mode(mode: str, allowed: Iterable[str] = VALID_MODES) -> bool:
    return isinstance(mode, str) and mode in tuple(allowed)
