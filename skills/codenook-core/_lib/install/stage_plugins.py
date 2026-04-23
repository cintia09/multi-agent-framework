"""Per-plugin install: run the 12-gate orchestrator for one plugin.

Replaces the bash idempotency-detection + ``skills/codenook-core/install.sh``
+ ``orchestrator.sh`` thin wrapper. The actual gate logic still lives in
``install-orchestrator/_orchestrator.py``; we just set its ``CN_*``
environment and invoke it as a subprocess (one per plugin).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from .stage_kernel import _FINGERPRINT_NAME, _compute_tree_fingerprint


def discover_plugins(repo_root: Path) -> list[str]:
    plugins_dir = repo_root / "plugins"
    if not plugins_dir.is_dir():
        return []
    out: list[str] = []
    for p in sorted(plugins_dir.iterdir()):
        if p.is_dir() and (p / "plugin.yaml").is_file():
            out.append(p.name)
    return out


def read_plugin_version(plugin_src: Path) -> str:
    yaml_p = plugin_src / "plugin.yaml"
    if not yaml_p.is_file():
        return ""
    try:
        d = yaml.safe_load(yaml_p.read_text(encoding="utf-8")) or {}
        return str(d.get("version") or "")
    except Exception:
        return ""


def existing_plugin_record(state_file: Path, plugin_id: str) -> dict | None:
    if not state_file.is_file():
        return None
    try:
        d = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    for r in d.get("installed_plugins") or []:
        if r.get("id") == plugin_id:
            return r
    return None


def install_plugin(
    *,
    repo_root: Path,
    workspace: Path,
    staged_kernel: Path,
    plugin_id: str,
    version: str,
    upgrade: bool,
    dry_run: bool,
) -> int:
    """Run the orchestrator for one plugin. Returns the orchestrator's
    exit code (0 ok, 1 gate failure, 2 IO/usage, 3 already installed).

    Implements the v0.13.x install.sh idempotency rule:
      - same version on disk → auto-promote to --upgrade and short-circuit
        (skip orchestrator, just refresh state.json).
      - different version on disk without --upgrade → exit 3.
    """
    plugin_src = repo_root / "plugins" / plugin_id
    if not plugin_src.is_dir():
        sys.stderr.write(f"install: plugin source not found: {plugin_src}\n")
        return 2

    state_file = workspace / ".codenook" / "state.json"
    new_version = version or read_plugin_version(plugin_src)
    existing = existing_plugin_record(state_file, plugin_id)
    existing_version = (existing or {}).get("version") or ""

    idempotent = False
    effective_upgrade = upgrade
    if existing_version and existing_version == new_version:
        effective_upgrade = True
        idempotent = True
    elif existing_version and existing_version != new_version and not upgrade:
        sys.stderr.write(
            f"install: plugin '{plugin_id}' is installed at v{existing_version}; "
            f"this source is v{new_version}\n"
            f"         re-run with --upgrade to perform the version bump\n"
        )
        return 3

    # Content-fingerprint check: VERSION-only short-circuit silently drops
    # in-version edits to plugin files (role.md, phases.yaml, …). If the
    # staged tree's ``.fingerprint`` is missing or stale relative to the
    # source, fall through to a full restage so dev-loop edits land.
    plugin_dst = workspace / ".codenook" / "plugins" / plugin_id
    if idempotent:
        fp_path = plugin_dst / _FINGERPRINT_NAME
        staged_fp = ""
        if fp_path.is_file():
            try:
                staged_fp = fp_path.read_text(encoding="utf-8").strip()
            except Exception:
                staged_fp = ""
        if not staged_fp or staged_fp != _compute_tree_fingerprint(plugin_src):
            idempotent = False

    builtin_dir = staged_kernel / "skills" / "builtin"
    core_version = (staged_kernel / "VERSION").read_text(encoding="utf-8").strip()

    if idempotent and not dry_run:
        # Short-circuit: same version already on disk. Refresh state.json
        # with the v0.11.3 schema fields (kernel_version, kernel_dir, …)
        # via the orchestrator's update_state_json helper.
        sys.path.insert(0, str(builtin_dir / "install-orchestrator"))
        sys.path.insert(0, str(builtin_dir / "_lib"))
        try:
            import _orchestrator as orch  # type: ignore
        except ImportError as e:
            sys.stderr.write(f"install: orchestrator import failed: {e}\n")
            return 1
        try:
            sha = orch._aggregate_files_sha256(
                workspace / ".codenook" / "plugins" / plugin_id)
        except Exception:
            sha = ""
        try:
            orch.update_state_json(
                workspace, plugin_id, new_version,
                kernel_version=core_version,
                kernel_dir=str(builtin_dir),
                files_sha256=sha,
            )
        except Exception as e:
            sys.stderr.write(f"install: update_state_json failed: {e}\n")
            return 1
        sys.stdout.write(
            f"  ↻ already installed (idempotent): plugin {plugin_id} "
            f"v{new_version}\n"
        )
        return 0

    helper = builtin_dir / "install-orchestrator" / "_orchestrator.py"
    if not helper.is_file():
        sys.stderr.write(f"install: orchestrator missing: {helper}\n")
        return 2

    env = os.environ.copy()
    env["CN_SRC"] = str(plugin_src)
    env["CN_WORKSPACE"] = str(workspace)
    env["CN_UPGRADE"] = "1" if effective_upgrade else "0"
    env["CN_DRY_RUN"] = "1" if dry_run else "0"
    env["CN_JSON"] = "0"
    env["CN_REQUIRE_SIG"] = os.environ.get("CODENOOK_REQUIRE_SIG", "0")
    env["CN_BUILTIN_DIR"] = str(builtin_dir)
    env["CN_CORE_VERSION"] = core_version
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(builtin_dir / "_lib") + (os.pathsep + pp if pp else "")
    )

    cp = subprocess.run(
        [sys.executable, str(helper)],
        env=env,
        text=True,
    )
    if cp.returncode == 0 and not dry_run:
        # Write content fingerprint into the staged plugin tree so the
        # next install can detect in-version source edits and restage.
        try:
            fp = _compute_tree_fingerprint(plugin_src)
            (plugin_dst / _FINGERPRINT_NAME).write_text(
                fp + "\n", encoding="utf-8"
            )
        except Exception as e:
            sys.stderr.write(
                f"install: warning: failed to write plugin fingerprint: {e}\n"
            )
    return cp.returncode
