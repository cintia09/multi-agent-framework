"""Discovery helpers over plugin-shipped knowledge documents.

The router-agent uses this module to enumerate ``knowledge/**/*.md``
files shipped with each installed plugin so it can decide which short
summaries to ground its draft on. Bodies are intentionally NOT read
beyond what's needed to materialise an implicit summary — see
``docs/router-agent.md`` §7 for the per-turn cap on full-body fetches.

Public API
----------
- :func:`discover_knowledge`  — recursive scan of one plugin's ``knowledge/``.
- :func:`aggregate_knowledge` — plugin_name → discover_knowledge output.
- :func:`find_relevant`       — score + rank against a query string.

Frontmatter shape
-----------------
Each ``.md`` file MAY start with a YAML frontmatter block delimited by
``---`` lines:

    ---
    title: CLI flag conventions
    summary: Long flags use --kebab-case; short flags reserved for the top 8.
    tags: [cli, argparse]
    ---

Files without frontmatter are still listed. Missing fields are filled
in by the resolution chain (highest wins):

1. The file's own frontmatter.
2. ``knowledge/INDEX.yaml`` entry whose ``path`` matches.
3. ``knowledge/INDEX.md`` entry parsed from a top-level bullet list of
   ``- [Title](relative/path.md) — summary`` lines.
4. Implicit-from-path fallback: ``title`` from filename stem, ``tags``
   from parent directory names relative to ``knowledge/``, ``summary``
   from the body's first H1/H2 or paragraph (Markdown links/images
   stripped, truncated to ~200 chars).

INDEX overrides apply only to fields that are missing from the file's
frontmatter; explicit frontmatter values always win.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


KNOWLEDGE_DIRNAME = "knowledge"
PLUGINS_DIRNAME = "plugins"
INDEX_YAML_NAME = "INDEX.yaml"
INDEX_MD_NAME = "INDEX.md"
SUMMARY_MAX_CHARS = 200

# T-006 §2.4 / fix-pass 1: a knowledge entry has exactly one canonical
# descriptor file per slug. Legacy ``entry.md`` / ``case.md`` siblings
# left behind by older migrations are intentionally ignored so the
# walker cannot surface the same entry twice. The accepted shapes are:
#   - ``<root>/<slug>/index.md`` (sub-directory entry, T-006 contract)
#   - ``<root>/<slug>.md`` (legacy flat short form, still in use under
#     ``memory/knowledge/`` for one-shot extracted notes)
#   - ``<root>/<slug>/SKILL.md`` (skill descriptor — included so callers
#     that point _walk_md_files at a ``skills/`` tree still work)
# Top-level ``INDEX.md`` / ``INDEX.yaml`` are handled separately by
# :func:`_load_index_yaml` / :func:`_load_index_md`.
_CANONICAL_DESCRIPTOR_NAMES: frozenset[str] = frozenset({"index.md", "SKILL.md"})

_SKIP_DIRS: frozenset[str] = frozenset({
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".venv",
    "venv",
    ".git",
    ".svn",
    ".hg",
    ".idea",
    ".vscode",
})


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return ``(frontmatter_dict, body)``. Empty dict if absent/invalid."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return {}, text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text
    raw = "".join(lines[1:end_idx])
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    body = "".join(lines[end_idx + 1 :])
    return data, body


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [t.strip() for t in raw if isinstance(t, str) and t.strip()]


def _should_skip_dir(name: str) -> bool:
    if name in _SKIP_DIRS:
        return True
    if name.startswith(".") and name not in (".",):
        return True
    return False


def _walk_md_files(root: Path):
    """Yield canonical descriptor ``*.md`` files under ``root``.

    Per T-006 §2.4 every knowledge / skill entity owns exactly one
    descriptor file. The walker honours that contract so legacy
    siblings (``entry.md`` next to ``index.md``, ``case.md`` next to
    ``index.md``) cannot register a second hit.

    Yielded shapes:
      * ``<root>/<slug>/index.md`` — knowledge sub-directory entry.
      * ``<root>/<slug>/SKILL.md`` — skill descriptor (preserved for
        callers that point the walker at a ``skills/`` tree).
      * ``<root>/<slug>.md`` — legacy flat short-form note (still used
        under ``memory/knowledge/`` for one-shot extracted entries).

    Top-level ``INDEX.md`` / ``INDEX.yaml`` at ``root`` are also
    yielded so :func:`discover_knowledge` can carve them out itself
    (preserves the long-standing override behaviour).
    """
    if not root.is_dir():
        return
    stack: list[Path] = [root]
    while stack:
        cur = stack.pop()
        try:
            entries = sorted(cur.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        is_root = cur.resolve() == root.resolve()
        for e in entries:
            if e.is_dir():
                if _should_skip_dir(e.name):
                    continue
                stack.append(e)
                continue
            if not e.is_file():
                continue
            if e.suffix.lower() != ".md":
                continue
            name = e.name
            if is_root:
                # Allow the legacy flat short form (``<slug>.md`` directly
                # under the root) plus the top-level INDEX.md override
                # marker. discover_knowledge filters INDEX.md out.
                yield e
                continue
            if name in _CANONICAL_DESCRIPTOR_NAMES:
                yield e


_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_MD_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")


def _strip_markdown(s: str) -> str:
    """Strip image / link syntax and inline emphasis for cleaner summaries."""
    s = _MD_IMG_RE.sub(r"\1", s)
    s = _MD_LINK_RE.sub(r"\1", s)
    s = re.sub(r"`+", "", s)
    s = re.sub(r"\*\*|__|\*|_", "", s)
    return s.strip()


def _truncate(s: str, n: int = SUMMARY_MAX_CHARS) -> str:
    s = " ".join(s.split())
    if len(s) <= n:
        return s
    cut = s[: n - 1].rstrip()
    return cut + "…"


def _summary_from_body(body: str) -> str:
    """Pick a short summary from the body.

    Priority:
      1. First H1/H2 heading text.
      2. First non-empty paragraph (collapsed whitespace).
    Markdown link/image syntax is stripped. Result is truncated to
    ``SUMMARY_MAX_CHARS``.
    """
    if not body:
        return ""
    # First pass — H1/H2 line.
    for raw in body.splitlines():
        m = _HEADING_RE.match(raw)
        if m and len(m.group(1)) <= 2:
            return _truncate(_strip_markdown(m.group(2)))
    # Second pass — first non-empty paragraph (skip pure heading / fence
    # / blockquote / list-marker noise that wasn't picked up above).
    paragraph: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            if paragraph:
                break
            continue
        if line.startswith("```") or line.startswith("~~~"):
            if paragraph:
                break
            continue
        paragraph.append(line)
    if not paragraph:
        return ""
    text = " ".join(paragraph)
    return _truncate(_strip_markdown(text))


def _implicit_tags_from_path(rel_parts: tuple[str, ...]) -> list[str]:
    """Directory components (relative to ``knowledge/``) become tags."""
    return [p for p in rel_parts[:-1] if p]


def _resolve_index_dir_target(rel_dir: str, kdir: Path) -> Path | None:
    """Pick the primary md file inside ``kdir / rel_dir`` for INDEX entries.

    Heuristic:
      1. ``<dirname>.md``
      2. ``README.md``
      3. first ``*.md`` alphabetically
    """
    target = (kdir / rel_dir).resolve()
    try:
        target.relative_to(kdir.resolve())
    except ValueError:
        return None
    if not target.is_dir():
        return None
    base = target.name
    candidate = target / f"{base}.md"
    if candidate.is_file():
        return candidate
    readme = target / "README.md"
    if readme.is_file():
        return readme
    try:
        mds = sorted(p for p in target.iterdir() if p.is_file() and p.suffix.lower() == ".md")
    except OSError:
        mds = []
    return mds[0] if mds else None


def _load_index_yaml(kdir: Path) -> dict[str, dict]:
    """Parse ``knowledge/INDEX.yaml`` → ``{abs_path_str: override_dict}``."""
    p = kdir / INDEX_YAML_NAME
    if not p.is_file():
        return {}
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(raw, dict):
        return {}
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return {}
    out: dict[str, dict] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        rel = e.get("path")
        if not isinstance(rel, str) or not rel.strip():
            continue
        rel = rel.strip().lstrip("./").replace("\\", "/")
        target_path: Path | None
        if rel.endswith("/") or not rel.lower().endswith(".md"):
            target_path = _resolve_index_dir_target(rel.rstrip("/"), kdir)
        else:
            cand = (kdir / rel).resolve()
            try:
                cand.relative_to(kdir.resolve())
            except ValueError:
                continue
            target_path = cand if cand.is_file() else None
        if target_path is None:
            continue
        override: dict[str, Any] = {}
        if isinstance(e.get("title"), str) and e["title"].strip():
            override["title"] = e["title"].strip()
        if isinstance(e.get("summary"), str):
            override["summary"] = e["summary"].strip()
        if isinstance(e.get("tags"), list):
            override["tags"] = _str_list(e.get("tags"))
        if override:
            out[str(target_path)] = override
    return out


_INDEX_MD_LINE_RE = re.compile(
    r"^\s*[-*+]\s*\[(?P<title>[^\]]+)\]\((?P<href>[^)]+)\)"
    r"(?:\s*[—\-:]\s*(?P<summary>.+))?\s*$"
)


def _load_index_md(kdir: Path) -> dict[str, dict]:
    """Parse ``knowledge/INDEX.md`` bullet links → ``{abs_path: override}``."""
    p = kdir / INDEX_MD_NAME
    if not p.is_file():
        return {}
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, dict] = {}
    for raw in text.splitlines():
        m = _INDEX_MD_LINE_RE.match(raw)
        if not m:
            continue
        href = m.group("href").strip()
        if href.startswith(("http://", "https://", "#", "mailto:")):
            continue
        href = href.split("#", 1)[0].split("?", 1)[0]
        href = href.lstrip("./").replace("\\", "/")
        if href.endswith("/") or not href.lower().endswith(".md"):
            target = _resolve_index_dir_target(href.rstrip("/"), kdir)
        else:
            cand = (kdir / href).resolve()
            try:
                cand.relative_to(kdir.resolve())
            except ValueError:
                continue
            target = cand if cand.is_file() else None
        if target is None:
            continue
        override: dict[str, Any] = {"title": m.group("title").strip()}
        summ = m.group("summary")
        if summ:
            override["summary"] = _truncate(_strip_markdown(summ.strip()))
        out[str(target)] = override
    return out


def discover_knowledge(plugin_dir: Path) -> list[dict]:
    """Recursive scan of ``<plugin_dir>/knowledge/**/*.md``.

    Returns ``[{path, title, summary, tags}]`` sorted by ``path``.
    ``path`` is the absolute filesystem path as a string so the caller
    can fetch the body on demand. Missing ``knowledge/`` directory
    yields ``[]``.

    Skips dot-directories and noise like ``__pycache__`` /
    ``node_modules``. Frontmatter, INDEX.yaml, INDEX.md, and
    implicit-from-path defaults compose per the resolution chain
    documented in the module docstring.
    """
    plugin_dir = Path(plugin_dir)
    kdir = plugin_dir / KNOWLEDGE_DIRNAME
    if not kdir.is_dir():
        return []

    index_yaml = _load_index_yaml(kdir)
    index_md = _load_index_md(kdir)
    kdir_resolved = kdir.resolve()

    out: list[dict] = []
    for entry in _walk_md_files(kdir):
        # Don't list the INDEX files themselves.
        if entry.name in (INDEX_YAML_NAME, INDEX_MD_NAME) and entry.parent == kdir:
            continue
        try:
            text = entry.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body = _parse_frontmatter(text)

        try:
            rel = entry.resolve().relative_to(kdir_resolved)
        except ValueError:
            rel = Path(entry.name)
        rel_parts = rel.parts

        # Implicit defaults (lowest priority).
        title = entry.stem
        summary = _summary_from_body(body)
        tags = _implicit_tags_from_path(rel_parts)

        # INDEX.md (next).
        idx_md_o = index_md.get(str(entry.resolve()))
        if idx_md_o:
            if "title" in idx_md_o:
                title = idx_md_o["title"]
            if "summary" in idx_md_o:
                summary = idx_md_o["summary"]
            if "tags" in idx_md_o:
                tags = idx_md_o["tags"]

        # INDEX.yaml (next).
        idx_y_o = index_yaml.get(str(entry.resolve()))
        if idx_y_o:
            if "title" in idx_y_o:
                title = idx_y_o["title"]
            if "summary" in idx_y_o:
                summary = idx_y_o["summary"]
            if "tags" in idx_y_o:
                tags = idx_y_o["tags"]

        # Frontmatter (highest).
        fm_title = fm.get("title")
        if isinstance(fm_title, str) and fm_title.strip():
            title = fm_title.strip()
        fm_summary = fm.get("summary")
        if isinstance(fm_summary, str):
            summary = fm_summary.strip()
        if isinstance(fm.get("tags"), list):
            tags = _str_list(fm.get("tags"))

        out.append(
            {
                "path": str(entry),
                "title": title,
                "summary": summary,
                "tags": list(tags),
            }
        )

    out.sort(key=lambda r: r["path"])
    return out


def _plugin_dir_name_from_manifest(manifest_path: Path) -> str:
    """``plugins/<dir>/plugin.yaml`` → ``<dir>`` (the on-disk directory)."""
    return manifest_path.parent.name


def aggregate_knowledge(workspace_root: Path) -> dict[str, list[dict]]:
    """Discover knowledge for every installed plugin under ``workspace_root``.

    Returns ``{plugin_name: [knowledge_record, ...]}`` keyed by the
    plugin directory name (matches the on-disk identity used by
    discovery helpers). Plugins with no ``knowledge/`` directory yield
    an empty list. Missing top-level ``plugins/`` returns ``{}``.
    """
    workspace_root = Path(workspace_root)
    plugins_dir = workspace_root / PLUGINS_DIRNAME
    if not plugins_dir.is_dir():
        return {}
    out: dict[str, list[dict]] = {}
    for entry in sorted(plugins_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        out[entry.name] = discover_knowledge(entry)
    return out


def _score(record: dict, query: str) -> int:
    """Score a record against ``query`` (single token).

    Scoring weights (per token): +3 per tag substring hit, +2 per
    title hit, +1 per summary hit. The caller may split a multi-word
    query into tokens and sum.
    """
    q = query.lower()
    score = 0
    for tag in record.get("tags", []):
        if isinstance(tag, str) and q in tag.lower():
            score += 3
    title = record.get("title") or ""
    if isinstance(title, str) and q in title.lower():
        score += 2
    summary = record.get("summary") or ""
    if isinstance(summary, str) and q in summary.lower():
        score += 1
    return score


def _score_query(record: dict, query: str) -> int:
    """Score a (possibly multi-word) query.

    The full query is scored first (preserves the v0.20 single-token
    behaviour for short queries). For multi-word queries we *also*
    sum each whitespace-separated token's score so directory-derived
    tags like ``APHA`` and titles like ``APHA Startup Baseline``
    contribute even when the user typed ``"APHA baseline"`` rather
    than the exact substring.
    """
    q = query.strip()
    if not q:
        return 0
    score = _score(record, q)
    tokens = [t for t in q.split() if t]
    if len(tokens) > 1:
        for t in tokens:
            score += _score(record, t)
    return score


def find_relevant(
    query: str,
    aggregated: dict[str, list[dict]],
    limit: int = 5,
) -> list[dict]:
    """Rank knowledge records across plugins by simple substring score.

    Returns flat
    ``[{plugin, path, title, summary, tags, score}, ...]`` truncated
    to ``limit``. Records with score 0 are omitted. Stable secondary
    sort key is ``(plugin, path)`` so equal scores have deterministic
    order. Empty/blank ``query`` returns ``[]``.
    """
    if not query or not query.strip() or limit <= 0:
        return []
    candidates: list[dict] = []
    for plugin, records in aggregated.items():
        for rec in records:
            s = _score_query(rec, query)
            if s <= 0:
                continue
            candidates.append(
                {
                    "plugin": plugin,
                    "path": rec.get("path", ""),
                    "title": rec.get("title", ""),
                    "summary": rec.get("summary", ""),
                    "tags": list(rec.get("tags", [])),
                    "score": s,
                }
            )
    candidates.sort(key=lambda r: (-r["score"], r["plugin"], r["path"]))
    return candidates[:limit]
