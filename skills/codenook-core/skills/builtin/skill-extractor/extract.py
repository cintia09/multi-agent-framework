#!/usr/bin/env python3
"""skill-extractor — M9.4.

Detects repeated script / CLI invocations (≥3 within the same phase log)
and proposes reusable ``skill`` candidates. Each candidate runs through
the shared patch-or-create decision flow:

    secret-scan → hash dedup → similarity → LLM judge → write/patch

Per-task cap = 1 (FR-EXT-CAP for skills). Best-effort: failures audit
``status=failed`` and exit 0; secret-blocked candidates exit non-zero so
the dispatcher surfaces the rejection (parity with M9.3).

CLI (M9.0 handoff contract, identical to knowledge-extractor):
    extract.py --task-id <id> --workspace <ws> --phase <phase> --reason <r>
               [--input <file>]

Audit-log schema (8 keys, locked by TC-M9.4-04):
    {asset_type, candidate_hash, existing_path, outcome, reason,
     source_task, timestamp, verdict}
``asset_type`` is always ``"skill"``.
``outcome`` ∈ {created, merged, replaced, dedup, blocked_secret, failed,
              dropped_by_cap, below_threshold}.
``verdict`` ∈ {create, merge, replace, dedup, blocked, failed, dropped, noop}.
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

PER_TASK_CAP = 1
MIN_REPEAT_THRESHOLD = 2  # v0.27.0: lowered from 3 to 2 — three+ invocations
MAX_SUMMARY = ml.MAX_SUMMARY_CHARS  # 200
MAX_TAGS = ml.MAX_TAGS  # 8
INPUT_BODY_TRUNC = 4096

# Skill names share memory_layer's flat-name validation: must start
# alphanum and contain only [A-Za-z0-9_.-]. Same regex is fine.
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.\-]+")

# Pre-filter: shell/CLI invocation pattern. Captures the first arg
# (script name or subcommand) so we can group / count repeats.
_INVOCATION_RE = re.compile(
    r"(?:^|\s)(?:"
    r"(?:bash|sh|zsh|python3?|node|npm|yarn|pnpm|make|cargo|go)\s+(\S+)"
    r"|"
    r"(\./\S+)"
    r")"
)


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str, fallback: str = "skill") -> str:
    s = _SLUG_RE.sub("-", (text or "").strip().lower()).strip("-")
    if not s:
        s = fallback
    if not re.match(r"^[A-Za-z0-9]", s):
        s = "s-" + s
    return s[: ml.MAX_TOPIC_CHARS]


def _audit(
    workspace: Path,
    *,
    outcome: str,
    verdict: str,
    reason: str = "",
    source_task: str = "",
    candidate_hash: str = "",
    existing_path: str | None = None,
    extra: dict | None = None,
) -> None:
    _audit_canonical(
        workspace,
        asset_type="skill",
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
                chunks.append("\n".join(lines[-200:]))
            except OSError:
                pass
        notes_dir = task_dir / "notes"
        if notes_dir.is_dir():
            # M9.4 R2-01: include .md, .txt, and .log alongside notes/*.md
            # so plain-text task notes and rotated logs participate in the
            # extractor's repeat-pattern detection.
            for p in sorted(notes_dir.glob("*")):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in {".md", ".txt", ".log"}:
                    continue
                try:
                    chunks.append(p.read_text(encoding="utf-8"))
                except OSError:
                    pass
    return ("\n\n".join(chunks))[:INPUT_BODY_TRUNC]


# --------------------------------------------------------- detection gate


def _count_repeats(text: str) -> dict[str, int]:
    """Return ``{first-arg-token: count}`` for shell/CLI invocations."""
    counts: dict[str, int] = {}
    for m in _INVOCATION_RE.finditer(text or ""):
        raw = (m.group(1) or m.group(2) or "").strip()
        if not raw:
            continue
        key = raw[2:] if raw.startswith("./") else raw
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _meets_threshold(text: str) -> tuple[bool, dict[str, int]]:
    counts = _count_repeats(text)
    qualifying = {k: v for k, v in counts.items() if v >= MIN_REPEAT_THRESHOLD}
    return (bool(qualifying), qualifying)


# ------------------------------------------------------------ LLM helpers


def _build_extract_prompt(
    task_id: str, phase: str, reason: str, body: str, qualifying: dict[str, int]
) -> str:
    repeats = "\n".join(f"- `{k}` invoked {v} times" for k, v in qualifying.items())
    return (
        "You are CodeNook's skill extractor.\n"
        f"Task: {task_id}  Phase: {phase}  Reason: {reason}\n\n"
        "Only propose a skill if you observe a repeated script / CLI\n"
        f"pattern invoked at least {MIN_REPEAT_THRESHOLD} times within the\n"
        "phase. Detected repeats:\n"
        f"{repeats}\n\n"
        "Respond with strict JSON of the form:\n"
        '  {"candidates":[{"name":..,"title":..,"summary":..,"tags":[..],"body":..}]}\n'
        "Constraints: name ≤ 64 alphanum/-_./ only, summary ≤ 200 chars,\n"
        "tags ≤ 8, no secrets, no PII. Per-task cap = 1.\n\n"
        "## Phase log (truncated)\n"
        f"{body}\n"
    )


def _build_decide_prompt(existing: dict, candidate: dict) -> str:
    return (
        "Decide how to merge a new skill candidate into existing memory.\n"
        "Default preference: merge.\n\n"
        "## Existing\n"
        f"name: {existing.get('name') or existing.get('title','')}\n"
        f"tags: {existing.get('tags',[])}\n\n"
        "## New candidate\n"
        f"name: {candidate.get('name','')}\n"
        f"tags: {candidate.get('tags',[])}\n\n"
        '## Output JSON\n{ "action": "merge"|"replace"|"create",'
        ' "rationale": "<≤200 chars>" }'
    )


def _parse_json_payload(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty LLM response")
    if raw.startswith("```"):
        first_nl = raw.find("\n")
        last_fence = raw.rfind("```")
        if first_nl >= 0 and last_fence > first_nl:
            raw = raw[first_nl + 1 : last_fence].strip()
    return json.loads(raw)


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
    for meta in ml.scan_skills(workspace):
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
    name = str(cand.get("name") or "") or _slugify(title)
    name = _slugify(name, fallback="skill")
    return (
        {
            "name": name,
            "title": title,
            "summary": summary,
            "tags": tags,
            "body": body,
        },
        truncated,
    )


# -------------------------------------------------------- decision flow


class _SecretBlocked(Exception):
    """Bubble up so main() exits non-zero on secret-blocked candidates."""


def _existing_skill_name_from_path(path: str) -> str:
    return Path(path).parent.name


def _process_candidate(
    workspace: Path, task_id: str, cand: dict, route: str = "cross_task"
) -> tuple[str, str, str | None]:
    body = cand["body"]
    name = cand["name"]
    title = cand["title"]
    summary = cand["summary"]
    tags = cand["tags"]

    # Step 1: secret scan.
    hit, rule_id = _scan_secrets(body)
    if hit:
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

    # Step 2: hash dedup.
    exists = ml.has_hash(workspace, "skill", candidate_hash)
    if exists:
        existing_path = None
        for meta in ml.scan_skills(workspace):
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
    similar = ml.find_similar(workspace, "skill", title, tags)

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
        existing_name = (
            _existing_skill_name_from_path(existing_path) if existing_path else None
        )
    else:
        action = "create"
        rationale = "no similar found"
        existing_path = None
        existing_name = None

    # Step 5: execute.
    if action == "merge" and existing_name:
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

        ml.patch_skill(
            workspace, name=existing_name, mutator=_mutate, rationale=rationale
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

    if action == "replace" and existing_name:
        new_fm = {
            "name": existing_name,
            "title": title,
            "summary": summary,
            "tags": tags,
            "status": "candidate",
            "source_task": task_id,
            "created_from_task": task_id,
            "created_at": _now_iso(),
        }
        ml.write_skill(
            workspace,
            name=existing_name,
            frontmatter=new_fm,
            body=body,
            status="candidate",
            created_from_task=task_id,
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

    # Default: create. If a same-named skill dir already exists, append
    # a unix-ts suffix to avoid clobbering.
    target_name = name
    suffixed = False
    target_skill_md = ml.memory_root(workspace) / "skills" / target_name / "SKILL.md"
    if target_skill_md.exists():
        target_name = f"{name}-{int(_dt.datetime.now().timestamp())}"
        target_name = target_name[: ml.MAX_TOPIC_CHARS]
        suffixed = True
    new_fm = {
        "name": target_name,
        "title": title,
        "summary": summary,
        "tags": tags,
        "status": "candidate",
        "source_task": task_id,
        "created_from_task": task_id,
        "created_at": _now_iso(),
    }
    written = ml.write_skill(
        workspace,
        name=target_name,
        frontmatter=new_fm,
        body=body,
        status="candidate",
        created_from_task=task_id,
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


# -------------------------------------------------------------------- main


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="skill-extractor")
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

    route = os.environ.get("CN_EXTRACTION_ROUTE_SKILL", "cross_task").strip()
    if route != "cross_task":
        route = "cross_task"

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
            "asset_type": "skill",
            "task_id": task_id,
            "phase": phase,
            "reason": reason,
        },
    )

    secret_blocked = False
    try:
        body_in = _read_task_context(workspace, task_id, input_path)

        # Detection gate: bail out before any LLM call when no script
        # invocation passes the ≥2 threshold (FR-EXT-S, TC-M9.4-02).
        meets, qualifying = _meets_threshold(body_in)
        if not meets:
            all_counts = _count_repeats(body_in)
            max_count = max(all_counts.values()) if all_counts else 0
            _audit(
                workspace,
                outcome="below_threshold",
                verdict="noop",
                reason=f"max_count={max_count}",
                source_task=task_id,
            )
            return 0

        prompt = _build_extract_prompt(task_id, phase, reason, body_in, qualifying)
        try:
            raw = call_llm(prompt, call_name="extract")
        except Exception as e:
            print(f"[best-effort] llm call failed: {e}", file=sys.stderr)
            ml.append_audit(
                workspace,
                {
                    "ts": _now_iso(),
                    "event": "extract_failed",
                    "asset_type": "skill",
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
                    "asset_type": "skill",
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
            if was_trunc:
                ml.append_audit(
                    workspace,
                    {
                        "ts": _now_iso(),
                        "event": "candidate_truncated",
                        "asset_type": "skill",
                        "task_id": task_id,
                        "name": n["name"],
                        "truncated": True,
                    },
                )
            normalized.append(n)

        kept, dropped = _rank_and_cap(normalized, workspace, task_id=task_id, route=route)
        if dropped:
            ml.append_audit(
                workspace,
                {
                    "ts": _now_iso(),
                    "event": "cap_truncated",
                    "asset_type": "skill",
                    "task_id": task_id,
                    "dropped_by_cap": len(dropped),
                },
            )

        for cand in kept:
            try:
                _process_candidate(workspace, task_id, cand, route=route)
            except _SecretBlocked:
                secret_blocked = True
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
                "asset_type": "skill",
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
