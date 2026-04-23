"""``codenook knowledge`` — plugin-shipped knowledge index commands.

Subcommands:
  reindex           rebuild ``<ws>/.codenook/memory/index.yaml`` from
                    every installed plugin's ``knowledge/`` and
                    ``skills/SKILL.md`` files.
  list              print the indexed knowledge by plugin.
  search <query>    rank knowledge entries against ``<query>`` using
                    the kernel's ``knowledge_index.find_relevant`` and
                    print the top hits.

The reindex command produces a unified ``index.yaml`` that includes
both plugin-shipped entries (from ``aggregate_knowledge``) and any
memory-extracted entries already present in
``<ws>/.codenook/memory/{knowledge,skills}/``. It is idempotent: two
back-to-back runs yield the same file modulo ``generated_at``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from .config import CodenookContext


USAGE = """\
codenook knowledge — plugin knowledge index

Subcommands:
  knowledge reindex            rebuild .codenook/memory/index.yaml
  knowledge list [--plugin P]  print indexed knowledge entries
  knowledge search <query>     rank entries against <query>

Options:
  --limit N        cap output for `search` / `list` (default 20).
"""


def _import_helpers():
    """Import kernel helpers; ``config.load_context`` already added
    ``<kernel>/_lib`` to ``sys.path``."""
    import knowledge_index as ki  # type: ignore
    try:
        from full_index import build_full_index, write_index_yaml  # type: ignore
    except ImportError:
        # full_index ships beside knowledge_index in the kernel _lib
        # directory; if it's missing the install is broken.
        sys.stderr.write("codenook knowledge: kernel module 'full_index' not found\n")
        raise
    return ki, build_full_index, write_index_yaml


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    if not args or args[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0

    sub = args[0]
    rest = list(args[1:])

    if sub == "reindex":
        return _cmd_reindex(ctx, rest)
    if sub == "list":
        return _cmd_list(ctx, rest)
    if sub == "search":
        return _cmd_search(ctx, rest)

    sys.stderr.write(f"codenook knowledge: unknown subcommand: {sub}\n")
    sys.stderr.write(USAGE)
    return 2


def _cmd_reindex(ctx: CodenookContext, args: list[str]) -> int:
    if args:
        sys.stderr.write(
            f"codenook knowledge reindex: unexpected args: {' '.join(args)}\n"
        )
        return 2
    _, build_full_index, write_index_yaml = _import_helpers()
    payload = build_full_index(ctx.workspace)
    target = write_index_yaml(ctx.workspace, payload)
    n_k = len(payload.get("knowledge", []))
    n_s = len(payload.get("skills", []))
    plugins: set[str] = set()
    for entry in payload.get("knowledge", []):
        p = entry.get("plugin")
        if isinstance(p, str):
            plugins.add(p)
    for entry in payload.get("skills", []):
        p = entry.get("plugin")
        if isinstance(p, str):
            plugins.add(p)
    sys.stdout.write(
        f"codenook knowledge: wrote {target}\n"
        f"  plugins: {len(plugins)}  knowledge: {n_k}  skills: {n_s}\n"
    )
    return 0


def _cmd_list(ctx: CodenookContext, args: list[str]) -> int:
    plugin_filter: str | None = None
    limit: int | None = None
    it = iter(args)
    try:
        for a in it:
            if a == "--plugin":
                plugin_filter = next(it)
            elif a == "--limit":
                limit = int(next(it))
            else:
                sys.stderr.write(f"codenook knowledge list: unknown arg: {a}\n")
                return 2
    except (StopIteration, ValueError):
        sys.stderr.write("codenook knowledge list: malformed flag value\n")
        return 2

    _, build_full_index, _ = _import_helpers()
    payload = build_full_index(ctx.workspace)
    entries = payload.get("knowledge", [])
    if plugin_filter:
        entries = [e for e in entries if e.get("plugin") == plugin_filter]
    if limit is not None:
        entries = entries[:limit]

    if not entries:
        sys.stdout.write("(no knowledge entries indexed)\n")
        return 0

    cur_plugin = None
    for e in entries:
        plug = e.get("plugin") or "(memory)"
        if plug != cur_plugin:
            sys.stdout.write(f"\n[{plug}]\n")
            cur_plugin = plug
        title = e.get("title") or e.get("topic") or "(untitled)"
        tags = ",".join(e.get("tags") or [])
        path = e.get("path") or ""
        summary = (e.get("summary") or "").strip()
        sys.stdout.write(f"  - {title}\n")
        sys.stdout.write(f"      path: {path}\n")
        if tags:
            sys.stdout.write(f"      tags: {tags}\n")
        if summary:
            sys.stdout.write(f"      summary: {summary}\n")
    return 0


def _cmd_search(ctx: CodenookContext, args: list[str]) -> int:
    query_parts: list[str] = []
    limit = 5
    it = iter(args)
    try:
        for a in it:
            if a == "--limit":
                limit = int(next(it))
            else:
                query_parts.append(a)
    except (StopIteration, ValueError):
        sys.stderr.write("codenook knowledge search: malformed --limit\n")
        return 2

    query = " ".join(query_parts).strip()
    if not query:
        sys.stderr.write("codenook knowledge search: missing <query>\n")
        return 2

    ki, build_full_index, _ = _import_helpers()
    payload = build_full_index(ctx.workspace)

    # Group entries by plugin so find_relevant can score uniformly.
    # Entries from both `knowledge` and `skills` go into the same pool
    # so `search` reflects everything installed / extracted. We remember
    # the per-record kind so the output line can label it.
    aggregated: dict[str, list[dict]] = {}
    kinds: dict[tuple[str, str], str] = {}

    for e in payload.get("knowledge", []):
        plug = e.get("plugin") or "(memory)"
        path = e.get("path") or ""
        rec = {
            "path": path,
            "title": e.get("title") or e.get("topic") or "",
            "summary": e.get("summary") or "",
            "tags": [str(t) for t in (e.get("tags") or [])],
        }
        aggregated.setdefault(plug, []).append(rec)
        kinds[(plug, path)] = "knowledge"

    for e in payload.get("skills", []):
        plug = e.get("plugin") or "(memory)"
        path = e.get("path") or ""
        # Skills use `name` where knowledge uses `title`; normalise.
        rec = {
            "path": path,
            "title": e.get("name") or e.get("title") or "",
            "summary": e.get("summary") or "",
            "tags": [str(t) for t in (e.get("tags") or [])],
        }
        aggregated.setdefault(plug, []).append(rec)
        kinds[(plug, path)] = "skill"

    hits = ki.find_relevant(query, aggregated, limit=limit)
    if not hits:
        sys.stdout.write(f"(no hits for query: {query})\n")
        return 0
    for h in hits:
        kind = kinds.get((h["plugin"], h["path"]), "knowledge")
        tag = "[S]" if kind == "skill" else "[K]"
        sys.stdout.write(
            f"[{h['score']}] {tag} {h['plugin']}  {h['title']}\n"
            f"      path: {h['path']}\n"
        )
        if h.get("tags"):
            sys.stdout.write(f"      tags: {','.join(h['tags'])}\n")
        if h.get("summary"):
            sys.stdout.write(f"      summary: {h['summary']}\n")
    return 0
