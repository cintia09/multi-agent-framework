#!/usr/bin/env python3
"""knowledge-extractor — M9.3.

Reads task context (either ``--input <file>`` or the workspace task dir),
asks the LLM to propose ``knowledge`` candidates, then runs each through
the patch-or-create decision flow (secret-scan → hash dedup → similarity
→ LLM judge → write).

Best-effort: any unexpected failure is logged via ``append_audit`` with
``status=failed`` and the process exits 0 (FR-EXT-5 / AC-EXT-4). The one
exception is secret-blocked candidates — TC-M9.3-12 requires a non-zero
exit code so the dispatcher can surface "this body was rejected".

CLI (M9.0 handoff contract):
    extract.py --task-id <id> --workspace <ws> --phase <phase> --reason <r>
               [--input <file>]

Audit-log schema (TC-M9.3-09 strict keys):
    {asset_type, candidate_hash, existing_path, outcome, reason,
     source_task, timestamp, verdict}

``outcome`` ∈ {created, merged, replaced, dedup, blocked_secret, failed,
              dropped_by_cap}.
``verdict`` ∈ {create, merge, replace, dedup, blocked, failed, dropped}.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import traceback
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_LIB = _HERE.parent / "_lib"
sys.path.insert(0, str(_LIB))

import memory_index  # noqa: E402
import memory_layer as ml  # noqa: E402
from extract_audit import audit as _audit_canonical  # noqa: E402
from llm_call import call_llm  # noqa: E402
try:  # M9.7 / TC-M9.7-07 — fail closed when secret scanner is missing.
    from secret_scan import redact as _redact  # noqa: E402
    from secret_scan import scan_secrets as _scan_secrets  # noqa: E402
except ImportError:
    print("secret scanner unavailable; refusing to write", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------- constants

PER_TASK_CAP = 3
MAX_SUMMARY = ml.MAX_SUMMARY_CHARS  # 200
MAX_TAGS = ml.MAX_TAGS  # 8
INPUT_BODY_TRUNC = 4096

# Slug regex matching memory_layer._TOPIC_RE (must start alphanum).
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.\-]+")


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str, fallback: str = "knowledge") -> str:
    s = _SLUG_RE.sub("-", (text or "").strip().lower()).strip("-")
    if not s:
        s = fallback
    if not re.match(r"^[A-Za-z0-9]", s):
        s = "k-" + s
    return s[: ml.MAX_TOPIC_CHARS]


def _audit(
    workspace: Path,
    *,
    asset_type: str = "knowledge",
    outcome: str,
    verdict: str,
    reason: str = "",
    source_task: str = "",
    candidate_hash: str = "",
    existing_path: str | None = None,
    extra: dict | None = None,
) -> None:
    """Thin pass-through to the shared canonical audit writer."""
    _audit_canonical(
        workspace,
        asset_type=asset_type,
        outcome=outcome,
        verdict=verdict,
        reason=reason,
        source_task=source_task,
        candidate_hash=candidate_hash,
        existing_path=existing_path,
        extra=extra,
    )


# --------------------------------------------------------- input gathering


def _read_task_context(workspace: Path, task_id: str, input_path: Path | None) -> str:
    if input_path is not None:
        try:
            return input_path.read_text(encoding="utf-8")[:INPUT_BODY_TRUNC]
        except OSError:
            return ""

    chunks: list[str] = []
    task_dir = workspace / ".codenook" / "tasks" / task_id
    if task_dir.is_dir():
        log = task_dir / "task.log"
        if log.is_file():
            try:
                lines = log.read_text(encoding="utf-8").splitlines()
                chunks.append("\n".join(lines[-100:]))
            except OSError:
                pass
        notes_dir = task_dir / "notes"
        if notes_dir.is_dir():
            for p in sorted(notes_dir.glob("*.md")):
                try:
                    chunks.append(p.read_text(encoding="utf-8"))
                except OSError:
                    pass
    return ("\n\n".join(chunks))[:INPUT_BODY_TRUNC]


# E2E-009: extract knowledge candidates directly from role-output frontmatter.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _candidates_from_role_outputs(workspace: Path, task_id: str) -> list[dict] | None:
    """Scan ``.codenook/tasks/<task>/outputs/*.md`` for an ``extract:`` block in
    the YAML frontmatter and harvest knowledge candidates from it.

    Returns:
        * ``None`` if no role outputs were found at all (caller may fall
          back to the LLM-driven pipeline).
        * ``[]`` (empty list) if outputs exist but none declared an
          ``extract:`` block — graceful "no_candidates" path.
        * A list of normalized candidate dicts otherwise.

    Frontmatter contract::

        ---
        verdict: ok
        extract:
          - title: "Use iterative fib for n<1000"
            summary: "Linear-time path avoids stack blowup"
            tags: [algorithm, fibonacci, performance]
            body: |
              Detail body here…
        ---
    """
    try:
        import yaml  # local import — extract.py must work in mock-only envs
    except ImportError:  # pragma: no cover
        return None

    out_dir = workspace / ".codenook" / "tasks" / task_id / "outputs"
    if not out_dir.is_dir():
        return None
    files = sorted(out_dir.glob("*.md"))
    if not files:
        return None

    candidates: list[dict] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        m = _FRONTMATTER_RE.match(text)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        block = fm.get("extract")
        if block is None:
            # E2E-P-003 — fall back: synthesize a minimal candidate from
            # the role's own `summary` + body when the role didn't author
            # an explicit `extract:` block. This guarantees the memory
            # layer is observable after a full lifecycle (round-2 fix).
            summary = (fm.get("summary") or "").strip()
            verdict = (fm.get("verdict") or "").strip()
            if summary and verdict in ("ok", "approve", "approved"):
                body_after = text[m.end():].strip()
                title = summary[:80] if len(summary) > 80 else summary
                candidates.append({
                    "title": title or f"{p.stem} note",
                    "summary": summary[:200],
                    "tags": [task_id, p.stem.split("-")[-1] or "role-output"],
                    "body": (body_after or summary)[:4096],
                    "_source_file": p.name,
                    "_source_role": p.stem,
                })
            continue
        items = block if isinstance(block, list) else [block]
        for it in items:
            if isinstance(it, dict):
                # Tag each candidate with its role-output origin so the
                # coarse-grained aggregator (change D) can record the
                # contributing roles as `sources` without duplicating
                # body content into per-role files.
                it = dict(it)
                it.setdefault("_source_file", p.name)
                it.setdefault("_source_role", p.stem)
                candidates.append(it)
    return candidates


# ─────────────────── change D: per-task aggregation ────────────────────
#
# Historical behaviour: four role outputs → four candidates → four
# near-identical ``memory/knowledge/*.md`` files. Change D collapses
# per-role candidates into a single synthesized ``by_topic`` entry for
# the task and records the contributing roles under ``sources_by_role``
# / the body's "## Sources" section.


def _aggregate_candidates_per_task(
    candidates: list[dict], task_id: str
) -> list[dict]:
    """Fold a list of per-role candidates into a single synthesized entry.

    * Single-candidate inputs pass through unchanged.
    * Multi-candidate inputs are merged:
        - ``title`` = first non-empty candidate title.
        - ``summary`` = first non-empty candidate summary.
        - ``tags`` = union (order-preserving) capped to MAX_TAGS.
        - ``body`` = concatenation of per-role bodies with a "### From
          <role>" header per contributor, plus a trailing "## Sources"
          list. No by-role file is ever written — the per-role view is
          reconstructed from this single content file.
        - ``topic`` = inherited from the first candidate's ``title`` /
          ``topic`` hint, falling back to ``task_id``.
    * ``_source_roles`` / ``_source_files`` are carried on the synth
      candidate so :func:`_process_candidate` can seed ``sources_by_role``
      via the memory layer.
    """
    real = [c for c in candidates if isinstance(c, dict)]
    if len(real) <= 1:
        return real

    titles = [str(c.get("title") or "").strip() for c in real]
    summaries = [str(c.get("summary") or "").strip() for c in real]
    bodies = [str(c.get("body") or "").strip() for c in real]
    files = [str(c.get("_source_file") or "") for c in real]
    roles = [str(c.get("_source_role") or "") for c in real]

    merged_tags: list[str] = []
    seen_tags: set[str] = set()
    for c in real:
        for t in c.get("tags") or []:
            if isinstance(t, str) and t and t not in seen_tags:
                seen_tags.add(t)
                merged_tags.append(t)
    if task_id and task_id not in seen_tags:
        merged_tags.append(task_id)

    title = next((t for t in titles if t), f"{task_id} knowledge")
    summary = next((s for s in summaries if s), "")

    body_parts: list[str] = []
    for role, f, b in zip(roles, files, bodies):
        if not b:
            continue
        header = f"### From {role or f or 'source'}"
        body_parts.append(f"{header}\n\n{b}")
    body = "\n\n".join(body_parts)

    sources_lines = []
    for role, f in zip(roles, files):
        label = role or f
        if label and label not in sources_lines:
            sources_lines.append(label)

    # Finding 4 (review): truncate the aggregated per-role body *first*,
    # then append the Sources block, so provenance isn't chopped off for
    # tasks with several long role outputs.
    body = body[: INPUT_BODY_TRUNC * 2]
    if sources_lines:
        body = (
            body.rstrip() + "\n\n## Sources\n"
            + "\n".join(f"- {s}" for s in sources_lines) + "\n"
        )

    # Inherit topic hint from the first candidate, if present.
    topic_hint = next(
        (str(c.get("topic")) for c in real if c.get("topic")),
        "",
    )

    out = {
        "title": title,
        "summary": summary,
        "tags": merged_tags[: MAX_TAGS],
        "body": body,
        "_source_roles": [r for r in roles if r],
        "_source_files": [f for f in files if f],
        "_aggregated": True,
    }
    if topic_hint:
        out["topic"] = topic_hint
    return [out]


# ------------------------------------------------------------ LLM helpers


def _build_extract_prompt(task_id: str, phase: str, reason: str, body: str) -> str:
    return (
        "You are CodeNook's knowledge extractor.\n"
        f"Task: {task_id}  Phase: {phase}  Reason: {reason}\n\n"
        "Read the task notes below and propose up to 5 reusable knowledge\n"
        "entries. Respond with strict JSON of the form:\n"
        '  {"candidates":[{"title":..,"summary":..,"tags":[..],"body":..}, ...]}\n'
        "Constraints: summary ≤ 200 chars, tags ≤ 8, no secrets, no PII.\n\n"
        "## Task notes\n"
        f"{body}\n"
    )


def _build_decide_prompt(existing: dict, candidate: dict) -> str:
    return (
        "Decide how to merge a new knowledge candidate into existing memory.\n"
        "Default preference: merge.\n\n"
        "## Existing\n"
        f"title: {existing.get('title','')}\n"
        f"tags: {existing.get('tags',[])}\n\n"
        "## New candidate\n"
        f"title: {candidate.get('title','')}\n"
        f"tags: {candidate.get('tags',[])}\n\n"
        '## Output JSON\n{ "action": "merge"|"replace"|"create",'
        ' "rationale": "<≤200 chars>" }'
    )


def _parse_json_payload(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty LLM response")
    # Tolerate fenced code blocks (```json ... ```).
    if raw.startswith("```"):
        first_nl = raw.find("\n")
        last_fence = raw.rfind("```")
        if first_nl >= 0 and last_fence > first_nl:
            raw = raw[first_nl + 1 : last_fence].strip()
    # Fast path: raw is already a clean JSON object.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Tolerate prose-wrapped JSON ("Sure, here is the result: {...}")
    # by extracting the first balanced top-level object. Handles strings
    # so a `{` inside `"..."` doesn't fool the brace counter. (v0.27)
    start = raw.find("{")
    if start < 0:
        raise ValueError("no '{' in LLM response")
    # Refuse top-level arrays — returning the first element of an array
    # would be a silent partial parse, and the function contract is
    # ``-> dict``. If a `[` precedes our first `{`, treat the payload as
    # array-shaped and reject so the caller's existing fallback runs.
    bracket = raw.find("[")
    if 0 <= bracket < start:
        raise ValueError("top-level array, not object, in LLM response")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : i + 1])
    raise ValueError("unbalanced '{' in LLM response")


# ------------------------------------------------------- ranking + caps


def _density(cand: dict, existing_tag_universe: set[str]) -> float:
    tags = {t for t in (cand.get("tags") or []) if isinstance(t, str)}
    if not tags:
        return 0.0
    dup = len(tags & existing_tag_universe) / len(tags)
    return len(tags) * (1.0 - dup)


def _rank_and_cap(
    candidates: list[dict],
    workspace: Path,
    task_id: str = "",
    route: str = "cross_task",
) -> tuple[list[dict], list[dict]]:
    universe: set[str] = set()
    for meta in ml.scan_knowledge(workspace):
        for t in meta.get("tags") or []:
            if isinstance(t, str):
                universe.add(t)
    scored = [(idx, _density(c, universe), c) for idx, c in enumerate(candidates)]
    scored.sort(key=lambda x: (-x[1], x[0]))
    kept = [c for _, _, c in scored[:PER_TASK_CAP]]
    dropped = [c for _, _, c in scored[PER_TASK_CAP:]]
    return kept, dropped


# ------------------------------------------------------- normalization


def _normalize_candidate(cand: dict) -> tuple[dict, bool]:
    """Truncate summary/tags. Returns (normalized, was_truncated)."""
    truncated = False
    summary = str(cand.get("summary") or "")
    if len(summary) > MAX_SUMMARY:
        summary = summary[:MAX_SUMMARY]
        truncated = True
    tags_raw = cand.get("tags") or []
    tags = [str(t) for t in tags_raw if isinstance(t, (str, int, float))]
    if len(tags) > MAX_TAGS:
        tags = tags[:MAX_TAGS]
        truncated = True
    body = str(cand.get("body") or "")
    title = str(cand.get("title") or "untitled")
    topic = str(cand.get("topic") or "") or _slugify(title)
    topic = _slugify(topic, fallback="knowledge")
    return (
        {
            "title": title,
            "topic": topic,
            "summary": summary,
            "tags": tags,
            "body": body,
        },
        truncated,
    )


# -------------------------------------------------------- decision flow


def _process_candidate(
    workspace: Path, task_id: str, cand: dict, route: str = "cross_task"
) -> tuple[str, str, str | None]:
    """Process one candidate. Returns (outcome, verdict, written_or_target_path)."""
    body = cand["body"]
    topic = cand["topic"]
    title = cand["title"]
    summary = cand["summary"]
    tags = cand["tags"]

    # Step 1: secret-scan (fail-close).
    hit, rule_id = _scan_secrets(body)
    if hit:
        # Redact body in the audit reason field (NFR-SECURITY).
        _ = _redact(body)
        _audit(
            workspace,
            outcome="blocked_secret",
            verdict="blocked",
            reason=f"secret-scanner:{rule_id}",
            source_task=task_id,
            candidate_hash=memory_index.get_hash(_redact(body)),
            extra={"route": route},
        )
        raise _SecretBlocked(rule_id or "unknown")

    candidate_hash = memory_index.get_hash(body)

    # Step 2: hash dedup — short-circuit before any LLM judge call.
    exists = ml.has_hash(workspace, "knowledge", candidate_hash)
    if exists:
        existing_path = None
        for meta in ml.scan_knowledge(workspace):
            if meta.get("dedup_hash") == candidate_hash:
                existing_path = meta.get("path")
                break
        _audit(
            workspace,
            outcome="dedup",
            verdict="dedup",
            reason="hash-match",
            source_task=task_id,
            candidate_hash=candidate_hash,
            existing_path=existing_path,
            extra={"route": route, "dest_path": existing_path},
        )
        return "dedup", "dedup", existing_path

    # Step 3: similarity search.
    similar = ml.find_similar(workspace, "knowledge", title, tags)

    # Step 4: LLM judge (only if similar found).
    if similar:
        existing = similar[0]
        decide_raw = call_llm(
            _build_decide_prompt(existing, cand),
            call_name="decide",
        )
        try:
            verdict_obj = _parse_json_payload(decide_raw)
        except Exception:
            verdict_obj = {"action": "create", "rationale": "judge-parse-failed"}
        action = verdict_obj.get("action", "create")
        rationale = str(verdict_obj.get("rationale", ""))[:200]
        existing_path = existing.get("path")
    else:
        action = "create"
        rationale = "no similar found"
        existing_path = None

    # Step 5: execute.
    if action == "merge" and existing_path:
        existing_topic = Path(existing_path).stem

        def _mutate(doc: dict) -> dict:
            fm = dict(doc.get("frontmatter") or {})
            fm["status"] = fm.get("status", "candidate")
            existing_tags = list(fm.get("tags") or [])
            for t in tags:
                if t not in existing_tags:
                    existing_tags.append(t)
            fm["tags"] = existing_tags[:MAX_TAGS]
            related = list(fm.get("related_tasks") or [])
            if task_id and task_id not in related:
                related.append(task_id)
            fm["related_tasks"] = related
            new_body = (doc.get("body") or "") + "\n\n" + body
            return {"frontmatter": fm, "body": new_body[:8192]}

        ml.patch_knowledge(
            workspace, topic=existing_topic, mutator=_mutate, rationale=rationale
        )
        _audit(
            workspace,
            outcome="merged",
            verdict="merge",
            reason=rationale,
            source_task=task_id,
            candidate_hash=candidate_hash,
            existing_path=existing_path,
            extra={"route": route, "dest_path": existing_path},
        )
        return "merged", "merge", existing_path

    if action == "replace" and existing_path:
        existing_topic = Path(existing_path).stem
        new_fm = {
            "title": title,
            "summary": summary,
            "tags": tags,
            "status": "candidate",
            "source_task": task_id,
            "created_from_task": task_id,
            "created_at": _now_iso(),
            "hash": candidate_hash,
            "topic": existing_topic,
        }
        ml.replace_knowledge(
            workspace,
            topic=existing_topic,
            frontmatter=new_fm,
            body=body,
            rationale=rationale,
        )
        _audit(
            workspace,
            outcome="replaced",
            verdict="replace",
            reason=rationale,
            source_task=task_id,
            candidate_hash=candidate_hash,
            existing_path=existing_path,
            extra={"route": route, "dest_path": existing_path},
        )
        return "replaced", "replace", existing_path

    # action == "create" (or fallback). If a same-named topic already
    # exists, append a unix-ts suffix to keep both copies (FR-LAY-3).
    target_topic = topic
    target_path = ml._knowledge_path(workspace, target_topic)
    suffixed = False
    if target_path.exists():
        target_topic = f"{topic}-{int(_dt.datetime.now().timestamp())}"
        target_topic = target_topic[: ml.MAX_TOPIC_CHARS]
        suffixed = True
    new_fm = {
        "title": title,
        "summary": summary,
        "tags": tags,
        "status": "candidate",
        "source_task": task_id,
        "created_from_task": task_id,
        "created_at": _now_iso(),
        "hash": candidate_hash,
        "topic": target_topic,
    }
    # Change D: record per-role provenance when aggregated (no per-role
    # file is written — this list *is* the by_role→by_topic reference).
    source_roles = cand.get("_source_roles") or []
    if source_roles:
        new_fm["sources_by_role"] = list(source_roles)
    if task_id:
        new_fm["sources"] = [task_id]
    written = ml.write_knowledge(
        workspace,
        topic=target_topic,
        summary=summary,
        tags=tags,
        body=body,
        frontmatter=new_fm,
        status="candidate",
        created_from_task=task_id,
        # Finding 3 (review): when we've already decided to suffix the
        # topic (FR-LAY-3 collision path), the extractor is explicitly
        # asking for a distinct entry — don't let fuzzy-merge fold it
        # back into the sibling it tried to distinguish from.
        fuzzy_merge=not suffixed,
    )
    _audit(
        workspace,
        outcome="created",
        verdict="create",
        reason=rationale + (" (suffixed)" if suffixed else ""),
        source_task=task_id,
        candidate_hash=candidate_hash,
        existing_path=existing_path,
        extra={"route": route, "dest_path": str(written)},
    )
    return "created", "create", str(written)


class _SecretBlocked(Exception):
    """Internal signal — bubble up so main() exits non-zero per TC-M9.3-12."""


# -------------------------------------------------------------------- main


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="knowledge-extractor")
    p.add_argument("--task-id", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--phase", default="")
    p.add_argument("--reason", default="")
    p.add_argument("--input", default=None, help="Optional explicit input file")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    workspace = Path(args.workspace).resolve()
    task_id = args.task_id
    phase = args.phase
    reason = args.reason
    input_path = Path(args.input).resolve() if args.input else None

    route = os.environ.get("CN_EXTRACTION_ROUTE_KNOWLEDGE", "cross_task").strip()
    if route != "cross_task":
        route = "cross_task"

    # Memory skeleton must exist (M9.1 init) — best-effort if missing.
    if not ml.has_memory(workspace):
        try:
            ml.init_memory_skeleton(workspace)
        except Exception:
            print("[best-effort] memory skeleton missing", file=sys.stderr)
            return 0

    ml.append_audit(
        workspace,
        {
            "ts": _now_iso(),
            "event": "extract_started",
            "asset_type": "knowledge",
            "task_id": task_id,
            "phase": phase,
            "reason": reason,
        },
    )

    secret_blocked = False
    try:
        # E2E-009: prefer YAML-frontmatter `extract:` blocks emitted by
        # role outputs. Fall back to the LLM-driven path only if no role
        # outputs exist.
        cands_raw: list[dict] | None
        cands_raw = _candidates_from_role_outputs(workspace, task_id)
        used_frontmatter = cands_raw is not None
        if used_frontmatter and not cands_raw:
            ml.append_audit(
                workspace,
                {
                    "ts": _now_iso(),
                    "event": "extract_complete",
                    "asset_type": "knowledge",
                    "task_id": task_id,
                    "status": "no_candidates",
                    "reason": "role outputs present but no `extract:` frontmatter block",
                },
            )
            return 0
        if cands_raw is None:
            body_in = _read_task_context(workspace, task_id, input_path)
            prompt = _build_extract_prompt(task_id, phase, reason, body_in)
            try:
                raw = call_llm(prompt, call_name="extract")
            except Exception as e:
                print(f"[best-effort] llm call failed: {e}", file=sys.stderr)
                ml.append_audit(
                    workspace,
                    {
                        "ts": _now_iso(),
                        "event": "extract_failed",
                        "asset_type": "knowledge",
                        "task_id": task_id,
                        "status": "failed",
                        "reason": str(e)[:200],
                    },
                )
                return 0

            try:
                payload = _parse_json_payload(raw)
                cands_raw = payload.get("candidates") or []
                if not isinstance(cands_raw, list):
                    raise ValueError("candidates must be a list")
            except Exception as e:
                print(f"[best-effort] candidate parse failed: {e}", file=sys.stderr)
                ml.append_audit(
                    workspace,
                    {
                        "ts": _now_iso(),
                        "event": "extract_failed",
                        "asset_type": "knowledge",
                        "task_id": task_id,
                        "status": "failed",
                        "reason": f"parse: {e}"[:200],
                    },
                )
                return 0

        normalized: list[dict] = []
        for cand in cands_raw:
            if not isinstance(cand, dict):
                continue
            n, was_trunc = _normalize_candidate(cand)
            # Preserve the aggregator-injected source hints through the
            # normalization step so _process_candidate can record them.
            for _k in ("_source_roles", "_source_files", "_aggregated",
                       "_source_role", "_source_file"):
                if _k in cand and _k not in n:
                    n[_k] = cand[_k]
            if was_trunc:
                ml.append_audit(
                    workspace,
                    {
                        "ts": _now_iso(),
                        "event": "candidate_truncated",
                        "asset_type": "knowledge",
                        "task_id": task_id,
                        "topic": n["topic"],
                        "truncated": True,
                    },
                )
            normalized.append(n)

        # ── Change D: collapse per-role candidates into one synthesized
        # entry per task so we never produce four near-identical files
        # for a single T-NNN.
        if used_frontmatter and len(normalized) > 1:
            before = len(normalized)
            normalized = _aggregate_candidates_per_task(normalized, task_id)
            ml.append_audit(
                workspace,
                {
                    "ts": _now_iso(),
                    "event": "candidates_aggregated",
                    "asset_type": "knowledge",
                    "task_id": task_id,
                    "before": before,
                    "after": len(normalized),
                },
            )

        kept, dropped = _rank_and_cap(normalized, workspace, task_id=task_id, route=route)
        if dropped:
            ml.append_audit(
                workspace,
                {
                    "ts": _now_iso(),
                    "event": "cap_truncated",
                    "asset_type": "knowledge",
                    "task_id": task_id,
                    "dropped_by_cap": len(dropped),
                },
            )

        for cand in kept:
            try:
                _process_candidate(workspace, task_id, cand, route=route)
            except _SecretBlocked:
                secret_blocked = True
                # Continue processing other candidates so they still
                # get a fair audit; we'll exit non-zero at the end.
                continue
            except Exception as e:
                print(
                    f"[best-effort] candidate processing failed: {e}",
                    file=sys.stderr,
                )
                _audit(
                    workspace,
                    outcome="failed",
                    verdict="failed",
                    reason=str(e)[:200],
                    source_task=task_id,
                )
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        ml.append_audit(
            workspace,
            {
                "ts": _now_iso(),
                "event": "extract_failed",
                "asset_type": "knowledge",
                "task_id": task_id,
                "status": "failed",
                "reason": str(e)[:200],
            },
        )
        return 0

    if secret_blocked:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
