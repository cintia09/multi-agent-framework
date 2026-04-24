#!/usr/bin/env python3
"""Gate G04 — plugin-version-check.  Uses _lib.semver.

Same-version policy:
  When ``--upgrade`` is asked against an installed plugin of the *same*
  version, we previously rejected with "would downgrade or no-op".
  This collides with the content-fingerprint short-circuit added in
  T-004 (stage_plugins.py): a dev-loop edit to a plugin file (e.g.
  appending a newline to a role.md) leaves ``plugin.yaml.version``
  unchanged but flips the staged ``.fingerprint``.  In that case
  ``stage_plugins`` correctly falls through to the orchestrator to
  restage; G04 must then *not* veto the same-version restage.

  Resolution: when the proposed and installed versions compare equal,
  read the staged ``.fingerprint``.  If it differs from a freshly
  computed source-tree fingerprint, treat the call as a legitimate
  same-version restage (no veto).  If the fingerprint matches,
  preserve the historical "would downgrade or no-op" rejection
  (idempotent fast-path is reported by ``stage_plugins`` instead).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from semver import parse, cmp_key  # noqa: E402

# stage_kernel owns the canonical fingerprint helpers; reuse them so the
# definition cannot drift.
_INSTALL_LIB = (
    Path(__file__).resolve().parents[3] / "_lib" / "install"
)
sys.path.insert(0, str(_INSTALL_LIB))
try:  # pragma: no cover - import wiring
    from stage_kernel import _FINGERPRINT_NAME, _compute_tree_fingerprint  # noqa: E402
except Exception:  # pragma: no cover - defensive
    _FINGERPRINT_NAME = ".fingerprint"
    _compute_tree_fingerprint = None  # type: ignore[assignment]

GATE = "plugin-version-check"


def main() -> int:
    src = Path(os.environ["CN_SRC"])
    workspace = os.environ.get("CN_WORKSPACE", "") or None
    upgrade = os.environ.get("CN_UPGRADE", "0") == "1"
    json_out = os.environ.get("CN_JSON", "0") == "1"
    reasons: list[str] = []

    pl = src / "plugin.yaml"
    try:
        plugin = yaml.safe_load(pl.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        reasons.append(f"cannot read plugin.yaml: {e}")
        return _emit(json_out, reasons)

    ver = plugin.get("version")
    if not isinstance(ver, str):
        reasons.append("plugin.yaml.version missing or not a string")
        return _emit(json_out, reasons)

    parsed = parse(ver)
    if parsed is None:
        reasons.append(f"version {ver!r} is not valid semver")
        return _emit(json_out, reasons)

    if upgrade and workspace:
        pid = plugin.get("id")
        if isinstance(pid, str):
            installed_yaml = (
                Path(workspace) / ".codenook" / "plugins" / pid / "plugin.yaml"
            )
            if installed_yaml.is_file():
                try:
                    inst = yaml.safe_load(
                        installed_yaml.read_text(encoding="utf-8")
                    ) or {}
                except yaml.YAMLError:
                    inst = {}
                inst_ver = inst.get("version")
                inst_parsed = parse(inst_ver) if isinstance(inst_ver, str) else None
                if inst_parsed and cmp_key(parsed) <= cmp_key(inst_parsed):
                    # Same-version restage carve-out: a missing or stale
                    # ``.fingerprint`` in the staged plugin tree means
                    # this is a dev-loop restage (not an idempotent
                    # repeat).  Allow it through; the idempotent fast-
                    # path in stage_plugins.py reports "↻ already
                    # installed" when the fingerprint *does* match.
                    # Strict downgrades (new < installed) are still
                    # vetoed unconditionally.
                    same_version = cmp_key(parsed) == cmp_key(inst_parsed)
                    fingerprint_mismatch = False
                    if same_version and _compute_tree_fingerprint is not None:
                        fp_path = (
                            Path(workspace) / ".codenook" / "plugins" / pid
                            / _FINGERPRINT_NAME
                        )
                        staged_fp = ""
                        if fp_path.is_file():
                            try:
                                staged_fp = fp_path.read_text(
                                    encoding="utf-8"
                                ).strip()
                            except Exception:
                                staged_fp = ""
                        try:
                            src_fp = _compute_tree_fingerprint(src)
                        except Exception:
                            src_fp = ""
                        # Missing staged fingerprint OR mismatch → treat
                        # as legitimate restage.  Only when both sides
                        # produce a fingerprint AND they match do we
                        # preserve the historical reject path.
                        if not staged_fp or not src_fp or staged_fp != src_fp:
                            fingerprint_mismatch = True
                    if not (same_version and fingerprint_mismatch):
                        reasons.append(
                            f"--upgrade rejected: would downgrade or no-op "
                            f"(installed={inst_ver}, new={ver})"
                        )

    return _emit(json_out, reasons)


def _emit(json_out: bool, reasons: list[str]) -> int:
    ok = not reasons
    if json_out:
        print(json.dumps({"ok": ok, "gate": GATE, "reasons": reasons}))
    else:
        for r in reasons:
            print(f"[G04] {r}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
