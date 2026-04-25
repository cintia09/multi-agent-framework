#!/usr/bin/env python3
"""install-orchestrator — runs the 12-gate plugin install pipeline.

Inputs (env, set by orchestrator.sh):
  CN_SRC            tarball or directory
  CN_WORKSPACE      target workspace root
  CN_UPGRADE        "1" if --upgrade
  CN_DRY_RUN        "1" if --dry-run
  CN_JSON           "1" if --json (machine-readable summary on stdout)
  CN_REQUIRE_SIG    "1" propagated to plugin-signature gate
  CN_BUILTIN_DIR    absolute path to skills/codenook-core/skills/builtin
  CN_CORE_VERSION   contents of VERSION file (no whitespace)

Exit codes:
  0  installed (or dry-run pass)
  1  any gate failed
  2  usage / IO error
  3  G03 reported "already installed" without --upgrade
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from atomic import atomic_write_json  # noqa: E402
from sh_run import sh_run as _sh_run  # noqa: E402

GATE_SEQ = [
    ("G01", "plugin-format",          "_format_check.py",     False),
    ("G02", "plugin-schema",          "_schema_check.py",     False),
    ("G03", "plugin-id-validate",     "_id_validate.py",      True),
    ("G04", "plugin-version-check",   "_version_check.py",    True),
    ("G05", "plugin-signature",       "_signature_check.py",  False),
    ("G06", "plugin-deps-check",      "_deps_check.py",       False),
    ("G07", "plugin-subsystem-claim", "_subsystem_claim.py",  True),
    # G08 sec-audit handled inline below
    # G09 size handled inline below
    ("G10", "plugin-shebang-scan",    "_shebang_scan.py",     False),
    ("G11", "plugin-path-normalize",  "_path_normalize.py",   False),
]

MAX_TOTAL_BYTES = 10 * 1024 * 1024
MAX_FILE_BYTES = 1 * 1024 * 1024


def stage_source(src: Path, staging_root: Path) -> Path:
    """Copy/extract src into a fresh staging dir; return staged path."""
    staging_root.mkdir(parents=True, exist_ok=True)
    # Tighten staging-root mode to 0700 even if it pre-existed with looser
    # perms; closes a local information-disclosure window during install.
    try:
        os.chmod(staging_root, 0o700)
    except OSError:
        pass
    # mkdtemp creates the per-install staged dir with mode 0700 by default.
    dest = Path(tempfile.mkdtemp(dir=str(staging_root), prefix="stage-"))
    if src.is_dir():
        # copytree requires the dest to NOT exist; remove the empty mkdtemp
        # placeholder, then copy. Re-tighten perms after copy.
        dest.rmdir()
        shutil.copytree(src, dest, symlinks=True)
        try:
            os.chmod(dest, 0o700)
        except OSError:
            pass
        return dest
    if src.is_file() and (src.suffixes[-2:] == [".tar", ".gz"]
                          or src.suffix in (".tgz", ".gz")):
        # dest already exists (mkdtemp) with mode 0700.
        with tarfile.open(src, "r:gz") as tf:
            # safe extract: refuse absolute / .. members and dangerous
            # member kinds; also validate linkname for hard/symlinks.
            for m in tf.getmembers():
                if m.name.startswith("/") or ".." in Path(m.name).parts:
                    raise RuntimeError(f"unsafe tar member: {m.name}")
                if m.isdev() or m.ischr() or m.isblk() or m.isfifo():
                    raise RuntimeError(
                        f"unsafe tar member kind ({m.type!r}): {m.name}"
                    )
                if m.islnk() or m.issym():
                    ln = m.linkname or ""
                    if os.path.isabs(ln) or ".." in Path(ln).parts:
                        raise RuntimeError(
                            f"unsafe tar linkname for {m.name!r}: {ln!r}"
                        )
            if sys.version_info >= (3, 12):
                tf.extractall(dest, filter="data")
            else:
                tf.extractall(dest)
        # If the tarball contains a single top-level directory, descend
        # into it so plugin.yaml is at the staged root.
        entries = [p for p in dest.iterdir()]
        if len(entries) == 1 and entries[0].is_dir():
            inner = entries[0]
            for child in inner.iterdir():
                shutil.move(str(child), str(dest / child.name))
            inner.rmdir()
        return dest
    # Unsupported source: clean up the empty placeholder mkdtemp dir.
    try:
        dest.rmdir()
    except OSError:
        pass
    raise RuntimeError(f"unsupported --src kind: {src}")


def run_gate(gate_py: Path, staged: Path, workspace: Path,
             upgrade: bool, extra_env: dict | None = None,
             ws_aware: bool = False) -> dict:
    """v0.24.0: invoke the gate's Python module directly via
    ``[sys.executable, _<name>.py]`` with the same CN_* env contract
    the .sh wrapper used to set. No bash subprocess required."""
    gate_dir = gate_py.parent
    env = os.environ.copy()
    env["CN_SRC"] = str(staged)
    env["CN_JSON"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if ws_aware:
        env["CN_WORKSPACE"] = str(workspace)
        env["CN_UPGRADE"] = "1" if upgrade else "0"
    # Per-gate extras that the .sh wrappers used to materialise:
    if gate_dir.name == "plugin-schema":
        env["CN_SCHEMA"] = str(gate_dir / "plugin-schema.yaml")
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, str(gate_py)],
        env=env, capture_output=True, text=True,
    )
    try:
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        out = {"ok": False, "gate": gate_dir.name,
               "reasons": [f"gate did not emit JSON (stderr={proc.stderr!r})"]}
    return out


def run_sec_audit(builtin_dir: Path, staged: Path) -> dict:
    audit_py = builtin_dir / "sec-audit" / "_audit.py"
    env = os.environ.copy()
    env["CN_WORKSPACE"] = str(staged)
    env["CN_JSON"] = "1"
    env["CN_PATTERNS"] = str(builtin_dir / "sec-audit" / "patterns.txt")
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, str(audit_py)],
        env=env, capture_output=True, text=True,
    )
    reasons: list[str] = []
    # sec-audit emits {"ok": bool, "findings": [...]} on stdout when --json.
    parsed: dict | None = None
    try:
        parsed = json.loads(proc.stdout)
    except (ValueError, TypeError):
        parsed = None
    if parsed is not None and isinstance(parsed.get("findings"), list):
        for f in parsed["findings"]:
            if not isinstance(f, dict):
                continue
            t = f.get("type", "?")
            p = f.get("path", "?")
            if t == "secret":
                reasons.append(f"secret match at {p}:{f.get('line', '?')}")
            elif t == "permission":
                reasons.append(
                    f"{p} mode {f.get('mode')} (expected {f.get('expected')})"
                )
            elif t == "world-writable":
                reasons.append(f"world-writable {p} mode {f.get('mode')}")
            else:
                reasons.append(f"{t}: {p}")
    elif proc.returncode == 1:
        # Fallback: JSON unparseable but sec-audit reported findings.
        reasons.append("sec-audit reported findings (no detail captured)")
    if proc.returncode >= 2:
        # Diagnostics-only: stderr captures runtime errors.
        diag = proc.stderr.strip() or "(no stderr)"
        reasons.append(
            f"sec-audit failed to run (exit {proc.returncode}): {diag}"
        )
    return {"ok": not reasons, "gate": "sec-audit", "reasons": reasons}


def check_size(staged: Path) -> dict:
    reasons: list[str] = []
    total = 0
    for root, _, files in os.walk(staged, followlinks=False):
        for n in files:
            p = Path(root) / n
            if p.is_symlink():
                continue
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            total += sz
            if sz > MAX_FILE_BYTES:
                reasons.append(
                    f"file {p.relative_to(staged)} is {sz} bytes "
                    f"(> {MAX_FILE_BYTES} per-file limit)"
                )
    if total > MAX_TOTAL_BYTES:
        reasons.append(
            f"total size {total} bytes > {MAX_TOTAL_BYTES} (10MB) limit"
        )
    return {"ok": not reasons, "gate": "size", "reasons": reasons}


def commit(staged: Path, workspace: Path, plugin_id: str,
           upgrade: bool) -> None:
    plugins_root = workspace / ".codenook" / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)
    dest = plugins_root / plugin_id

    # Pre-flight: staged dir must live under workspace's .codenook so the
    # upcoming os.replace stays on the same filesystem.
    staged_resolved = Path(staged).resolve()
    expected_stage_root = (workspace / ".codenook" / "staging").resolve()
    if staged_resolved.parent != expected_stage_root:
        raise RuntimeError(
            f"refusing to commit: staged path {staged_resolved} not under "
            f"expected staging root {expected_stage_root}"
        )

    if dest.exists() and not upgrade:
        raise RuntimeError(
            f"destination {dest} exists and --upgrade not set"
        )

    # Test hook: simulate a replace failure to exercise rollback.
    fail_replace = os.environ.get("CODENOOK_TEST_FAIL_REPLACE") == "1"

    backup: Path | None = None
    if dest.exists():
        backup = dest.with_name(dest.name + ".bak-" + secrets.token_hex(4))
        os.rename(dest, backup)
    try:
        if fail_replace:
            raise RuntimeError("simulated replace failure (test hook)")
        os.replace(staged, dest)
    except Exception:
        # Roll back: restore the backup if dest is empty (replace failed
        # before consuming the rename).
        if backup is not None and not dest.exists():
            try:
                os.rename(backup, dest)
            except OSError:
                pass
        raise
    else:
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)


def _aggregate_files_sha256(staged: Path) -> str:
    """Aggregate sha256 of all regular files under `staged` (sorted)."""
    import hashlib
    h = hashlib.sha256()
    base = Path(staged).resolve()
    files = []
    for root, _, names in os.walk(base, followlinks=False):
        for n in names:
            p = Path(root) / n
            if p.is_symlink() or not p.is_file():
                continue
            files.append(p)
    for p in sorted(files, key=lambda x: x.relative_to(base).as_posix()):
        rel = p.relative_to(base).as_posix().encode("utf-8")
        h.update(b"\0path:" + rel + b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            pass
    return h.hexdigest()


def update_state_json(workspace: Path, plugin_id: str, version: str,
                      *, kernel_version: str = "",
                      kernel_dir: str = "",
                      files_sha256: str = "") -> None:
    sj = workspace / ".codenook" / "state.json"
    if sj.is_file():
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}

    now_iso = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    installs = data.get("installed_plugins")
    if not isinstance(installs, list):
        installs = []
    # Backward-compat: keep prior records, drop any duplicate id.
    installs = [r for r in installs
                if not (isinstance(r, dict) and r.get("id") == plugin_id)]
    entry = {
        "id": plugin_id,
        "version": version,
        "installed_at": now_iso,
    }
    if files_sha256:
        entry["files_sha256"] = files_sha256
    installs.append(entry)

    # E2E-019: enrich workspace state.json schema (v1).
    data["schema_version"] = "v1"
    if kernel_version:
        data["kernel_version"] = kernel_version
    data["installed_at"] = now_iso
    if kernel_dir:
        data["kernel_dir"] = kernel_dir
    data.setdefault("bin", ".codenook/bin/codenook")
    data["installed_plugins"] = installs

    sj.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(sj), data)


def emit(json_out: bool, ok: bool, plugin_id: str | None, version: str | None,
         results: list[dict], dry_run: bool, exit_code: int) -> int:
    if json_out:
        print(json.dumps({
            "ok": ok,
            "plugin_id": plugin_id,
            "version": version,
            "dry_run": dry_run,
            "gate_results": results,
        }))
    else:
        for r in results:
            if not r.get("ok"):
                gate = r.get("gate", "?")
                code_map = {
                    "plugin-format": "G01",
                    "plugin-schema": "G02",
                    "plugin-id-validate": "G03",
                    "plugin-version-check": "G04",
                    "plugin-signature": "G05",
                    "plugin-deps-check": "G06",
                    "plugin-subsystem-claim": "G07",
                    "sec-audit": "G08",
                    "size": "G09",
                    "plugin-shebang-scan": "G10",
                    "plugin-path-normalize": "G11",
                }
                code = code_map.get(gate, "Gxx")
                for reason in r.get("reasons", []):
                    text = reason if reason.startswith(f"[{code}]") \
                        else f"[{code}] {reason}"
                    print(text, file=sys.stderr)
        if ok:
            tag = "DRY-RUN OK" if dry_run else "INSTALLED"
            print(f"✓ {tag}: plugin {plugin_id} {version or ''}".rstrip(),
                  file=sys.stderr)
    return exit_code


def main() -> int:
    src = Path(os.environ["CN_SRC"])
    workspace = Path(os.environ["CN_WORKSPACE"]).resolve()
    upgrade = os.environ.get("CN_UPGRADE", "0") == "1"
    dry_run = os.environ.get("CN_DRY_RUN", "0") == "1"
    json_out = os.environ.get("CN_JSON", "0") == "1"
    require_sig = os.environ.get("CN_REQUIRE_SIG", "0") == "1"
    builtin_dir = Path(os.environ["CN_BUILTIN_DIR"]).resolve()
    core_version = os.environ.get("CN_CORE_VERSION", "")
    kernel_dir = str(builtin_dir)

    if not src.exists():
        print(f"orchestrator: --src not found: {src}", file=sys.stderr)
        return 2

    staging_root = workspace / ".codenook" / "staging"
    try:
        staged = stage_source(src, staging_root)
    except Exception as e:
        print(f"orchestrator: failed to stage source: {e}", file=sys.stderr)
        return 2

    results: list[dict] = []
    plugin_id: str | None = None
    version: str | None = None

    try:
        # Try to read plugin.yaml early (best-effort, used for reporting only).
        pl = staged / "plugin.yaml"
        if pl.is_file():
            try:
                doc = yaml.safe_load(pl.read_text(encoding="utf-8")) or {}
                if isinstance(doc, dict):
                    plugin_id = doc.get("id") if isinstance(doc.get("id"), str) else None
                    version = doc.get("version") if isinstance(doc.get("version"), str) else None
            except yaml.YAMLError:
                pass

        extra_env = {"CODENOOK_REQUIRE_SIG": "1"} if require_sig else {}

        # G01..G07, then G10/G11 — runs gate skills via subprocess.
        early = [g for g in GATE_SEQ if g[0] in ("G01", "G02", "G03", "G04",
                                                  "G05", "G06", "G07")]
        late = [g for g in GATE_SEQ if g[0] in ("G10", "G11")]
        for code, name, sh, ws_aware in early:
            gate_py = builtin_dir / name / sh
            env = extra_env if name == "plugin-signature" else None
            results.append(run_gate(gate_py, staged, workspace, upgrade,
                                    extra_env=env, ws_aware=ws_aware))

        # G08 sec-audit
        results.append(run_sec_audit(builtin_dir, staged))
        # G09 size
        results.append(check_size(staged))

        for code, name, sh, ws_aware in late:
            gate_py = builtin_dir / name / sh
            results.append(run_gate(gate_py, staged, workspace, upgrade,
                                    ws_aware=ws_aware))

        failed = [r for r in results if not r.get("ok")]
        if failed:
            # Promote G03 "already installed" to exit 3 when --upgrade absent.
            if not upgrade:
                for r in failed:
                    if r.get("gate") == "plugin-id-validate":
                        # Prefer the structured code; keep substring fallback
                        # for one release for older plugin-id-validate builds.
                        # TODO(0.3.0): drop the substring fallback.
                        already = (
                            r.get("code") == "already_installed"
                            or any("already installed" in s
                                   for s in r.get("reasons", []))
                        )
                        if already:
                            return emit(json_out, False, plugin_id, version,
                                        results, dry_run, 3)
            return emit(json_out, False, plugin_id, version, results, dry_run, 1)

        if dry_run:
            return emit(json_out, True, plugin_id, version, results, dry_run, 0)

        # G12 commit
        try:
            if not plugin_id:
                raise RuntimeError("plugin id missing after gates passed (bug)")
            files_sha256 = _aggregate_files_sha256(staged)
            commit(staged, workspace, plugin_id, upgrade)
            # commit() consumed `staged` via os.replace; mark consumed so the
            # finally block doesn't try to rmtree the now-installed plugin dir.
            staged = None
            try:
                update_state_json(workspace, plugin_id, version or "",
                                  kernel_version=core_version,
                                  kernel_dir=kernel_dir,
                                  files_sha256=files_sha256)
            except Exception as state_exc:
                # v0.29.10 — rollback. The plugin files are already on
                # disk under .codenook/plugins/<id> but state.json never
                # learned about them. Remove the orphaned tree so the
                # workspace is consistent (no entry, no files) and a
                # retry can re-install cleanly.
                try:
                    plugin_dst = workspace / ".codenook" / "plugins" / plugin_id
                    if plugin_dst.exists():
                        shutil.rmtree(plugin_dst, ignore_errors=True)
                except Exception:
                    pass
                raise RuntimeError(
                    f"state.json update failed after commit: {state_exc} "
                    f"(rolled back files for {plugin_id})"
                ) from state_exc
        except Exception as e:
            commit_result = {"ok": False, "gate": "commit",
                             "reasons": [f"commit failed: {e}"]}
            results.append(commit_result)
            return emit(json_out, False, plugin_id, version, results, dry_run, 1)

        return emit(json_out, True, plugin_id, version, results, dry_run, 0)
    finally:
        if staged is not None:
            shutil.rmtree(staged, ignore_errors=True)
        _cleanup_staging_root(staging_root)


def _cleanup_staging_root(staging_root: Path) -> None:
    try:
        if staging_root.exists() and not any(staging_root.iterdir()):
            staging_root.rmdir()
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
