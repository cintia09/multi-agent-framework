"""Stage the codenook-core kernel into ``<ws>/.codenook/codenook-core``.

Replaces ``skills/codenook-core/init.sh`` and the inline VERSION-compare
+ atomic-rename logic that used to live there.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

# What we never copy into the staged kernel.
_EXCLUDE_DIRS = {"tests", "__pycache__", ".pytest_cache"}
_EXCLUDE_SUFFIXES = (".pyc",)

# Name of the per-install content fingerprint file written into ``dst``.
# Used to detect in-version source edits that VERSION alone would miss.
_FINGERPRINT_NAME = ".fingerprint"


def _ignore(_dir: str, names: list[str]) -> set[str]:
    out: set[str] = set()
    for n in names:
        if n in _EXCLUDE_DIRS or n.endswith(_EXCLUDE_SUFFIXES):
            out.add(n)
    return out


def _read_version(p: Path) -> str:
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return ""


def _iter_source_files(src: Path):
    """Yield (relative_posix_path, absolute_path) for every file under
    ``src`` that ``stage_kernel`` would copy (mirrors ``_ignore`` rules
    and the ``_EXCLUDE_DIRS`` skip at the top level).
    """
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(d for d in dirnames if d not in _EXCLUDE_DIRS)
        rel_dir = Path(dirpath).relative_to(src)
        for name in sorted(filenames):
            if name in _EXCLUDE_DIRS or name.endswith(_EXCLUDE_SUFFIXES):
                continue
            rel = (rel_dir / name).as_posix()
            yield rel, Path(dirpath) / name


def _compute_tree_fingerprint(src: Path) -> str:
    """SHA256 of a deterministic listing of ``src`` files: each line is
    ``<sorted relative posix path> <sha256 of contents>``. Any in-version
    edit (add / remove / modify) flips the digest.
    """
    h = hashlib.sha256()
    for rel, abs_path in _iter_source_files(src):
        try:
            file_hash = hashlib.sha256(abs_path.read_bytes()).hexdigest()
        except OSError:
            file_hash = "missing"
        h.update(f"{rel} {file_hash}\n".encode("utf-8"))
    return h.hexdigest()


def stage_kernel(core_src: Path, workspace: Path) -> Path:
    """Copy ``<core_src>/*`` (minus tests/) into
    ``<workspace>/.codenook/codenook-core/``.

    Idempotent: skips re-staging only when both the staged ``VERSION``
    file matches ``<core_src>/VERSION`` AND the staged ``.fingerprint``
    matches a freshly-computed content hash of the source tree. The
    fingerprint check catches in-version source edits (the dev-loop
    case) that a VERSION-only check would silently drop. A missing
    ``.fingerprint`` is treated as a mismatch so the first upgrade
    onto this scheme always restages once.

    Returns the staged kernel root.
    """
    dst = workspace / ".codenook" / "codenook-core"
    src_version = _read_version(core_src / "VERSION")
    dst_version = _read_version(dst / "VERSION")

    if dst.is_dir() and dst_version and dst_version == src_version:
        fp_path = dst / _FINGERPRINT_NAME
        if fp_path.is_file():
            try:
                staged_fp = fp_path.read_text(encoding="utf-8").strip()
            except Exception:
                staged_fp = ""
            if staged_fp and staged_fp == _compute_tree_fingerprint(core_src):
                return dst
        # else: fall through to restage (missing or stale fingerprint)

    parent = dst.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".codenook-core.", dir=str(parent)))
    try:
        for entry in os.listdir(core_src):
            if entry in _EXCLUDE_DIRS:
                continue
            s = core_src / entry
            d = staging / entry
            if s.is_dir():
                shutil.copytree(s, d, ignore=_ignore, symlinks=False)
            else:
                shutil.copy2(s, d)

        # Write fingerprint into the staged tree before swap so the
        # final ``dst`` always has a fingerprint matching its contents.
        fp = _compute_tree_fingerprint(core_src)
        (staging / _FINGERPRINT_NAME).write_text(fp + "\n", encoding="utf-8")

        if dst.is_dir():
            backup = dst.with_name(dst.name + ".old")
            if backup.is_dir():
                shutil.rmtree(backup, ignore_errors=True)
            os.replace(dst, backup)
            os.replace(staging, dst)
            shutil.rmtree(backup, ignore_errors=True)
        else:
            os.replace(staging, dst)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return dst


def init_memory_skeleton(workspace: Path) -> None:
    """Create the ``.codenook/memory`` skeleton and gitignore stubs."""
    mem = workspace / ".codenook" / "memory"
    for sub in ("knowledge", "skills", "history"):
        (mem / sub).mkdir(parents=True, exist_ok=True)
        gk = mem / sub / ".gitkeep"
        if not gk.is_file():
            gk.write_text("", encoding="utf-8")

    gi = mem / ".gitignore"
    _append_unique(gi, ".index-snapshot.json")

    tasks = workspace / ".codenook" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    _append_unique(tasks / ".gitignore", ".chain-snapshot.json")


def _append_unique(path: Path, line: str) -> None:
    line = line.rstrip("\n")
    if not path.is_file():
        path.write_text(line + "\n", encoding="utf-8")
        return
    existing = [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8").splitlines()]
    if line in existing:
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
