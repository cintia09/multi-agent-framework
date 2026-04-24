"""Helpers for tests that need to invoke `_lib.cli.cmd_task` in-process.

The CLI lives at `skills/codenook-core/_lib/cli/cmd_task.py`. To
import it we need the kernel directory to be on `sys.path` so the
`_lib` package resolves. We also need a `CodenookContext` instance
pointing at the test workspace.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
KERNEL = REPO / "skills" / "codenook-core"

# Make `_lib.cli...` importable.
if str(KERNEL) not in sys.path:
    sys.path.insert(0, str(KERNEL))


@dataclass
class _Ctx:
    workspace: Path
    state_file: Path
    state: dict
    kernel_dir: Path


def make_ctx(workspace: Path) -> _Ctx:
    return _Ctx(workspace=workspace,
                state_file=workspace / ".codenook" / "state.json",
                state={"kernel_version": "test"},
                kernel_dir=KERNEL)


def write_state(workspace: Path, task_id: str, state: dict) -> Path:
    sf = workspace / ".codenook" / "tasks" / task_id / "state.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(state), encoding="utf-8")
    return sf
