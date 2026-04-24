"""G04 (plugin-version-check) — fingerprint mismatch carve-out.

When ``--upgrade`` is asked against an installed plugin of the *same*
version we historically rejected with "would downgrade or no-op".  T-006
relaxes this: if the staged plugin tree's ``.fingerprint`` exists and
differs from a freshly computed source-tree fingerprint, treat the call
as a legitimate dev-loop restage.  Without a fingerprint file the
historical reject still fires (backward-compatible with the bats
fixture in ``m2-plugin-version-check.bats``).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
GATE = (
    REPO_ROOT
    / "skills/codenook-core/skills/builtin/plugin-version-check/_version_check.py"
)
STAGE_KERNEL = REPO_ROOT / "skills/codenook-core/_lib/install/stage_kernel.py"


def _run_gate(src: Path, workspace: Path, *, upgrade: bool) -> tuple[int, dict]:
    env = os.environ.copy()
    env["CN_SRC"] = str(src)
    env["CN_WORKSPACE"] = str(workspace)
    env["CN_UPGRADE"] = "1" if upgrade else "0"
    env["CN_JSON"] = "1"
    cp = subprocess.run(
        [sys.executable, str(GATE)], env=env, capture_output=True, text=True
    )
    out = cp.stdout.strip()
    payload = json.loads(out) if out else {"ok": cp.returncode == 0, "reasons": []}
    return cp.returncode, payload


def _mk_plugin(dir_: Path, *, pid: str, version: str, body: str = "") -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / "plugin.yaml").write_text(
        f"id: {pid}\nversion: {version}\n", encoding="utf-8"
    )
    (dir_ / "role.md").write_text(body or "stub\n", encoding="utf-8")


def _compute_fp(src: Path) -> str:
    sys.path.insert(0, str(STAGE_KERNEL.parent))
    try:
        from stage_kernel import _compute_tree_fingerprint  # type: ignore
        return _compute_tree_fingerprint(src)
    finally:
        sys.path.remove(str(STAGE_KERNEL.parent))


def test_same_version_allow_when_no_fingerprint(tmp_path: Path) -> None:
    """Pre-T004 installs lack .fingerprint → treat as stale → allow restage."""
    src = tmp_path / "src"
    ws = tmp_path / "ws"
    _mk_plugin(src, pid="foo", version="1.0.0")
    _mk_plugin(
        ws / ".codenook" / "plugins" / "foo", pid="foo", version="1.0.0"
    )
    rc, payload = _run_gate(src, ws, upgrade=True)
    assert rc == 0, payload


def test_same_version_reject_when_fingerprint_matches(tmp_path: Path) -> None:
    src = tmp_path / "src"
    ws = tmp_path / "ws"
    installed = ws / ".codenook" / "plugins" / "foo"
    _mk_plugin(src, pid="foo", version="1.0.0", body="role-content\n")
    _mk_plugin(installed, pid="foo", version="1.0.0", body="anything\n")
    # Fingerprint matches the SOURCE tree (the canonical idempotent state):
    (installed / ".fingerprint").write_text(
        _compute_fp(src) + "\n", encoding="utf-8"
    )
    rc, payload = _run_gate(src, ws, upgrade=True)
    assert rc != 0, payload
    assert any("downgrade or no-op" in r for r in payload["reasons"])


def test_same_version_allow_when_fingerprint_mismatch(tmp_path: Path) -> None:
    """Dev-loop edit: source changed but version stayed put → allow restage."""
    src = tmp_path / "src"
    ws = tmp_path / "ws"
    installed = ws / ".codenook" / "plugins" / "foo"
    _mk_plugin(src, pid="foo", version="1.0.0", body="new content\n")
    _mk_plugin(installed, pid="foo", version="1.0.0", body="anything\n")
    # Stale fingerprint (from a hypothetical older source tree).
    (installed / ".fingerprint").write_text("0" * 64 + "\n", encoding="utf-8")
    rc, payload = _run_gate(src, ws, upgrade=True)
    assert rc == 0, payload
    assert payload["ok"] is True, payload


def test_downgrade_still_rejected(tmp_path: Path) -> None:
    src = tmp_path / "src"
    ws = tmp_path / "ws"
    _mk_plugin(src, pid="foo", version="1.0.0")
    _mk_plugin(
        ws / ".codenook" / "plugins" / "foo", pid="foo", version="2.0.0"
    )
    # Even if a stale fingerprint is present, an actual *downgrade* must
    # still fail — carve-out is keyed on equal-version, not <.
    (ws / ".codenook" / "plugins" / "foo" / ".fingerprint").write_text(
        "0" * 64 + "\n", encoding="utf-8"
    )
    rc, payload = _run_gate(src, ws, upgrade=True)
    assert rc != 0, payload
