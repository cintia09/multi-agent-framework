"""task_chain — M10.1 chain primitives.

Implements ``docs/v6/task-chains-v6.md`` §3 lifecycle and §4 interface for
parent/child task linking. Persistence target is each task's
``state.json`` (validated against ``schemas/task-state.schema.json``);
chain_root is cached per task and a workspace-wide
``.codenook/tasks/.chain-snapshot.json`` carries a monotonically
increasing ``generation`` counter so callers can detect chain
mutations cheaply.

Public API:

    get_parent(workspace, task_id)        -> Optional[str]
    set_parent(workspace, child, parent, *, force=False) -> None
    walk_ancestors(workspace, task_id, *, max_depth=None) -> list[str]
    chain_root(workspace, task_id)        -> Optional[str]
    detach(workspace, task_id)            -> None

Errors:

    CycleError              — self-loop or ancestor cycle
    TaskNotFoundError       — referenced state.json missing
    AlreadyAttachedError    — child already has a parent (no --force)

Audit (via extract_audit.audit, asset_type="chain"):

    chain_attached, chain_attach_failed, chain_detached,
    chain_walk_truncated
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Sibling _lib imports — assumes PYTHONPATH includes this directory
# (tests set PYTHONPATH=$M10_LIB_DIR; CLI is run as `python -m task_chain`
# with the same PYTHONPATH).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atomic import atomic_write_json, atomic_write_json_validated  # noqa: E402
import extract_audit  # noqa: E402

_TASK_ID_RE = re.compile(r"^T-[A-Za-z0-9_-]+$")

_SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "schemas"
_TASK_STATE_SCHEMA = str(_SCHEMAS_DIR / "task-state.schema.json")

_SNAPSHOT_REL = Path(".codenook") / "tasks" / ".chain-snapshot.json"


# ───────────────────────────────────────────────────────────── exceptions

class CycleError(ValueError):
    """Raised when set_parent would form a cycle."""


class TaskNotFoundError(FileNotFoundError):
    """Raised when a referenced task's state.json does not exist."""


class AlreadyAttachedError(RuntimeError):
    """Raised when attaching a child that already has a parent_id (without --force)."""


# ───────────────────────────────────────────────────────────── path helpers

def _ws(workspace: Path | str) -> Path:
    return Path(workspace)


def _task_dir(workspace: Path | str, task_id: str) -> Path:
    return _ws(workspace) / ".codenook" / "tasks" / task_id


def _state_path(workspace: Path | str, task_id: str) -> Path:
    return _task_dir(workspace, task_id) / "state.json"


def _snapshot_path(workspace: Path | str) -> Path:
    return _ws(workspace) / _SNAPSHOT_REL


def _check_task_id(tid: str) -> None:
    if not isinstance(tid, str) or not _TASK_ID_RE.match(tid):
        raise ValueError(f"invalid task_id format: {tid!r}")


# ─────────────────────────────────────────────────────────── state IO core

def _read_state_json(workspace: Path | str, task_id: str) -> Optional[dict]:
    """Return parsed state.json or None on missing / unreadable / malformed.

    This is the single read seam the test suite spies on (TC-M10.1-08).
    Callers MUST go through this helper.
    """
    p = _state_path(workspace, task_id)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_state_json(workspace: Path | str, task_id: str, state: dict) -> None:
    p = _state_path(workspace, task_id)
    atomic_write_json_validated(str(p), state, _TASK_STATE_SCHEMA)


# ─────────────────────────────────────────────────────────── snapshot ops

def _read_snapshot(workspace: Path | str) -> dict:
    p = _snapshot_path(workspace)
    if not p.exists():
        return {"version": 1, "generation": 0, "chains": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("snapshot must be object")
        data.setdefault("version", 1)
        data.setdefault("generation", 0)
        data.setdefault("chains", {})
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return {"version": 1, "generation": 0, "chains": {}}


def _bump_snapshot(workspace: Path | str, *, clear: bool = True) -> int:
    snap = _read_snapshot(workspace)
    snap["generation"] = int(snap.get("generation", 0)) + 1
    if clear:
        snap["chains"] = {}
    p = _snapshot_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(p), snap)
    return snap["generation"]


def _snapshot_lookup(workspace: Path | str, task_id: str) -> Optional[dict]:
    snap = _read_snapshot(workspace)
    entry = snap.get("chains", {}).get(task_id)
    return entry if isinstance(entry, dict) else None


