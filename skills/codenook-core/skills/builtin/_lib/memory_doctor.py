"""Diagnose (and optionally repair) workspace memory frontmatter.

Scans ``<ws>/.codenook/memory/knowledge/*.md`` and
``<ws>/.codenook/memory/skills/<name>/SKILL.md`` for frontmatter
issues that historically cause downstream tooling (index.yaml
generation, ``knowledge search``, memory_index.build_index) to crash
or silently drop entries. When ``repair=True`` the known-safe fixes
are written back in place, with a timestamped backup of each
modified file placed under
``<ws>/.codenook/memory/.repair-backup/<iso-timestamp>/``.

Plugin-shipped files under ``<ws>/.codenook/plugins/<id>/knowledge``
and ``<ws>/.codenook/plugins/<id>/skills`` are scanned read-only —
they belong to upstream plugin maintainers.

Public surface: :func:`diagnose` returning a structured report dict.
Keep business logic here; the CLI wrapper
(``_lib/cli/cmd_memory.py``) is a thin argparse around this.
"""
from __future__ import annotations

import datetime as _dt
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

try:  # Reuse the canonical helpers when the builtin lib is on sys.path.
    from knowledge_index import (  # type: ignore
        SUMMARY_MAX_CHARS,
        _parse_frontmatter,
        _strip_markdown,
        _summary_from_body,
    )
except ImportError:  # pragma: no cover — fallback used only in pure-import contexts
    SUMMARY_MAX_CHARS = 200

    def _parse_frontmatter(text: str) -> tuple[dict, str]:  # type: ignore[misc]
        if not text.startswith("---"):
            return {}, text
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != "---":
            return {}, text
        end = None
        for i in range(1, len(lines)):
            if lines[i].rstrip("\r\n") == "---":
                end = i
                break
        if end is None:
            return {}, text
        try:
            data = yaml.safe_load("".join(lines[1:end])) or {}
        except yaml.YAMLError:
            return {}, text
        if not isinstance(data, dict):
            return {}, text
        return data, "".join(lines[end + 1:])

    def _strip_markdown(s: str) -> str:  # type: ignore[misc]
        return s.strip()

    def _summary_from_body(body: str) -> str:  # type: ignore[misc]
        for raw in body.splitlines():
            line = raw.strip()
            if line:
                return line[:SUMMARY_MAX_CHARS]
        return ""


_H1_RE = re.compile(r"^\s{0,3}#\s+(.+?)\s*#*\s*$")


# ───────────────────────────────────────────────────────── discovery

def _workspace_memory(ws: Path) -> Path:
    return ws / ".codenook" / "memory"


def _plugins_root(ws: Path) -> Path:
    return ws / ".codenook" / "plugins"


def _iter_workspace_files(ws: Path) -> list[tuple[str, Path]]:
    """Return ``[(kind, path), ...]`` for workspace memory files.

    ``kind`` is ``"knowledge"`` or ``"skill"``.
    """
    mem = _workspace_memory(ws)
    out: list[tuple[str, Path]] = []
    kdir = mem / "knowledge"
    if kdir.is_dir():
        for p in sorted(kdir.iterdir()):
            if p.is_file() and p.suffix.lower() == ".md" and not p.name.startswith("."):
                out.append(("knowledge", p))
    sdir = mem / "skills"
    if sdir.is_dir():
        # Expected layout: skills/<name>/SKILL.md. Also flag any
        # stray skills/SKILL.md at the wrong level (warn only).
        stray = sdir / "SKILL.md"
        if stray.is_file():
            out.append(("skill-stray", stray))
        for sub in sorted(sdir.iterdir()):
            if not sub.is_dir() or sub.name.startswith("."):
                continue
            sm = sub / "SKILL.md"
            if sm.is_file():
                out.append(("skill", sm))
    return out


