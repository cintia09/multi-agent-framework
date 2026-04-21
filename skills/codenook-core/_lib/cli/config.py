"""Workspace + kernel resolution for the codenook CLI.

The CLI shim is installed at ``<ws>/.codenook/bin/codenook(.cmd)`` and
forwards to ``<core>/_lib/cli/__main__.py``. Two pieces of context need
to be resolved on every run:

* ``workspace``  — the project root that owns ``.codenook/``.
* ``kernel_dir`` — ``<ws>/.codenook/codenook-core/skills/builtin``,
  recorded inside ``.codenook/state.json`` at install time. The kernel
  contains the helper python scripts (``orchestrator-tick/_tick.py``,
  ``hitl-adapter/_hitl.py``, …) the CLI delegates to.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodenookContext:
    workspace: Path
    state_file: Path
    state: dict
    kernel_dir: Path

    @property
    def kernel_lib(self) -> Path:
        return self.kernel_dir / "_lib"

    @property
    def kernel_version(self) -> str:
        return str(self.state.get("kernel_version") or "?")


def _bin_dir() -> Path | None:
    """Best-effort: when the CLI ran via the bin shim, the parent of the
    shim is ``<ws>/.codenook/bin``. Use ``argv[0]`` to find it."""
    try:
        argv0 = Path(sys.argv[0]).resolve()
        if argv0.parent.name == "bin" and argv0.parent.parent.name == ".codenook":
            return argv0.parent
    except Exception:
        return None
    return None


def resolve_workspace(explicit: str | None = None) -> Path:
    if explicit:
        ws = Path(explicit).expanduser().resolve()
        if not ws.is_dir():
            sys.stderr.write(f"codenook: workspace not found: {ws}\n")
            sys.exit(2)
        return ws

    env = os.environ.get("CODENOOK_WORKSPACE")
    if env:
        ws = Path(env).expanduser().resolve()
        if (ws / ".codenook").is_dir():
            return ws

    bd = _bin_dir()
    if bd is not None:
        return bd.parent.parent  # <ws>

    cur = Path.cwd().resolve()
    for c in [cur, *cur.parents]:
        if (c / ".codenook").is_dir():
            return c

    return cur


def load_context(workspace: Path) -> CodenookContext:
    state_file = workspace / ".codenook" / "state.json"
    if not state_file.is_file():
        sys.stderr.write(
            f"codenook: no .codenook/state.json under {workspace}\n"
            f"          run: python install.py --target \"{workspace}\"\n"
        )
        sys.exit(1)
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception as e:
        sys.stderr.write(f"codenook: failed to read state.json: {e}\n")
        sys.exit(1)

    kdir_raw = state.get("kernel_dir") or ""
    if not kdir_raw:
        sys.stderr.write(
            f"codenook: kernel_dir missing in {state_file}\n"
            f"          re-run: python install.py --target \"{workspace}\"\n"
        )
        sys.exit(1)
    kdir = Path(kdir_raw)
    if not kdir.is_dir():
        sys.stderr.write(
            f"codenook: kernel_dir invalid in {state_file}: {kdir}\n"
            f"          re-run: python install.py --target \"{workspace}\"\n"
        )
        sys.exit(1)

    ctx = CodenookContext(
        workspace=workspace,
        state_file=state_file,
        state=state,
        kernel_dir=kdir,
    )
    # All downstream python helpers expect _lib on PYTHONPATH and
    # CODENOOK_WORKSPACE in the environment.
    sys.path.insert(0, str(ctx.kernel_lib))
    os.environ["PYTHONPATH"] = (
        str(ctx.kernel_lib)
        + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    )
    os.environ["CODENOOK_WORKSPACE"] = str(workspace)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    return ctx


def next_task_id(workspace: Path) -> str:
    """Walk ``<ws>/.codenook/tasks/`` and return the next free ``T-NNN``."""
    tasks_dir = workspace / ".codenook" / "tasks"
    n = 1
    while (tasks_dir / f"T-{n:03d}").is_dir():
        n += 1
    return f"T-{n:03d}"


def is_active_task_dir(p: Path) -> bool:
    """True iff *p* is an active task directory worth iterating.

    A directory counts as active when:
      * it is a directory (not a regular file or symlink to one)
      * its name does not start with ``.`` or ``_`` (skips
        ``.gitignore``, ``.archive/``, ``_pending/`` and friends)
      * a ``state.json`` file exists inside it

    Used by every kernel surface that walks ``.codenook/tasks/`` so a
    user-dropped legacy folder (e.g. archived investigation notes
    without state.json) never surfaces as an active task and never
    crashes the iterator.
    """
    if not p.is_dir():
        return False
    name = p.name
    if name.startswith(".") or name.startswith("_"):
        return False
    if not (p / "state.json").is_file():
        return False
    return True


def iter_active_task_dirs(tasks_dir: Path):
    """Yield active task directories under *tasks_dir* in sorted order.

    Returns an empty iterator when ``tasks_dir`` does not exist.
    """
    if not tasks_dir.is_dir():
        return
    for d in sorted(tasks_dir.iterdir()):
        if is_active_task_dir(d):
            yield d