def _snapshot_remember(workspace: Path | str, task_id: str, root: str,
                       ancestors: list[str]) -> None:
    snap = _read_snapshot(workspace)
    snap.setdefault("chains", {})[task_id] = {
        "root": root,
        "ancestors": list(ancestors),
    }
    p = _snapshot_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(p), snap)


# ───────────────────────────────────────────────────────────────── audit

def _audit(workspace: Path | str, *, outcome: str, verdict: str,
           source_task: str, reason: str = "") -> None:
    try:
        extract_audit.audit(
            workspace,
            asset_type="chain",
            outcome=outcome,
            verdict=verdict,
            source_task=source_task,
            reason=reason,
        )
    except Exception:
        # Never let audit failures mask the primary operation.
        pass


# ─────────────────────────────────────────────────────────── public API

def get_parent(workspace: Path | str, task_id: str) -> Optional[str]:
    state = _read_state_json(workspace, task_id)
    if state is None:
        return None
    val = state.get("parent_id")
    return val if isinstance(val, str) else None


def walk_ancestors(workspace: Path | str, task_id: str, *,
                   max_depth: Optional[int] = None,
                   max_tokens: Optional[int] = None) -> list[str]:
    """Return ancestor chain child→root including ``task_id`` itself.

    Truncates (best-effort) on missing/malformed mid-chain state.json
    or when max_depth is hit; emits ``chain_walk_truncated`` audit in
    those cases. Returns ``[]`` if the starting task itself does not
    exist.
    """
    chain: list[str] = []
    seen: set[str] = set()
    cur: Optional[str] = task_id
    first = True
    while cur is not None:
        state = _read_state_json(workspace, cur)
        if state is None:
            if first:
                return []
            _audit(workspace, outcome="chain_walk_truncated", verdict="warn",
                   source_task=task_id,
                   reason=f"unreadable state.json at {cur}")
            break
        if cur in seen:
            raise CycleError(f"cycle detected at {cur}")
        seen.add(cur)
        chain.append(cur)
        if max_depth is not None and len(chain) >= max_depth:
            _audit(workspace, outcome="chain_walk_truncated", verdict="warn",
                   source_task=task_id,
                   reason=f"max_depth={max_depth} reached")
            break
        nxt = state.get("parent_id")
        cur = nxt if isinstance(nxt, str) else None
        first = False
    return chain


def chain_root(workspace: Path | str, task_id: str) -> Optional[str]:
    """Return cached chain_root; recompute (and persist) if missing.

    Single-state-read fast path: when state.json already carries a
    valid chain_root, this function performs exactly one
    ``_read_state_json`` call (TC-M10.1-08 contract).
    """
    state = _read_state_json(workspace, task_id)
    if state is None:
        return None
    parent = state.get("parent_id")
    cached = state.get("chain_root")
    if parent is None:
        return None
    if isinstance(cached, str) and cached:
        return cached
    # Recompute: walk parent chain and persist.
    ancestors = walk_ancestors(workspace, parent)
    if not ancestors:
        return None
    root = ancestors[-1]
    state["chain_root"] = root
    _write_state_json(workspace, task_id, state)
    return root


def set_parent(workspace: Path | str, child_id: str, parent_id: str,
               *, force: bool = False) -> None:
    """Attach ``child_id`` to ``parent_id``.

    Validates id format, parent existence, no-self-loop and no-cycle,
    optionally rejects an already-attached child (unless ``force`` is
    True), then atomically writes the child's state.json with new
    ``parent_id``/``chain_root`` and bumps the workspace snapshot
    generation. Emits ``chain_attached`` (success) or
    ``chain_attach_failed`` (any raised exception).
    """
    try:
        _check_task_id(child_id)
        _check_task_id(parent_id)
        if child_id == parent_id:
            raise CycleError(f"self-loop: {child_id} cannot be its own parent")
        child_state = _read_state_json(workspace, child_id)
        if child_state is None:
            raise TaskNotFoundError(f"child task not found: {child_id}")
        parent_state = _read_state_json(workspace, parent_id)
        if parent_state is None:
            raise TaskNotFoundError(f"parent task not found: {parent_id}")
        if not force and isinstance(child_state.get("parent_id"), str):
            raise AlreadyAttachedError(
                f"task {child_id} already attached to "
                f"{child_state['parent_id']!r}; pass force=True to override"
            )
        # Cycle check: walking parent's ancestors must NOT include child.
        parent_chain = walk_ancestors(workspace, parent_id)
        if child_id in parent_chain:
            raise CycleError(
                f"cycle: {child_id} appears in ancestors of {parent_id}"
            )
        # chain_root = last element of parent_chain (parent's own root).
        new_root = parent_chain[-1] if parent_chain else parent_id
        child_state["parent_id"] = parent_id
        child_state["chain_root"] = new_root
        _write_state_json(workspace, child_id, child_state)
        _bump_snapshot(workspace)
        _audit(workspace, outcome="chain_attached", verdict="ok",
               source_task=child_id,
               reason=f"parent={parent_id},root={new_root}")
    except (CycleError, TaskNotFoundError, AlreadyAttachedError, ValueError) as e:
        _audit(workspace, outcome="chain_attach_failed", verdict="error",
               source_task=child_id,
               reason=f"{type(e).__name__}: {e}")
        raise