def _iter_plugin_files(ws: Path) -> list[tuple[str, str, Path]]:
    """Return ``[(plugin_id, kind, path), ...]`` for plugin files."""
    proot = _plugins_root(ws)
    out: list[tuple[str, str, Path]] = []
    if not proot.is_dir():
        return out
    for pdir in sorted(proot.iterdir()):
        if not pdir.is_dir() or pdir.name.startswith("."):
            continue
        pid = pdir.name
        kdir = pdir / "knowledge"
        if kdir.is_dir():
            for p in sorted(kdir.rglob("*.md")):
                if p.name in ("INDEX.yaml", "INDEX.md"):
                    continue
                out.append((pid, "knowledge", p))
        sdir = pdir / "skills"
        if sdir.is_dir():
            for sub in sorted(sdir.iterdir()):
                if not sub.is_dir():
                    continue
                sm = sub / "SKILL.md"
                if sm.is_file():
                    out.append((pid, "skill", sm))
    return out


# ───────────────────────────────────────────────────────── analysis

def _first_h1(body: str) -> str | None:
    for line in body.splitlines():
        m = _H1_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def _coerce_tags(raw: Any) -> tuple[list[str], list[str]]:
    """Return ``(tags_list, issues)`` — best-effort coercion.

    ``issues`` is a list of human-readable problem descriptions found
    in the input (empty when ``raw`` is already a clean list of str).
    """
    issues: list[str] = []
    if raw is None:
        issues.append("tags is null")
        return [], issues
    if isinstance(raw, str):
        issues.append(f"tags not a list (got: str {raw!r})")
        parts = [t.strip() for t in raw.split(",")]
        return [p for p in parts if p], issues
    if not isinstance(raw, list):
        issues.append(f"tags not a list (got: {type(raw).__name__})")
        return [str(raw)], issues
    out: list[str] = []
    had_non_string = False
    for t in raw:
        if isinstance(t, str):
            if t.strip():
                out.append(t.strip())
        else:
            had_non_string = True
            # Render datetime/int/etc. as a plain string.
            out.append(str(t))
    if had_non_string:
        issues.append("tags contains non-string items")
    return out, issues


def _stringify_fm_values(fm: dict) -> tuple[dict, list[str]]:
    """Return ``(new_fm, issues)`` with datetime values ISO-stringified."""
    issues: list[str] = []
    new_fm: dict = {}
    for k, v in fm.items():
        if isinstance(v, (_dt.datetime, _dt.date)):
            iso = v.isoformat()
            issues.append(f"{k} is {type(v).__name__}, should be string ('{iso}')")
            new_fm[k] = iso
        else:
            new_fm[k] = v
    return new_fm, issues


def _analyse_file(path: Path, *, kind: str) -> dict[str, Any]:
    """Inspect one memory file and return a diagnosis dict.

    Shape::

        {
          "path": str,
          "kind": "knowledge"|"skill"|"skill-stray",
          "issues": [str, ...],
          "fixes": {                # proposed repair actions
              "title": str|None,
              "summary": str|None,
              "tags": list[str]|None,
              "frontmatter_stringify": {key: iso_str, ...},
          },
          "no_frontmatter": bool,
        }
    """
    result: dict[str, Any] = {
        "path": str(path),
        "kind": kind,
        "issues": [],
        "fixes": {},
        "no_frontmatter": False,
    }

    if kind == "skill-stray":
        result["issues"].append(
            "SKILL.md at memory/skills/SKILL.md (expected memory/skills/<name>/SKILL.md)"
        )
        return result

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        result["issues"].append(f"cannot read file: {e}")
        return result

    # Re-parse without the _parse_frontmatter YAML-safety layer so we
    # can preserve datetime.date types; knowledge_index strips them
    # silently via yaml.safe_load, which is exactly what we need.
    fm: dict = {}
    body = text
    if text.startswith("---"):
        lines = text.splitlines(keepends=True)
        end = None
        for i in range(1, len(lines)):
            if lines[i].rstrip("\r\n") == "---":
                end = i
                break
        if end is None:
            result["no_frontmatter"] = True
            result["issues"].append("no frontmatter block (missing closing ---)")
            return result
        raw_fm = "".join(lines[1:end])
        try:
            data = yaml.safe_load(raw_fm) or {}
        except yaml.YAMLError as e:
            result["issues"].append(f"frontmatter YAML parse error: {e}")
            return result
        if not isinstance(data, dict):
            result["issues"].append("frontmatter YAML is not a mapping")
            return result
        fm = data
        body = "".join(lines[end + 1:])
    else:
        result["no_frontmatter"] = True
        result["issues"].append("no frontmatter block")
        return result

    # datetime.* frontmatter values (the bug that broke _scan_memory).
    stringified, dt_issues = _stringify_fm_values(fm)
    if dt_issues:
        result["issues"].extend(dt_issues)
        result["fixes"]["frontmatter_stringify"] = {
            k: v for k, v in stringified.items() if fm.get(k) != v
        }

    # Title
    title_key = "name" if kind == "skill" else "title"
    title = fm.get(title_key)
    if not (isinstance(title, str) and title.strip()):
        h1 = _first_h1(body)
        derived = h1 if h1 else path.stem
        result["issues"].append(f"{title_key} missing")
        result["fixes"]["title_key"] = title_key
        result["fixes"]["title"] = derived

    # Summary
    summary = fm.get("summary")
    if not (isinstance(summary, str) and summary.strip()):
        derived = _summary_from_body(body) or ""
        result["issues"].append("summary missing (empty string)")
        result["fixes"]["summary"] = derived

    # Tags
    if "tags" in fm:
        coerced, tag_issues = _coerce_tags(fm.get("tags"))
        if tag_issues:
            result["issues"].extend(tag_issues)
            result["fixes"]["tags"] = coerced
    # Missing `tags` is not an error — downstream treats it as [].

    return result


