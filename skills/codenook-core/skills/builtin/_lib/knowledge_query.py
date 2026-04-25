"""``find_relevant`` — kernel-side knowledge retrieval (v0.22.0).

Public API
----------
:func:`find_relevant` — given a free-form query (plus optional role /
phase / plugin context), rank entries from
``<ws>/.codenook/memory/index.yaml`` and return the top-N hits.

Used by ``orchestrator-tick`` and ``codenook tick`` to substitute
``{{KNOWLEDGE_HITS}}`` placeholders in plugin manifest templates.
External callers (skills, conductors, future router passes) may import
the same module to ground themselves on the same ranking.

Behaviour
---------
* Reads ``<ws>/.codenook/memory/index.yaml`` (built by v0.21.0
  ``codenook knowledge reindex``).
* Falls back to a transient in-memory scan via
  :func:`knowledge_index.aggregate_knowledge` when the index is
  missing — so a freshly-installed workspace still works.
* Pure read; no side effects; idempotent.

Scoring
-------
Token-overlap scoring of the query against each entry's tags
(weight ×3) + summary (×1) + path segments (×0.5). A match against
the entry's ``plugin`` (when ``plugin=`` is specified) adds a +1
bias once. Returns at most ``top_n`` entries with score > 0.

Each hit carries a ``reason`` string explaining the dominant match
contributors so downstream prompts can show *why* an entry was picked.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import yaml


CODENOOK_DIRNAME = ".codenook"
MEMORY_DIRNAME = "memory"
INDEX_YAML_NAME = "index.yaml"

WEIGHT_TAG = 3.0
WEIGHT_SUMMARY = 1.0
WEIGHT_PATH = 0.5
PLUGIN_BIAS = 1.0

_TOKEN_SPLIT_RE = re.compile(r"[\s,;:/\\\(\)\[\]\{\}\"'<>!?]+")
_MIN_TOKEN_LEN = 2


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenise; drop dupes preserving first-seen order."""
    if not text:
        return []
    raw = _TOKEN_SPLIT_RE.split(text.lower())
    seen: set[str] = set()
    out: list[str] = []
    for t in raw:
        t = t.strip("-_.")
        if len(t) < _MIN_TOKEN_LEN:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _index_yaml_path(workspace: Path | str) -> Path:
    return Path(workspace) / CODENOOK_DIRNAME / MEMORY_DIRNAME / INDEX_YAML_NAME


def _load_entries(workspace: Path | str) -> list[dict[str, Any]]:
    """Walk the workspace knowledge directories live and return entries.

    v0.29.0+ — there is no on-disk ``index.yaml`` to read; every call
    re-scans plugin and memory ``knowledge/`` directories directly.
    Each returned entry has at least ``path, summary, tags`` and may
    carry a ``plugin`` key (``None`` for memory-extracted entries).
    Never raises — discovery errors yield ``[]``.
    """
    try:
        import knowledge_index as ki  # type: ignore
    except ImportError:
        return []
    out: list[dict[str, Any]] = []

    plugins_root = Path(workspace) / CODENOOK_DIRNAME / "plugins"
    if plugins_root.is_dir():
        for pdir in sorted(plugins_root.iterdir(), key=lambda x: x.name):
            if not pdir.is_dir():
                continue
            try:
                recs = ki.discover_knowledge(pdir)
            except Exception:
                continue
            for rec in recs:
                out.append(
                    {
                        "plugin": pdir.name,
                        "title": rec.get("title", ""),
                        "path": rec.get("path", ""),
                        "summary": rec.get("summary", ""),
                        "tags": list(rec.get("tags") or []),
                    }
                )

    memory_root = Path(workspace) / CODENOOK_DIRNAME / MEMORY_DIRNAME
    if memory_root.is_dir():
        try:
            recs = ki.discover_knowledge(memory_root)
        except Exception:
            recs = []
        for rec in recs:
            out.append(
                {
                    "plugin": None,
                    "title": rec.get("title", ""),
                    "path": rec.get("path", ""),
                    "summary": rec.get("summary", ""),
                    "tags": list(rec.get("tags") or []),
                }
            )
    return out


def _path_segments(path: str) -> list[str]:
    if not path:
        return []
    parts = re.split(r"[/\\]+", path.lower())
    return [p for p in parts if p]


