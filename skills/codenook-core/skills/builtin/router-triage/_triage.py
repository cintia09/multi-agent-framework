#!/usr/bin/env python3
"""router-triage core. Invoked by triage.sh.

Decision algorithm (architecture §4 / M3 spec):
  1. Builtin intent table (regex on common verbs)
  2. Plugin intent_patterns from each installed manifest
  3. Fall-through to chat (low confidence) or hitl (tied plugins)

Confidence calibration (M3, intentionally simple):
  * builtin skill match: 0.9
  * single plugin regex match: 0.85
  * multiple plugin matches (hitl): 0.55
  * chat fall-through: 0.30
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from manifest_load import load_all  # noqa: E402

# Reject pathological plugin patterns before compiling them — a
# malicious manifest could otherwise stall the router with an
# exponential-backtrack regex like (a+)+b on adversarial input.
PATTERN_MAX_LEN = 256
REDOS_BLACKLIST = re.compile(
    r"(\([^)]*[+*]\)[+*])"          # (a+)+ , (.*)*  ...
    r"|(\([^)]*\\[swdSWD]\+\)[+*])"  # (\w+)+ , (\d+)*
)


def regex_is_safe(pat: str) -> bool:
    if len(pat) > PATTERN_MAX_LEN:
        return False
    if REDOS_BLACKLIST.search(pat):
        return False
    return True

# ---------------------------------------------------------------- builtin table
BUILTIN_INTENTS: list[tuple[str, re.Pattern[str]]] = [
    ("list-plugins", re.compile(r"\b(list|show)\b.*\bplugins?\b", re.IGNORECASE)),
    ("show-config",  re.compile(r"\b(show|print)\b.*\b(config|settings)\b", re.IGNORECASE)),
    ("help",         re.compile(r"\bhelp\b", re.IGNORECASE)),
]


def match_builtin(text: str) -> tuple[str, str] | None:
    """Return (skill_name, matched_pattern_repr) or None."""
    for name, pat in BUILTIN_INTENTS:
        if pat.search(text):
            return name, pat.pattern
    return None


def match_plugins(text: str, manifests: list[dict],
                  reasons: list[str] | None = None) -> list[tuple[str, str]]:
    """Return list of (plugin_id, matched_pattern) — empty if none.

    Patterns failing the ReDoS safety check are skipped and recorded in
    reasons[] (when provided).
    """
    hits: list[tuple[str, str]] = []
    for m in manifests:
        if "_error" in m:
            continue
        for pat_str in m.get("intent_patterns") or []:
            if not regex_is_safe(pat_str):
                if reasons is not None:
                    reasons.append(
                        f"regex rejected: ReDoS risk ({m.get('id')}: {pat_str!r})"
                    )
                continue
            try:
                if re.search(pat_str, text, re.IGNORECASE):
                    hits.append((m["id"], pat_str))
                    break  # one match per plugin is enough
            except re.error:
                continue
    return hits


def build_dispatch(target: str, role_hint: str, user_input: str,
                   task: str, ws: Path, build_sh: str) -> tuple[str | None, str | None]:
    """Return (payload_json_or_None, error_or_None)."""
    cmd = [build_sh, "--target", target, "--user-input", user_input,
           "--workspace", str(ws), "--json"]
    if task:
        cmd += ["--task", task]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        return None, f"dispatch-build exec failed: {e}"
    if res.returncode != 0:
        return None, f"dispatch-build rc={res.returncode}: {res.stderr.strip()}"
    return res.stdout.strip(), None


def main() -> int:
    user_input = os.environ["CN_USER_INPUT"]
    task       = os.environ.get("CN_TASK", "")
    ws         = Path(os.environ["CN_WORKSPACE"]).resolve()
    build_sh   = os.environ["CN_BUILD_SH"]

    manifests = load_all(ws)
    reasons: list[str] = []
    decision   = "chat"
    target: str | None = None
    confidence = 0.30
    dispatch_payload: str | None = None

    # 1. builtin
    bi = match_builtin(user_input)
    if bi:
        decision   = "skill"
        target     = bi[0]
        confidence = 0.9
        reasons.append(f"builtin intent matched: {bi[1]!r}")
        payload, err = build_dispatch(target, "builtin-skill",
                                      user_input, task, ws, build_sh)
        if err:
            reasons.append(f"dispatch_payload unavailable: {err}")
        dispatch_payload = payload

    else:
        # 2. plugin patterns
        hits = match_plugins(user_input, manifests, reasons)
        if len(hits) == 1:
            target = hits[0][0]
            decision = "plugin"
            confidence = 0.85
            reasons.append(f"matched intent regex {hits[0][1]!r} → {target}")
            payload, err = build_dispatch(target, "plugin-worker",
                                          user_input, task, ws, build_sh)
            if err:
                reasons.append(f"dispatch_payload unavailable: {err}")
            dispatch_payload = payload
        elif len(hits) >= 2:
            decision = "hitl"
            confidence = 0.55
            reasons.append("multiple plugins matched — ask user to pick: "
                           + ", ".join(h[0] for h in hits))
        else:
            # 3. chat fall-through
            decision = "chat"
            confidence = 0.30
            reasons.append("no builtin or plugin pattern matched — falling back to chat")

    out = {
        "decision":         decision,
        "target":           target,
        "confidence":       confidence,
        "reasons":          reasons,
        "dispatch_payload": dispatch_payload,
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