# ───────────────────────────────────────────────────────── repair

def _iso_timestamp() -> str:
    # Windows-safe: ':' is illegal in paths, so format without it.
    now = _dt.datetime.now(tz=_dt.timezone.utc)
    return now.strftime("%Y-%m-%dT%H-%M-%SZ")


def _backup_file(ws: Path, src: Path, stamp: str) -> Path:
    """Copy *src* into ``.repair-backup/<stamp>/<rel>``. Returns dest."""
    mem = _workspace_memory(ws)
    try:
        rel = src.resolve().relative_to(mem.resolve())
        dest = mem / ".repair-backup" / stamp / rel
    except ValueError:
        # Fall back to just the filename under the timestamp dir.
        dest = mem / ".repair-backup" / stamp / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def _serialise_frontmatter(fm: dict) -> str:
    """Dump frontmatter as ``---\\n<yaml>---\\n`` preserving str values."""
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n"


def _apply_repairs(ws: Path, diag: dict, stamp: str) -> list[str]:
    """Apply the fixes recorded in *diag* to disk.

    Returns a list of one-line descriptions of what was repaired.
    """
    path = Path(diag["path"])
    fixes = diag.get("fixes") or {}
    if not fixes:
        return []
    if diag.get("no_frontmatter"):
        # The spec is "warn only" for missing frontmatter — do not
        # synthesise a stub. Refuse to touch the file.
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.startswith("---"):
        return []
    lines = text.splitlines(keepends=True)
    end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end = i
            break
    if end is None:
        return []
    raw_fm = "".join(lines[1:end])
    try:
        fm = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(fm, dict):
        return []
    body = "".join(lines[end + 1:])

    actions: list[str] = []

    # 1. datetime → ISO string (must happen first so key order is preserved).
    dt_fixes = fixes.get("frontmatter_stringify") or {}
    for k, iso in dt_fixes.items():
        fm[k] = iso
        actions.append(f"stringified {k} → '{iso}'")

    # 2. title / name
    if "title_key" in fixes and "title" in fixes:
        key = fixes["title_key"]
        fm[key] = fixes["title"]
        actions.append(f"set {key} = {fixes['title']!r}")

    # 3. summary
    if "summary" in fixes:
        fm["summary"] = fixes["summary"]
        actions.append(f"set summary (len={len(fixes['summary'])})")

    # 4. tags coercion
    if "tags" in fixes:
        fm["tags"] = fixes["tags"]
        actions.append(f"coerced tags → {fixes['tags']!r}")

    if not actions:
        return []

    # Backup, then rewrite the file atomically.
    _backup_file(ws, path, stamp)
    new_text = _serialise_frontmatter(fm) + body
    path.write_text(new_text, encoding="utf-8")
    return actions