def _score_entry(
    entry: dict[str, Any],
    tokens: Iterable[str],
    plugin_pin: str | None,
) -> tuple[float, list[str]]:
    """Score one entry; return ``(score, reason_fragments)``."""
    tokens_list = list(tokens)
    tag_strs = [str(t).lower() for t in (entry.get("tags") or []) if t]
    summary_l = str(entry.get("summary") or "").lower()
    path_segs = _path_segments(str(entry.get("path") or ""))

    score = 0.0
    tag_hits: list[str] = []
    summary_hits: list[str] = []
    path_hits: list[str] = []

    for tok in tokens_list:
        # Tags — count distinct matching tags rather than per-tag hits
        # so a multi-token query against the same tag doesn't double-pay.
        for tag in tag_strs:
            if tok == tag or tok in tag.split() or tok in tag:
                score += WEIGHT_TAG
                tag_hits.append(tag)
                break  # one tag per token; further tags handled below
        # Summary
        if tok and tok in summary_l:
            score += WEIGHT_SUMMARY
            summary_hits.append(tok)
        # Path segments
        for seg in path_segs:
            if tok == seg or tok in seg:
                score += WEIGHT_PATH
                path_hits.append(seg)
                break

    if plugin_pin and entry.get("plugin") == plugin_pin:
        score += PLUGIN_BIAS

    reasons: list[str] = []
    if tag_hits:
        reasons.append("tag match: " + ", ".join(sorted(set(tag_hits))[:3]))
    if summary_hits:
        reasons.append("summary keyword: " + ", ".join(sorted(set(summary_hits))[:3]))
    if path_hits:
        reasons.append("path: " + ", ".join(sorted(set(path_hits))[:2]))
    if plugin_pin and entry.get("plugin") == plugin_pin:
        reasons.append(f"plugin pin: {plugin_pin}")

    return score, reasons


def find_relevant(
    workspace: Path | str,
    query: str,
    role: str | None = None,
    phase_id: str | None = None,
    plugin: str | None = None,
    top_n: int = 8,
) -> list[dict[str, Any]]:
    """Rank knowledge entries against ``query`` (+ optional context).

    Args:
      workspace:  workspace root (the parent of ``.codenook``).
      query:      free-form text; typically ``task.input`` plus task
                  keywords.
      role:       optional dispatched role name; folded into the query.
      phase_id:   optional phase id; folded into the query.
      plugin:     when set, entries whose ``plugin`` matches get a +1
                  scoring bias (used to pin to the active plugin).
      top_n:      maximum hits returned (≥ 0). Defaults to 8.

    Returns:
      List of ``{path, summary, tags, plugin, score, reason}`` dicts,
      sorted by ``(-score, plugin, path)``. Empty list if no matches
      or the index is empty/missing/corrupt.
    """
    if not isinstance(top_n, int) or top_n <= 0:
        return []

    parts: list[str] = []
    if query:
        parts.append(str(query))
    if role:
        parts.append(str(role))
    if phase_id:
        parts.append(str(phase_id))
    tokens = _tokenize(" ".join(parts))
    if not tokens:
        return []

    entries = _load_entries(workspace)
    if not entries:
        return []

    hits: list[dict[str, Any]] = []
    for entry in entries:
        score, reasons = _score_entry(entry, tokens, plugin)
        if score <= 0:
            continue
        hits.append(
            {
                "title": str(entry.get("title") or ""),
                "path": str(entry.get("path") or ""),
                "summary": str(entry.get("summary") or ""),
                "tags": list(entry.get("tags") or []),
                "plugin": entry.get("plugin"),
                "score": round(score, 2),
                "reason": "; ".join(reasons) if reasons else "(no specific reason)",
            }
        )

    hits.sort(key=lambda h: (-h["score"], (h["plugin"] or ""), h["path"]))
    return hits[:top_n]


# ---------------------------------------------------------------- rendering
KNOWLEDGE_HITS_PLACEHOLDER = "{{KNOWLEDGE_HITS}}"

_HEADER = (
    "## Auto-retrieved knowledge hits (v0.22.0+)\n"
    "\n"
    "Top {n} matches from `.codenook/memory/index.yaml` (kernel-injected).\n"
    "The self-retrieval guide above still applies — these are advisory,\n"
    "not exhaustive.\n"
    "\n"
)

_EMPTY = (
    "## Auto-retrieved knowledge hits (v0.22.0+)\n"
    "\n"
    "_No matches found in index.yaml. Run `codenook knowledge reindex`\n"
    "if you expected hits._\n"
)


_HITS_LINE_LIMIT = 400  # truncate any one summary/tag/reason at this length
_HITS_LINE_BREAK_RE = None  # lazy import below


def _sanitise_for_prompt(value: str, *, limit: int = _HITS_LINE_LIMIT) -> str:
    """Defang an untrusted string before splicing into a sub-agent prompt.

    Knowledge entries are user-authored YAML; their ``summary``, ``title``
    and ``tags`` flow into ``{{KNOWLEDGE_HITS}}`` verbatim, which means a
    hostile (or careless) entry could:
      * smuggle a fake instruction block at the next-prompt-section level
        by embedding "\n## " or "\n---" boundaries (prompt injection /
        section spoofing);
      * bury the real prompt under thousands of repeated lines (token DoS).

    Strip CRs, collapse newlines into ``\\n`` literals so the output stays
    a single visible line per field, drop NUL bytes, escape literal
    triple-backtick fences, and cap the length.
    """
    s = (value or "").replace("\x00", "")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", "\\n")
    s = s.replace("```", "\u200b`\u200b`\u200b`\u200b")
    if len(s) > limit:
        s = s[:limit] + "\u2026[truncated]"
    return s


