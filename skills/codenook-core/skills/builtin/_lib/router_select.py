"""router_select — M7 keyword/applies_to/priority router shim.

Background
----------
The M3 router (`router-triage`, removed in M8.7) routed via per-plugin
`intent_patterns` (regex). The M7 packaging spec adds a new, simpler
routing surface to plugin.yaml — `applies_to`, `keywords`,
`routing.priority` — that the M7 routing tests consume.

This shim is intentionally narrow:

* It is consumed by the M7 routing tests (`m7-routing.bats`) and may be
  reused as a Python-only scoring helper inside `router-agent` (M8.2)
  for any caller that wants a quick "given this user input, which
  installed plugin wins?" decision without committing to the regex DSL.
* It is a Python API only (no CLI entry); the M3 `router-triage` skill
  that previously consumed it has been removed in M8.7.

Decision algorithm
------------------
Inputs: a free-text task prompt + the list of installed plugin
manifests (loaded via `manifest_load.load_all`).

For each plugin compute a match score:

    score = keyword_hits * 10 + applies_to_hits * 5

A `keyword_hit` is a case-insensitive substring match between any
`plugin.keywords[*]` entry and the input. An `applies_to_hit` is a
case-insensitive substring match between any `plugin.applies_to[*]`
entry and the input. Wildcard `"*"` in `applies_to` is excluded from
counting (it would otherwise dominate generic).

Pick the plugin with the highest score. Ties broken by
`routing.priority` (higher wins). Further ties broken by alphabetical
plugin id (deterministic).

If no plugin scored > 0, fall back to the first plugin whose
`applies_to` contains `"*"` (the catch-all). If none, return None.
"""
from __future__ import annotations

from typing import Iterable

DEFAULT_PRIORITY = 0


def _norm_list(val) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        return [val]
    if isinstance(val, (list, tuple)):
        return [str(x) for x in val]
    return []


def _score(text: str, manifest: dict) -> int:
    text_l = text.lower()
    keywords = [k.lower() for k in _norm_list(manifest.get("keywords"))]
    applies = [a.lower() for a in _norm_list(manifest.get("applies_to"))]
    kw_hits = sum(1 for k in keywords if k and k in text_l)
    at_hits = sum(1 for a in applies if a and a != "*" and a in text_l)
    return kw_hits * 10 + at_hits * 5


def _priority(manifest: dict) -> int:
    routing = manifest.get("routing") or {}
    if not isinstance(routing, dict):
        return DEFAULT_PRIORITY
    p = routing.get("priority", DEFAULT_PRIORITY)
    try:
        return int(p)
    except (TypeError, ValueError):
        return DEFAULT_PRIORITY


def _is_wildcard_fallback(manifest: dict) -> bool:
    return "*" in _norm_list(manifest.get("applies_to"))


def select(text: str, manifests: Iterable[dict]) -> str | None:
    """Return the chosen plugin id, or None if there is nothing to pick.

    `manifests` should be an iterable of dicts as produced by
    `manifest_load.load_all` (each carries an "id" key plus the plugin's
    raw plugin.yaml fields).
    """
    plugins = [m for m in manifests if isinstance(m, dict) and m.get("id")]
    if not plugins:
        return None

    scored = [(m, _score(text, m)) for m in plugins]
    best = max(s for _, s in scored)

    if best > 0:
        candidates = [m for m, s in scored if s == best]
    else:
        # Fallback: any plugin claiming applies_to == ["*"] (or
        # containing it). Specialised plugins NEVER use the wildcard,
        # so this isolates true catch-all plugins like 'generic'.
        candidates = [m for m in plugins if _is_wildcard_fallback(m)]
        if not candidates:
            return None

    candidates.sort(key=lambda m: (-_priority(m), m["id"]))
    return candidates[0]["id"]


def select_with_score(text: str, manifests: Iterable[dict]) -> dict | None:
    """Diagnostic variant — returns {id, score, priority, reason}."""
    plugins = [m for m in manifests if isinstance(m, dict) and m.get("id")]
    if not plugins:
        return None
    scored = [(m, _score(text, m)) for m in plugins]
    best = max(s for _, s in scored)
    if best > 0:
        candidates = [(m, s) for m, s in scored if s == best]
        reason = "keyword_or_applies_to"
    else:
        candidates = [(m, 0) for m in plugins if _is_wildcard_fallback(m)]
        reason = "wildcard_fallback"
        if not candidates:
            return None
    candidates.sort(key=lambda ms: (-_priority(ms[0]), ms[0]["id"]))
    chosen, score = candidates[0]
    return {
        "id": chosen["id"],
        "score": score,
        "priority": _priority(chosen),
        "reason": reason,
    }
