"""parent_suggester — M10.2 token-set Jaccard candidate ranker.

Implements ``docs/task-chains.md`` §5: a zero-dependency,
pure-Python similarity scorer that surfaces likely parent tasks for a
new (about-to-spawn) task. The router-agent's "parent preflight" UX
(M10.3) renders the returned suggestions for user confirmation.

Algorithm (spec §5.1, §5.2, §5.3):

    1. Tokenize child_brief: lowercase → split on punctuation/whitespace
       → drop stopwords (built-in EN+ZH list, ≤ ~50 entries) → drop
       tokens shorter than 2 chars → set.
    2. For each open task in ``<workspace>/.codenook/tasks/``:
        - skip when status ∈ {done, cancelled}
        - skip the child's own task_id (via ``exclude_ids``)
        - build candidate text from ``state.json`` title+summary +
          ``draft-config.yaml`` ``input`` + first 3 user turns from
          ``router-context.md``; tokenize the same way.
        - compute Jaccard = |A ∩ B| / |A ∪ B| (0 when union empty).
    3. Drop scores below ``threshold`` (default 0.15).
    4. Sort by (-score, task_id) and return the first ``top_k``.

Failure semantics (spec §5.7):

    * Per-candidate IO/JSON error → skip + ``parent_suggest_skip``
      audit (one line per skipped candidate).
    * Whole-pool enumeration raises → return ``[]`` and emit
      ``parent_suggest_failed`` audit. The router-agent never gets
      blocked by suggestion failures.

CLI:

    python -m parent_suggester --workspace <ws> --brief <text>
        [--top-k N] [--threshold T] [--json] [--exclude TID]...

Exit codes mirror task_chain.py: 0 success, 2 invalid args (argparse),
1 runtime error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_audit  # noqa: E402
import memory_layer as _ml  # noqa: E402

# ───────────────────────────────────────────────────────── public types

class Suggestion(NamedTuple):
    task_id: str
    title: str
    score: float          # ∈ [0, 1]
    reason: str           # e.g. "shared: feature, auth, login"


# ───────────────────────────────────────────────────────── tokenization

# Split on any non-(ascii-alnum / underscore / CJK-unified-ideograph) run.
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9_\u4e00-\u9fff]+")

_STOPWORDS = frozenset({
    # English (≤ 40)
    "a", "an", "the", "of", "in", "on", "at", "for", "to", "is", "are",
    "was", "were", "be", "been", "by", "with", "as", "and", "or", "but",
    "if", "then", "else", "this", "that", "these", "those", "i", "you",
    "he", "she", "it", "we", "they", "what", "which", "who", "when",
    "where", "how", "why", "from", "into", "than", "so", "do", "does",
    # Chinese (≤ 30)
    "的", "了", "是", "在", "和", "与", "或", "这", "那", "也", "都",
    "就", "一个", "我", "你", "他", "她", "它", "我们", "你们", "他们",
    "啊", "吧", "呢", "把", "给", "让", "但是", "如果", "因为", "所以",
    "被", "对", "还",
})


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    parts = _TOKEN_SPLIT_RE.split(text.lower())
    return {p for p in parts if p and len(p) >= 2 and p not in _STOPWORDS}


# ───────────────────────────────────────────────────────── path helpers

def _ws_path(workspace: Path | str) -> Path:
    return Path(workspace)


def _tasks_dir(workspace: Path | str) -> Path:
    return _ws_path(workspace) / ".codenook" / "tasks"


def _state_path(workspace: Path | str, task_id: str) -> Path:
    return _tasks_dir(workspace) / task_id / "state.json"


def _draft_path(workspace: Path | str, task_id: str) -> Path:
    return _tasks_dir(workspace) / task_id / "draft-config.yaml"


def _router_context_path(workspace: Path | str, task_id: str) -> Path:
    return _tasks_dir(workspace) / task_id / "router-context.md"


# ───────────────────────────────────────────────────────── audit helper

def _audit(workspace: Path | str, *, outcome: str, verdict: str,
           source_task: str = "", reason: str = "") -> None:
    """Write a chain-asset audit line; never raise."""
    try:
        extract_audit.audit(
            workspace,
            asset_type="chain",
            outcome=outcome,
            verdict=verdict,
            source_task=source_task,
            reason=reason,
        )
    except Exception:
        pass


def _diag(workspace: Path | str, *, kind: str, source_task: str = "",
          reason: str = "") -> None:
    """Spec §9.1 diagnostic: emit a single jsonl record with ``kind``.

    Bypasses ``extract_audit.audit`` to avoid the canonical+side-record
    duplication (which would emit two lines, one missing ``kind``).
    """
    try:
        rec = {
            "asset_type": "chain",
            "candidate_hash": "",
            "existing_path": None,
            "outcome": "diagnostic",
            "reason": reason,
            "source_task": source_task,
            "timestamp": extract_audit._now_iso(),
            "verdict": "noop",
            "kind": kind,
        }
        _ml.append_audit(workspace, rec)
    except Exception:
        pass


# ───────────────────────────────────────────────────────── pool listing

# Statuses that REMOVE a task from the suggestion pool (spec §5.3).
_CLOSED_STATUSES = frozenset({"done", "cancelled"})


def _list_open_tasks(workspace: Path | str) -> list[str]:
    """Return task_ids that are present and not closed.

    Raises OSError on disk-level failure so the caller can convert it
    into a ``parent_suggest_failed`` audit. Per-candidate read errors
    are NOT surfaced here — they are handled by ``_load_candidate``
    inside ``suggest_parents`` so a single bad state.json can be
    skipped + audited individually.
    """
    root = _tasks_dir(workspace)
    if not root.exists():
        return []
    out: list[str] = []
    for entry in sorted(os.listdir(root)):
        if entry.startswith("."):
            continue
        if not (root / entry).is_dir():
            continue
        out.append(entry)
    return out


def _load_candidate(workspace: Path | str, task_id: str) -> Optional[dict]:
    """Read state.json + best-effort brief sources. Return None on failure."""
    sp = _state_path(workspace, task_id)
    if not sp.exists():
        return None
    try:
        with open(sp, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(state, dict):
        return None
    status = state.get("status")
    if status in _CLOSED_STATUSES:
        return {"_closed": True}
    title = state.get("title") or ""
    summary = state.get("summary") or ""
    brief_parts: list[str] = []
    if isinstance(title, str):
        brief_parts.append(title)
    if isinstance(summary, str):
        brief_parts.append(summary)
    # Optional draft-config.yaml `input` (best effort, no YAML dep).
    dp = _draft_path(workspace, task_id)
    if dp.exists():
        try:
            with open(dp, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.lstrip()
                    if s.startswith("input:"):
                        val = s.split(":", 1)[1].strip().strip("\"'")
                        if val:
                            brief_parts.append(val)
                        break
        except OSError:
            pass
    # Optional router-context.md first 3 user turns.
    rc = _router_context_path(workspace, task_id)
    if rc.exists():
        try:
            user_turns: list[str] = []
            with open(rc, "r", encoding="utf-8") as f:
                in_user = False
                buf: list[str] = []
                for line in f:
                    if line.startswith("## "):
                        if in_user and buf:
                            user_turns.append(" ".join(buf).strip())
                            buf = []
                        in_user = "user" in line.lower()
                        if len(user_turns) >= 3:
                            break
                    elif in_user:
                        buf.append(line.strip())
                if in_user and buf and len(user_turns) < 3:
                    user_turns.append(" ".join(buf).strip())
            brief_parts.extend(user_turns[:3])
        except OSError:
            pass
    return {
        "task_id": task_id,
        "title": title if isinstance(title, str) else "",
        "brief_text": "\n".join(brief_parts),
    }


# ───────────────────────────────────────────────────────── public API

def suggest_parents(
    workspace: Path | str,
    child_brief: str,
    *,
    top_k: int = 3,
    threshold: float = 0.15,
    exclude_ids: Optional[Iterable[str]] = None,
    exclude_task_ids: Optional[Iterable[str]] = None,
) -> list[Suggestion]:
    """Rank open tasks by token-set Jaccard against ``child_brief``.

    Returns up to ``top_k`` :class:`Suggestion` items with score
    ``>= threshold``. Ties broken deterministically by ascending
    ``task_id``. Empty workspace (no tasks) returns ``[]`` without
    auditing. See module docstring for failure semantics.

    ``exclude_ids`` / ``exclude_task_ids`` are aliases (the spec uses
    the former, the M10.2 task brief uses the latter); both are unioned
    when supplied.
    """
    excludes: set[str] = set()
    if exclude_ids:
        excludes.update(exclude_ids)
    if exclude_task_ids:
        excludes.update(exclude_task_ids)

    child_tokens = _tokenize(child_brief)

    try:
        ids = _list_open_tasks(workspace)
    except Exception as e:  # noqa: BLE001 — defensive per spec §5.7
        # Diagnostic side-record + canonical record (spec §9.1).
        _diag(workspace, kind="parent_suggest_failed",
              reason=f"{type(e).__name__}: {e}")
        _audit(workspace, outcome="parent_suggest_failed", verdict="error",
               reason=f"{type(e).__name__}: {e}")
        return []

    suggestions: list[Suggestion] = []
    for tid in ids:
        if tid in excludes:
            continue
        try:
            cand = _load_candidate(workspace, tid)
        except Exception as e:  # noqa: BLE001
            _diag(workspace, kind="parent_suggest_skip",
                  source_task=tid, reason=f"{type(e).__name__}: {e}")
            _audit(workspace, outcome="parent_suggest_skip", verdict="warn",
                   source_task=tid, reason=f"{type(e).__name__}: {e}")
            continue
        if cand is None:
            _diag(workspace, kind="parent_suggest_skip",
                  source_task=tid, reason="unreadable or invalid state.json")
            _audit(workspace, outcome="parent_suggest_skip", verdict="warn",
                   source_task=tid, reason="unreadable or invalid state.json")
            continue
        if cand.get("_closed"):
            continue
        cand_tokens = _tokenize(cand["title"] + "\n" + cand["brief_text"])
        union = child_tokens | cand_tokens
        if not union:
            score = 0.0
            shared: list[str] = []
        else:
            inter = child_tokens & cand_tokens
            score = len(inter) / len(union)
            shared = sorted(inter)
        if score < threshold:
            continue
        if shared:
            reason = "shared: " + ", ".join(shared[:5])
        else:
            reason = "shared: (none)"
        suggestions.append(Suggestion(
            task_id=tid,
            title=cand["title"],
            score=round(score, 6),
            reason=reason,
        ))

    suggestions.sort(key=lambda s: (-s.score, s.task_id))
    if top_k is not None and top_k >= 0:
        suggestions = suggestions[:top_k]
    return suggestions


# ─────────────────────────────────────────────────────────────── CLI

def cli_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="parent_suggester",
        description="Rank open tasks by Jaccard similarity to a child brief.",
    )
    ap.add_argument("--workspace", default=".",
                    help="Workspace root (default: cwd).")
    ap.add_argument("--brief", required=True, help="Child task brief text.")
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=0.15)
    ap.add_argument("--exclude", action="append", default=[],
                    help="Task ID to exclude (repeatable).")
    ap.add_argument("--json", action="store_true", help="Emit JSON output.")

    args = ap.parse_args(argv)
    try:
        out = suggest_parents(
            args.workspace,
            args.brief,
            top_k=args.top_k,
            threshold=args.threshold,
            exclude_ids=args.exclude or None,
        )
    except Exception as e:  # noqa: BLE001
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(
            [{"task_id": s.task_id, "title": s.title,
              "score": s.score, "reason": s.reason} for s in out],
            ensure_ascii=False, indent=2,
        ))
    else:
        for s in out:
            print(f"{s.score:.4f}\t{s.task_id}\t{s.title}\t# {s.reason}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_main(sys.argv[1:]))
