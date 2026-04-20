#!/usr/bin/env python3
"""config-extractor — M9.5.

Detects repeated configuration signals in a phase log (env-var assignments,
port numbers, paths, model names, threshold tuning, explicit
``task-config-set k=v`` calls) and proposes ``config.yaml entries[]`` via
the shared patch-or-create decision flow:

    pre-filter (≥2 distinct signals) → LLM extract → secret-scan
        → cap=5 → for each candidate:
            same-key match? → LLM `decide` (anti-bloat: default merge)
            else            → upsert (create)

Per-task cap = 5 (FR-EXT-CAP for config). Best-effort: failures audit
``status=failed`` and exit 0; secret-blocked candidates exit non-zero so
the dispatcher surfaces the rejection (parity with M9.3 / M9.4).

CLI (M9.0 handoff contract, identical to knowledge / skill extractor):
    extract.py --task-id <id> --workspace <ws> --phase <phase> --reason <r>
               [--input <file>]

Audit-log schema (8 keys, locked by TC-M9.3-09 / TC-M9.4-04 / TC-M9.5-05):
    {asset_type, candidate_hash, existing_path, outcome, reason,
     source_task, timestamp, verdict}
``asset_type`` is always ``"config"``.
``outcome`` ∈ {created, merged, replaced, blocked_secret, failed,
              dropped_by_cap, below_threshold, schema_error}.
``verdict`` ∈ {create, merge, replace, blocked, failed, dropped, noop}.
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

PER_TASK_CAP = 5
MIN_DISTINCT_SIGNALS = 2  # ≥2 distinct config signals to invoke the LLM.
MAX_APPLIES_WHEN = 200    # spec §4.1
MAX_SUMMARY = 120         # spec §4.1
INPUT_BODY_TRUNC = 4096

# Pre-filter: KEY=VALUE-shaped lines or `task-config-set k=v`.
# Key ≥ 2 chars, allowed: alnum/dot/underscore/hyphen.
_KV_RE = re.compile(
    r"(?:^|[\s])(?:task-config-set\s+)?"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_.\-]{1,63})\s*=\s*"
    r"(?P<val>[^\s#]+)"
)


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        asset_type="config",
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
            for p in sorted(notes_dir.glob("*.md")):
                try:
                    chunks.append(p.read_text(encoding="utf-8"))
                except OSError:
                    pass
    return ("\n\n".join(chunks))[:INPUT_BODY_TRUNC]


# --------------------------------------------------------- detection gate


# Treat shell builtins / common keywords as noise — they show up as
# `KEY=VAL` in `export FOO=bar` lines but the key is meaningful, so we
# only filter pure-noise tokens.
_NOISE_KEYS = {"PS1", "PS2", "IFS"}


def _has_config_signals(text: str) -> tuple[bool, set[str]]:
    """Return ``(meets, distinct_keys)``.

    Counts distinct KEY=VAL tokens (and ``task-config-set k=v``). Gates
    at ``MIN_DISTINCT_SIGNALS`` (≥2). Pure noise keys are filtered.
    """
    distinct: set[str] = set()
    for m in _KV_RE.finditer(text or ""):
        key = m.group("key")
        if key in _NOISE_KEYS:
            continue
        distinct.add(key)
    return (len(distinct) >= MIN_DISTINCT_SIGNALS, distinct)


# ------------------------------------------------------------ LLM helpers


def _build_extract_prompt(
    task_id: str, phase: str, reason: str, body: str, distinct: set[str]
) -> str:
    keys = ", ".join(sorted(distinct)[:20]) or "(none)"
    return (
        "You are CodeNook's config extractor.\n"
        f"Task: {task_id}  Phase: {phase}  Reason: {reason}\n\n"
        "Identify durable project-level configuration entries (NOT one-off\n"
        "values). Detected distinct config keys in the phase log:\n"
        f"  {keys}\n\n"
        "Respond with strict JSON of the form:\n"
        '  {"candidates":[{"key":..,"value":..,"applies_when":..,"summary":..}]}\n'
        f"Constraints: ≤ {PER_TASK_CAP} candidates, applies_when ≤"
        f" {MAX_APPLIES_WHEN} chars, summary ≤ {MAX_SUMMARY} chars,\n"
        "no secrets / PII. Prefer reusable, value-typed entries.\n\n"
        "## Phase log (truncated)\n"
        f"{body}\n"
    )


def _build_decide_prompt(existing: dict, candidate: dict) -> str:
    return (
        "Decide how to merge a new config entry candidate into existing memory.\n"
        "Anti-bloat bias: default to MERGE unless the new candidate has a\n"
        "fundamentally different scope (different applies_when domain).\n\n"
        "## Existing\n"
        f"key: {existing.get('key','')}\n"
        f"value: {existing.get('value','')!r}\n"
        f"applies_when: {existing.get('applies_when','')}\n"
        f"summary: {existing.get('summary','')}\n\n"
        "## New candidate\n"
        f"key: {candidate.get('key','')}\n"
        f"value: {candidate.get('value','')!r}\n"
        f"applies_when: {candidate.get('applies_when','')}\n"
        f"summary: {candidate.get('summary','')}\n\n"
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


# ------------------------------------------------------- normalization


def _normalize_candidate(cand: dict) -> tuple[dict | None, bool]:
    """Return ``(normalized, was_truncated)`` or ``(None, False)`` if invalid."""
    key = str(cand.get("key") or "").strip()
    if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$", key):
        return None, False
    truncated = False
    aw = str(cand.get("applies_when") or "always")
    if len(aw) > MAX_APPLIES_WHEN:
        aw = aw[:MAX_APPLIES_WHEN]
        truncated = True
    summary = str(cand.get("summary") or "")
    if len(summary) > MAX_SUMMARY:
        summary = summary[:MAX_SUMMARY]
        truncated = True
    value = cand.get("value")
    return (
        {
            "key": key,
            "value": value,
            "applies_when": aw,
            "summary": summary,
        },
        truncated,
    )


def _candidate_hash(cand: dict) -> str:
    blob = json.dumps(
        {"key": cand["key"], "value": cand.get("value")},
        sort_keys=True,
        ensure_ascii=False,
    )
    return memory_index.get_hash(blob)


def _candidate_text_blob(cand: dict) -> str:
    """All textual fields concatenated for secret scanning."""
    return "\n".join(
        str(x) for x in (
            cand.get("key", ""),
            cand.get("value", ""),
            cand.get("applies_when", ""),
            cand.get("summary", ""),
        )
    )


# -------------------------------------------------------- decision flow


class _SecretBlocked(Exception):
    """Bubble up so main() exits non-zero on secret-blocked candidates."""


def _find_existing_by_key(entries: list[dict], key: str) -> dict | None:
    for e in entries:
        if e.get("key") == key:
            return e
    return None


def _process_candidate(
    workspace: Path,
    task_id: str,
    cand: dict,
    existing_entries: list[dict],
    route: str = "cross_task",
) -> tuple[str, str]:
    is_task_route = route == "task_specific"
    key = cand["key"]
    blob = _candidate_text_blob(cand)

    # Step 1: secret scan.
    hit, rule_id = _scan_secrets(blob)
    if hit:
        _ = _redact(blob)
        _audit(
            workspace,
            outcome="blocked_secret",
            verdict="blocked",
            reason=f"secret-scanner:{rule_id}",
            source_task=task_id,
            candidate_hash=_candidate_hash(cand),
            extra={"route": route},
        )
        raise _SecretBlocked(rule_id or "unknown")

    cand_hash = _candidate_hash(cand)
    existing = _find_existing_by_key(existing_entries, key)

    # Step 2: same-key match → call decide LLM (anti-bloat: default merge).
    if existing is not None:
        try:
            decide_raw = call_llm(
                _build_decide_prompt(existing, cand),
                call_name="decide",
            )
            verdict_obj = _parse_json_payload(decide_raw)
            action = verdict_obj.get("action", "merge") or "merge"
            rationale = str(verdict_obj.get("rationale", ""))[:200]
        except Exception as e:
            action = "merge"
            rationale = f"decide-fallback: {e}"[:200]
    else:
        action = "create"
        rationale = "no existing key"

    # `create` against an existing key would conflict — coerce to merge.
    if existing is not None and action == "create":
        action = "merge"
        rationale = f"coerced-merge ({rationale})"[:200]

    # Step 3: execute.
    entry_payload: dict = {
        "key": key,
        "value": cand.get("value"),
        "applies_when": cand["applies_when"],
        "summary": cand["summary"],
        "status": "candidate",
        "created_from_task": task_id,
    }

    def _do_upsert(rationale_str: str) -> None:
        if is_task_route:
            ml.upsert_config_to_task(
                workspace, task_id, entry=entry_payload, rationale=rationale_str
            )
        else:
            ml.upsert_config_entry(
                workspace, entry=entry_payload, rationale=rationale_str
            )

    if action == "replace":
        _do_upsert(rationale or "replace")
        outcome, verdict = "replaced", "replace"
    elif action == "merge":
        _do_upsert(rationale or "merge")
        outcome, verdict = "merged", "merge"
    else:  # create (no existing)
        _do_upsert(rationale or "create")
        outcome, verdict = "created", "create"

    if is_task_route:
        dest_path = str(ml._task_config_path(workspace, task_id))
    else:
        dest_path = "config.yaml"

    _audit(
        workspace,
        outcome=outcome,
        verdict=verdict,
        reason=rationale,
        source_task=task_id,
        candidate_hash=cand_hash,
        existing_path=(dest_path if existing is not None else None),
        extra={"route": route, "dest_path": dest_path},
    )
    return outcome, verdict


# -------------------------------------------------------------------- main


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="config-extractor")
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

    route = os.environ.get("CN_EXTRACTION_ROUTE_CONFIG", "cross_task").strip()
    if route not in ("task_specific", "cross_task"):
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
            "asset_type": "config",
            "task_id": task_id,
            "phase": phase,
            "reason": reason,
        },
    )

    secret_blocked = False
    try:
        body_in = _read_task_context(workspace, task_id, input_path)

        # Detection gate: ≥2 distinct config signals before any LLM call.
        meets, distinct = _has_config_signals(body_in)
        if not meets:
            _audit(
                workspace,
                outcome="below_threshold",
                verdict="noop",
                reason=f"distinct_signals={len(distinct)}",
                source_task=task_id,
            )
            return 0

        # Read existing entries early — fails fast on duplicate-key schema
        # violations (TC-M9.5-02) without ever touching the file.
        try:
            if route == "task_specific":
                existing_entries = ml.read_task_config_entries(workspace, task_id)
            else:
                existing_entries = ml.read_config_entries(workspace)
        except Exception as e:
            ml.append_audit(
                workspace,
                {
                    "ts": _now_iso(),
                    "event": "extract_failed",
                    "asset_type": "config",
                    "task_id": task_id,
                    "status": "failed",
                    "reason": f"schema: {e}"[:200],
                },
            )
            _audit(
                workspace,
                outcome="schema_error",
                verdict="failed",
                reason=f"duplicate or malformed: {e}"[:200],
                source_task=task_id,
            )
            return 0

        prompt = _build_extract_prompt(task_id, phase, reason, body_in, distinct)
        try:
            raw = call_llm(prompt, call_name="extract")
        except Exception as e:
            print(f"[best-effort] llm call failed: {e}", file=sys.stderr)
            ml.append_audit(
                workspace,
                {
                    "ts": _now_iso(),
                    "event": "extract_failed",
                    "asset_type": "config",
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
                    "asset_type": "config",
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
            if n is None:
                continue
            if was_trunc:
                ml.append_audit(
                    workspace,
                    {
                        "ts": _now_iso(),
                        "event": "candidate_truncated",
                        "asset_type": "config",
                        "task_id": task_id,
                        "key": n["key"],
                        "truncated": True,
                    },
                )
            normalized.append(n)

        # Cap (FR-EXT-CAP). Stable order: as the LLM proposed.
        kept = normalized[:PER_TASK_CAP]
        dropped = normalized[PER_TASK_CAP:]
        if dropped:
            ml.append_audit(
                workspace,
                {
                    "ts": _now_iso(),
                    "event": "cap_truncated",
                    "asset_type": "config",
                    "task_id": task_id,
                    "dropped_by_cap": len(dropped),
                },
            )

        for cand in kept:
            try:
                _process_candidate(workspace, task_id, cand, existing_entries, route=route)
                # Refresh existing_entries view after each upsert so a
                # later candidate with the same key sees the prior write.
                try:
                    if route == "task_specific":
                        existing_entries = ml.read_task_config_entries(workspace, task_id)
                    else:
                        existing_entries = ml.read_config_entries(workspace)
                except Exception:
                    pass
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
                "asset_type": "config",
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
