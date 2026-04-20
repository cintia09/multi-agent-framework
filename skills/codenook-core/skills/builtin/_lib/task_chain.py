"""task_chain — M10.1 chain primitives.

Implements ``docs/task-chains.md`` §3 lifecycle and §4 interface for
parent/child task linking. Persistence target is each task's
``state.json`` (validated against ``schemas/task-state.schema.json``);
chain_root is cached per task and a workspace-wide
``.codenook/tasks/.chain-snapshot.json`` (schema v2 per spec §8.2)
carries a monotonically increasing ``generation`` counter so callers
can detect chain mutations cheaply.

Public API:

    get_parent(workspace, task_id)        -> Optional[str]
    set_parent(workspace, child, parent, *, force=False) -> None
    walk_ancestors(workspace, task_id, *, max_depth=None) -> list[str]
    chain_root(workspace, task_id)        -> Optional[str]
    detach(workspace, task_id)            -> None

Errors:

    CycleError              — raised by set_parent on self-loop or
                              ancestor cycle (only set_parent raises;
                              walk_ancestors silently truncates and
                              emits chain_walk_truncated).
    CorruptChainError       — raised by set_parent when parent ancestry
                              is corrupt (mid-chain state missing).
    TaskNotFoundError       — referenced state.json missing
    AlreadyAttachedError    — child already has a parent (no --force)

Audit (via extract_audit.audit, asset_type="chain"):

    chain_attached, chain_attach_failed, chain_detached,
    chain_walk_truncated  + diagnostics chain_root_stale,
    chain_snapshot_slow_rebuild
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

# Sibling _lib imports — assumes PYTHONPATH includes this directory
# (tests set PYTHONPATH=$M10_LIB_DIR; CLI is run as `python -m task_chain`
# with the same PYTHONPATH).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atomic import atomic_write_json, atomic_write_json_validated  # noqa: E402
import extract_audit  # noqa: E402
import memory_layer as _ml  # noqa: E402

_TASK_ID_RE = re.compile(r"^T-[A-Za-z0-9_-]+$")

_SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "schemas"
_TASK_STATE_SCHEMA = str(_SCHEMAS_DIR / "task-state.schema.json")

_SNAPSHOT_REL = Path(".codenook") / "tasks" / ".chain-snapshot.json"
_SNAPSHOT_SCHEMA_VERSION = 1
_SLOW_REBUILD_MS = 500.0


# ───────────────────────────────────────────────────────────── exceptions

class CycleError(ValueError):
    """Raised when set_parent would form a cycle."""


class CorruptChainError(ValueError):
    """Raised by set_parent when the parent's ancestry is corrupt
    (e.g. mid-chain state.json missing or malformed) so we cannot
    safely compute chain_root. The attachment is refused (M10.6
    R1-MINOR-08)."""


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
#
# Schema v2 (docs/task-chains.md §8.2)::
#
#   {
#     "schema_version": 1,
#     "generation": <int>,
#     "built_at": "<iso8601>",
#     "entries": {
#       "<task_id>": {
#         "parent_id": "<tid>" | null,
#         "chain_root": "<tid>" | null,
#         "state_mtime": "<iso8601>"
#       },
#       ...
#     }
#   }
#
# Cold-start fallback read: any snapshot file lacking "entries" (e.g.
# the v1 ``{version, generation, chains}`` shape produced before
# M10.6) is treated as a cold start — full ``_build_snapshot`` rebuild.


def _iso_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_mtime(p: Path) -> str:
    try:
        ts = p.stat().st_mtime
    except OSError:
        return ""
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _empty_snapshot(generation: int = 0) -> dict:
    return {
        "schema_version": _SNAPSHOT_SCHEMA_VERSION,
        "generation": generation,
        "built_at": _iso_now(),
        "entries": {},
    }


def _read_snapshot(workspace: Path | str) -> dict:
    """Return parsed snapshot or an empty v2 shell.

    A snapshot lacking the v2 ``entries`` field is treated as a cold
    start (returned as empty); callers that need the old generation
    counter still see ``generation=0``. ``_bump_snapshot`` and
    ``_build_snapshot`` are responsible for re-populating the file.
    """
    p = _snapshot_path(workspace)
    if not p.exists():
        return _empty_snapshot()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("snapshot must be object")
    except (OSError, json.JSONDecodeError, ValueError):
        return _empty_snapshot()
    # v1 → cold start; preserve old generation only as a hint, never
    # trust its entries.
    if "entries" not in data or not isinstance(data.get("entries"), dict):
        return _empty_snapshot(generation=int(data.get("generation", 0) or 0))
    data.setdefault("schema_version", _SNAPSHOT_SCHEMA_VERSION)
    data.setdefault("generation", 0)
    data.setdefault("built_at", _iso_now())
    return data


def _write_snapshot(workspace: Path | str, snap: dict) -> None:
    p = _snapshot_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(p), snap)


def _build_snapshot(workspace: Path | str) -> dict:
    """Full O(N) scan of ``.codenook/tasks/*/state.json`` and rebuild.

    Resolves ``chain_root`` for every task with a single topo pass: we
    first record (task_id, parent_id, mtime) for every task, then walk
    parent links once with cycle/missing-parent guards, memoising
    chain_root so each task is computed exactly once.

    Bumps the snapshot generation; preserves the previous counter when
    the on-disk file is readable. Emits ``chain_snapshot_slow_rebuild``
    diagnostic when wall time exceeds 500 ms (spec §8.5).
    """
    t0 = time.perf_counter()
    ws = _ws(workspace)
    tasks_dir = ws / ".codenook" / "tasks"
    raw: dict[str, dict] = {}
    if tasks_dir.is_dir():
        for entry in os.listdir(tasks_dir):
            if entry.startswith("."):
                continue
            sp = tasks_dir / entry / "state.json"
            if not sp.is_file():
                continue
            try:
                with open(sp, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(state, dict):
                continue
            pid = state.get("parent_id")
            raw[entry] = {
                "parent_id": pid if isinstance(pid, str) else None,
                "state_mtime": _iso_mtime(sp),
            }

    # Memoised chain_root resolver. Returns ``(root, cycle)`` so the
    # outer frame can detect when a descendant signalled a cycle (or an
    # ancestor on the in-progress stack pointed back at itself) and
    # avoid memoising a bogus root for any node still inside the cycle.
    # Spec §8.2: chain_root is null for cycle members, self-parents,
    # and tasks whose parent is missing.
    roots: dict[str, Optional[str]] = {}

    def resolve(tid: str, in_progress: set[str]) -> tuple[Optional[str], bool]:
        if tid in roots:
            return roots[tid], False
        if tid in in_progress:
            # Cycle: do NOT memoise — every frame on the stack must see
            # the cycle signal so it can refuse to record a fake root.
            return None, True
        node = raw.get(tid)
        if node is None:
            roots[tid] = None
            return None, False
        pid = node["parent_id"]
        if pid is None:
            roots[tid] = None
            return None, False
        if pid not in raw:
            roots[tid] = None
            return None, False
        in_progress.add(tid)
        parent_root, cycle = resolve(pid, in_progress)
        in_progress.discard(tid)
        if cycle:
            # Don't memoise — tid sits on (or hangs off) the cycle.
            return None, True
        # tid's chain_root = parent's chain_root if parent has one,
        # else parent itself (parent is a root with at least one child).
        roots[tid] = parent_root if parent_root is not None else pid
        return roots[tid], False

    entries: dict[str, dict] = {}
    for tid, node in raw.items():
        cr, _cycle = resolve(tid, set())
        entries[tid] = {
            "parent_id": node["parent_id"],
            "chain_root": cr,
            "state_mtime": node["state_mtime"],
        }

    prev = _read_snapshot(workspace)
    snap = {
        "schema_version": _SNAPSHOT_SCHEMA_VERSION,
        "generation": int(prev.get("generation", 0) or 0) + 1,
        "built_at": _iso_now(),
        "entries": entries,
    }
    _write_snapshot(workspace, snap)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if elapsed_ms > _SLOW_REBUILD_MS:
        _diag(workspace, kind="chain_snapshot_slow_rebuild",
              source_task="",
              reason=f"elapsed_ms={elapsed_ms:.1f} N={len(entries)}")
    return snap


def _bump_snapshot(workspace: Path | str, *, clear: bool = True) -> int:
    """Bump generation. If snapshot is missing v2 entries → full rebuild.

    ``clear`` is preserved as a no-op kwarg for source compatibility
    with M10.1 callers; v2 always rebuilds entries to keep them in
    lockstep with state.json mutations.
    """
    del clear  # v2: entries are always derived from state.json
    snap = _build_snapshot(workspace)
    return int(snap["generation"])


def _invalidate_snapshot(workspace: Path | str, task_id: str) -> None:
    """Mtime-aware invalidation: rebuild the single entry if its
    state.json mtime drifted; otherwise no-op.
    """
    snap = _read_snapshot(workspace)
    sp = _state_path(workspace, task_id)
    if not sp.exists():
        return
    mt = _iso_mtime(sp)
    entry = snap.get("entries", {}).get(task_id)
    if entry is not None and entry.get("state_mtime") == mt:
        return
    _build_snapshot(workspace)


# Internal shims (kept so external callers / older tests still
# import without breaking; both no-op on the v2 path because entries
# are derived from state.json on every bump/build).

def _snapshot_lookup(workspace: Path | str, task_id: str) -> Optional[dict]:
    snap = _read_snapshot(workspace)
    entry = snap.get("entries", {}).get(task_id)
    if not isinstance(entry, dict):
        return None
    # Re-shape into the legacy {root, ancestors} surface used by the CLI.
    return {
        "root": entry.get("chain_root"),
        "ancestors": [],  # ancestors no longer cached eagerly in v2
    }


def _snapshot_remember(workspace: Path | str, task_id: str, root: str,
                       ancestors: list[str]) -> None:
    # v2 derives entries from state.json on bump/build; explicit
    # remember calls become a request to refresh that single entry.
    del root, ancestors  # superseded by mtime-driven derivation
    _invalidate_snapshot(workspace, task_id)


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


def _diag(workspace: Path | str, *, kind: str, source_task: str = "",
          reason: str = "") -> None:
    """Emit a single diagnostic jsonl record (spec §9.1).

    Bypasses ``extract_audit.audit`` to avoid the canonical+side-record
    duplication that would otherwise emit two lines (one with ``kind``,
    one without). Writes directly via ``memory_layer.append_audit`` with
    the 8 canonical keys plus ``kind``.
    """
    try:
        rec = {
            "asset_type": "chain",
            "candidate_hash": "",
            "existing_path": None,
            "outcome": "diagnostic",
            "reason": reason,
            "source_task": source_task,
            "timestamp": extract_audit._now_iso(),
            "verdict": "noop",
            "kind": kind,
        }
        _ml.append_audit(workspace, rec)
    except Exception:
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
    exist. Cross-checks the snapshot for stale ``state_mtime`` entries
    and emits a ``chain_root_stale`` diagnostic when one is observed
    (best-effort observability; never raises).
    """
    chain, _trunc, _reason = _walk_with_status(
        workspace, task_id, max_depth=max_depth, max_tokens=max_tokens
    )
    return chain


def _walk_with_status(workspace: Path | str, task_id: str, *,
                      max_depth: Optional[int] = None,
                      max_tokens: Optional[int] = None,
                      ) -> tuple[list[str], Optional[str], str]:
    """Internal walk that also returns truncation status.

    Returns ``(chain, truncation_kind, reason)`` where ``truncation_kind``
    is one of ``None`` (clean walk), ``"unreadable"`` (missing/malformed
    mid-chain state.json), ``"cycle"`` (loop detected mid-chain), or
    ``"depth"`` (max_depth reached). Used by ``set_parent`` to classify
    walk truncation (M10.6 MINOR-08 raises on ``unreadable``; M10.1
    MINOR-02 downgrades audit verdict on the residual cases).
    """
    del max_tokens  # legacy import alias kwarg; unused
    chain: list[str] = []
    seen: set[str] = set()
    cur: Optional[str] = task_id
    first = True
    truncation_kind: Optional[str] = None
    truncation_reason = ""
    snap_entries = (_read_snapshot(workspace).get("entries") or {})
    stale_seen = False
    while cur is not None:
        state = _read_state_json(workspace, cur)
        if state is None:
            if first:
                return [], None, ""
            truncation_kind = "unreadable"
            truncation_reason = f"unreadable state.json at {cur}"
            _audit(workspace, outcome="chain_walk_truncated", verdict="warn",
                   source_task=task_id, reason=truncation_reason)
            break
        if cur in seen:
            truncation_kind = "cycle"
            truncation_reason = f"cycle detected at {cur}"
            _audit(workspace, outcome="chain_walk_truncated", verdict="warn",
                   source_task=task_id, reason=truncation_reason)
            break
        seen.add(cur)
        chain.append(cur)
        # Snapshot freshness check: stale entry → diag (one per walk).
        if not stale_seen:
            entry = snap_entries.get(cur) if isinstance(snap_entries, dict) else None
            if isinstance(entry, dict):
                disk_mtime = _iso_mtime(_state_path(workspace, cur))
                if entry.get("state_mtime") and entry["state_mtime"] != disk_mtime:
                    _diag(workspace, kind="chain_root_stale", source_task=cur,
                          reason=f"snap={entry.get('state_mtime')} disk={disk_mtime}")
                    stale_seen = True
        if max_depth is not None and len(chain) >= max_depth:
            truncation_kind = "depth"
            truncation_reason = f"max_depth={max_depth} reached"
            _audit(workspace, outcome="chain_walk_truncated", verdict="warn",
                   source_task=task_id, reason=truncation_reason)
            break
        nxt = state.get("parent_id")
        cur = nxt if isinstance(nxt, str) else None
        first = False
    return chain, truncation_kind, truncation_reason


def chain_root(workspace: Path | str, task_id: str) -> Optional[str]:
    """Return cached chain_root; recompute (and persist) if missing.

    Single-state-read fast path: when state.json already carries a
    valid chain_root, this function performs exactly one
    ``_read_state_json`` call (TC-M10.1-08 contract). The v2 chain
    snapshot is updated as a side-effect of every ``set_parent`` /
    ``detach`` (via ``_bump_snapshot`` → ``_build_snapshot``), so
    callers needing an out-of-band chain_root view can read
    ``entries[tid].chain_root`` from the snapshot directly.
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
        parent_chain, trunc_kind, trunc_reason = _walk_with_status(
            workspace, parent_id
        )
        if child_id in parent_chain:
            raise CycleError(
                f"cycle: {child_id} appears in ancestors of {parent_id}"
            )
        # M10.6 R1-MINOR-08: refuse attachment when the parent's
        # ancestry walk truncated due to corrupt mid-chain state
        # (unreadable / missing state.json). chain_root computed from a
        # truncated walk would be bogus, and silently attaching would
        # propagate the corruption to the new child.
        if trunc_kind == "unreadable":
            raise CorruptChainError(
                f"corrupt ancestry of {parent_id}: {trunc_reason}"
            )
        # chain_root = last element of parent_chain (parent's own root).
        new_root = parent_chain[-1] if parent_chain else parent_id
        child_state["parent_id"] = parent_id
        child_state["chain_root"] = new_root
        _write_state_json(workspace, child_id, child_state)
        _bump_snapshot(workspace)
        # M10.1 R1-MINOR-02: if walking the parent's ancestry truncated
        # (cycle / depth) the cached chain_root is best-effort and may
        # be wrong; downgrade verdict to "warn" and tag the side-record
        # with chain_root_uncertain=true so callers can act on it.
        if trunc_kind is not None:
            try:
                extract_audit.audit(
                    workspace,
                    asset_type="chain",
                    outcome="chain_attached",
                    verdict="warn",
                    source_task=child_id,
                    reason=(f"parent={parent_id},root={new_root},"
                            f"truncated={trunc_kind}:{trunc_reason}"),
                    extra={"chain_root_uncertain": True},
                )
            except Exception:
                pass
        else:
            _audit(workspace, outcome="chain_attached", verdict="ok",
                   source_task=child_id,
                   reason=f"parent={parent_id},root={new_root}")
    except (CycleError, CorruptChainError, TaskNotFoundError,
            AlreadyAttachedError, ValueError) as e:
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


class _UsageExit64Parser(argparse.ArgumentParser):
    """ArgumentParser whose ``error()`` exits with status 64 (spec §4.3).

    Argparse's default ``error()`` prints usage and exits with status 2;
    the M10 CLI contract requires usage errors to exit 64 so callers
    can distinguish them from operational failures (1/2/3).
    """

    def error(self, message: str) -> "None":  # type: ignore[override]
        self.print_usage(sys.stderr)
        prog = self.prog or "task_chain"
        sys.stderr.write(f"{prog}: error: {message}\n")
        sys.exit(64)


def cli_main(argv: list[str]) -> int:
    ap = _UsageExit64Parser(
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
    except CorruptChainError as e:
        print(f"CorruptChainError: {e}", file=sys.stderr)
        return 2
    except (TaskNotFoundError, ValueError, OSError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_main(sys.argv[1:]))