def render_hits_block(hits: list[dict[str, Any]]) -> str:
    """Format hits as a markdown bullet list for prompt substitution.

    Per-field strings are run through ``_sanitise_for_prompt`` so that a
    knowledge entry cannot inject prompt-level structure (newlines, fake
    section headers, oversize blobs) into a sub-agent dispatch.
    """
    if not hits:
        return _EMPTY
    lines: list[str] = [_HEADER.format(n=len(hits))]
    for h in hits:
        plugin = _sanitise_for_prompt(h.get("plugin") or "(memory)", limit=64)
        score = h.get("score", 0)
        path = _sanitise_for_prompt(h.get("path") or "", limit=200)
        summary = _sanitise_for_prompt((h.get("summary") or "").strip())
        tags_raw = h.get("tags") or []
        tags = [_sanitise_for_prompt(str(t), limit=64) for t in tags_raw[:32]]
        reason = _sanitise_for_prompt((h.get("reason") or "").strip())
        lines.append(f"- `{path}` (plugin: {plugin}, score: {score})\n")
        if summary:
            lines.append(f"  summary: {summary}\n")
        if tags:
            lines.append(f"  tags: {', '.join(tags)}\n")
        if reason:
            lines.append(f"  why selected: {reason}\n")
    return "".join(lines)


def substitute_placeholder(
    body: str,
    workspace: Path | str,
    query: str,
    role: str | None = None,
    phase_id: str | None = None,
    plugin: str | None = None,
    top_n: int = 8,
) -> str:
    """Replace ``{{KNOWLEDGE_HITS}}`` in ``body`` with a rendered hits block.

    Backward-compat: if the placeholder is absent, returns ``body``
    unchanged (no work done, no I/O).
    """
    if KNOWLEDGE_HITS_PLACEHOLDER not in (body or ""):
        return body
    hits = find_relevant(
        workspace,
        query,
        role=role,
        phase_id=phase_id,
        plugin=plugin,
        top_n=top_n,
    )
    block = render_hits_block(hits)
    return body.replace(KNOWLEDGE_HITS_PLACEHOLDER, block)


def resolve_top_n(workspace: Path | str, default: int = 8) -> int:
    """Return ``default`` (v0.29.0+).

    Previously honoured ``<ws>/.codenook/config.yaml`` key
    ``knowledge_hits.top_n``; that knob lived in the now-removed
    per-memory ``config.yaml``. The kernel hard-codes the default
    again — callers can override per-call via the ``top_n`` argument
    on ``find_relevant`` / ``substitute_*placeholder``.
    """
    del workspace
    return default


# ---------------------------------------------------------------- v0.28.3
# Single-brace ``{KNOWLEDGE_HITS}`` placeholder — compact markdown list,
# default top-5, EMPTY string on zero hits (no "no hits" stub).
#
# Distinct from the legacy double-brace ``{{KNOWLEDGE_HITS}}`` which
# emits a verbose header + "no hits" stub. New phase prompt templates
# use the single-brace form so the "## 相关 workspace 知识" section
# stays clean when the index has nothing to offer.

SINGLE_KH_PLACEHOLDER = "{KNOWLEDGE_HITS}"

DEFAULT_SINGLE_TOP_N = 5


def render_hits_block_compact(hits: list[dict[str, Any]]) -> str:
    """Format hits as a compact markdown bullet list.

    Returns the empty string when ``hits`` is empty so callers can drop
    a clean blank into the rendered prompt rather than a "no hits"
    advisory message.
    """
    if not hits:
        return ""
    lines: list[str] = []
    for h in hits:
        title = (h.get("title") or "").strip()
        path = (h.get("path") or "").strip()
        summary = (h.get("summary") or "").strip()
        label = title or path or "(untitled entry)"
        if summary:
            lines.append(f"- **{label}** (`{path}`) — {summary}")
        else:
            lines.append(f"- **{label}** (`{path}`)")
    return "\n".join(lines) + "\n"


def substitute_single_placeholder(
    body: str,
    workspace: Path | str,
    query: str,
    role: str | None = None,
    phase_id: str | None = None,
    plugin: str | None = None,
    top_n: int = DEFAULT_SINGLE_TOP_N,
) -> str:
    """Replace ``{KNOWLEDGE_HITS}`` (single-brace) with a compact list.

    * If ``body`` does not contain the placeholder → return ``body``
      unchanged (no I/O).
    * If the search returns zero hits → replace with empty string
      (clean blank, NOT a "no hits" stub).
    * Otherwise → replace with markdown bullet list (title + summary).
    """
    if SINGLE_KH_PLACEHOLDER not in (body or ""):
        return body
    hits = find_relevant(
        workspace,
        query,
        role=role,
        phase_id=phase_id,
        plugin=plugin,
        top_n=top_n,
    )
    return body.replace(SINGLE_KH_PLACEHOLDER, render_hits_block_compact(hits))