# ───────────────────────────────────────────────────────── public API

def diagnose(workspace: Path | str, *, repair: bool = False) -> dict[str, Any]:
    """Scan the workspace memory layer and return a structured report.

    When ``repair=True`` applies safe fixes to workspace files and
    records what was done under ``report["repaired"]``. Plugin files
    are always read-only.
    """
    ws = Path(workspace)
    report: dict[str, Any] = {
        "workspace": str(ws),
        "workspace_issues": [],
        "workspace_clean": 0,
        "plugin_issues": [],
        "repaired": [],
        "timestamp": _iso_timestamp(),
    }

    # Workspace files
    ws_files = _iter_workspace_files(ws)
    for kind, p in ws_files:
        diag = _analyse_file(p, kind=kind)
        if diag["issues"]:
            report["workspace_issues"].append(diag)
        else:
            report["workspace_clean"] += 1

    # Apply repairs after the read pass so diagnosis is stable.
    if repair and report["workspace_issues"]:
        stamp = report["timestamp"]
        for diag in report["workspace_issues"]:
            actions = _apply_repairs(ws, diag, stamp)
            if actions:
                report["repaired"].append(
                    {"path": diag["path"], "actions": actions}
                )

    # Plugin files — diagnose only.
    for pid, kind, p in _iter_plugin_files(ws):
        diag = _analyse_file(p, kind=kind)
        if diag["issues"]:
            diag["plugin"] = pid
            report["plugin_issues"].append(diag)

    return report


# ───────────────────────────────────────────────────────── text render

def render_report(report: dict, *, repaired: bool) -> str:
    """Render *report* for the human-readable doctor output."""
    lines: list[str] = []
    ws_mem = Path(report["workspace"]) / ".codenook" / "memory"
    lines.append(f"codenook memory doctor: scanning {ws_mem}...")
    lines.append("")

    clean = report.get("workspace_clean", 0)
    issues = report.get("workspace_issues") or []
    if clean:
        lines.append(f"✓ {clean} files clean")

    if issues:
        lines.append(f"⚠ {len(issues)} files need attention:")
        lines.append("")
        for diag in issues:
            rel = _short_path(report["workspace"], diag["path"])
            lines.append(f"  {rel}")
            for issue in diag["issues"]:
                lines.append(f"    - {issue}")
            lines.append("")

    plug_issues = report.get("plugin_issues") or []
    if plug_issues:
        lines.append("Plugin files (read-only; report upstream):")
        for diag in plug_issues:
            rel = _short_path(report["workspace"], diag["path"])
            pid = diag.get("plugin", "?")
            lines.append(f"  [{pid}] {rel}")
            for issue in diag["issues"]:
                lines.append(f"    - {issue}")
        lines.append("")

    repaired_list = report.get("repaired") or []
    if repaired:
        if repaired_list:
            lines.append(f"Repaired {len(repaired_list)} file(s):")
            for r in repaired_list:
                rel = _short_path(report["workspace"], r["path"])
                lines.append(f"  {rel}")
                for a in r["actions"]:
                    lines.append(f"    · {a}")
            backup_root = (
                ws_mem / ".repair-backup" / report["timestamp"]
            )
            lines.append(f"Backups written to: {backup_root}")
        else:
            lines.append("No files needed auto-repair.")
    else:
        if issues:
            repairable = sum(1 for d in issues if d.get("fixes"))
            if repairable:
                lines.append(
                    f"Run with --repair to auto-fix {repairable} issue(s) in memory/ files."
                )

    if not clean and not issues and not plug_issues:
        lines.append("No memory files found.")

    return "\n".join(lines).rstrip() + "\n"


def _short_path(workspace: str, path: str) -> str:
    try:
        return str(Path(path).relative_to(Path(workspace))).replace("\\", "/")
    except ValueError:
        return path