def detach(workspace: Path | str, task_id: str) -> None:
    """Set parent_id and chain_root to null. Idempotent — no audit on no-op."""
    state = _read_state_json(workspace, task_id)
    if state is None:
        # Nothing to detach; treat as no-op (mirrors get_parent's tolerance).
        return
    if state.get("parent_id") is None:
        return
    state["parent_id"] = None
    state["chain_root"] = None
    _write_state_json(workspace, task_id, state)
    _bump_snapshot(workspace)
    _audit(workspace, outcome="chain_detached", verdict="ok",
           source_task=task_id)


# ─────────────────────────────────────────────────────────────── CLI

def _cli_show(args) -> int:
    ws = args.workspace
    chain = walk_ancestors(ws, args.task)
    if not chain:
        print(f"task not found: {args.task}", file=sys.stderr)
        return 1
    snap = _snapshot_lookup(ws, args.task)
    snapshot_hit = snap is not None and snap.get("ancestors") == chain
    if args.format == "json":
        out = {
            "task_id": args.task,
            "parent_id": chain[1] if len(chain) > 1 else None,
            "chain_root": chain[-1] if len(chain) > 1 else None,
            "ancestors": chain,
            "depth": len(chain),
            "snapshot_hit": snapshot_hit,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for i, tid in enumerate(chain):
            prefix = "* " if i == 0 else "  " + ("└─ " if i == len(chain) - 1 else "├─ ")
            print(f"{prefix}{tid}")
    # Update snapshot cache (best-effort) so subsequent --format=json
    # show calls report snapshot_hit=true.
    try:
        if len(chain) > 1:
            _snapshot_remember(ws, args.task, chain[-1], chain)
    except Exception:
        pass
    return 0


def cli_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="task_chain",
        description="CodeNook M10 task-chain primitives (attach/detach/show/root).",
    )
    ap.add_argument("--workspace", default=".",
                    help="Workspace root (default: cwd).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _ws_arg(p):
        # SUPPRESS default so top-level --workspace is preserved when
        # subcommand omits it; subcommand value wins when given.
        p.add_argument("--workspace", default=argparse.SUPPRESS,
                       help="Workspace root (overrides top-level --workspace).")

    p_at = sub.add_parser("attach", help="Set child's parent_id.")
    p_at.add_argument("child")
    p_at.add_argument("parent")
    p_at.add_argument("--force", action="store_true",
                      help="Overwrite existing parent_id.")
    _ws_arg(p_at)

    p_de = sub.add_parser("detach", help="Clear child's parent_id.")
    p_de.add_argument("child")
    _ws_arg(p_de)

    p_sh = sub.add_parser("show", help="Print ancestor chain (child→root).")
    p_sh.add_argument("task")
    p_sh.add_argument("--format", choices=("text", "json"), default="text")
    _ws_arg(p_sh)

    p_rt = sub.add_parser("root", help="Print cached chain_root for a task.")
    p_rt.add_argument("task")
    _ws_arg(p_rt)

    args = ap.parse_args(argv)
    workspace = getattr(args, "workspace", ".")

    try:
        if args.cmd == "attach":
            set_parent(workspace, args.child, args.parent, force=args.force)
            return 0
        if args.cmd == "detach":
            detach(workspace, args.child)
            return 0
        if args.cmd == "show":
            args.workspace = workspace
            return _cli_show(args)
        if args.cmd == "root":
            r = chain_root(workspace, args.task)
            print(r if r is not None else "")
            return 0
    except AlreadyAttachedError as e:
        print(f"AlreadyAttachedError: {e}", file=sys.stderr)
        return 3
    except CycleError as e:
        print(f"CycleError: {e}", file=sys.stderr)
        return 2
    except (TaskNotFoundError, ValueError, OSError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_main(sys.argv[1:]))
