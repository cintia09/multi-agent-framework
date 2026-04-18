#!/usr/bin/env python3
"""model-probe core algorithm. Invoked by probe.sh.

Reads its inputs from CN_* environment variables (set by probe.sh):
  CN_OUTPUT         optional output file path; '' → stdout
  CN_TIER_PRIORITY  optional YAML file overriding built-in tier_priority
  CN_CHECK_TTL      optional path to a catalog JSON to check freshness
  CN_TTL_DAYS       integer TTL window for --check-ttl

Probe-mode (no --check-ttl): emit a catalog JSON.
TTL-mode (--check-ttl set): exit 0 if fresh, 1 if stale.

On any catastrophic error: stderr starts with 'probe failed:' and exits
non-zero (see SKILL.md).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path


def die(msg: str, code: int = 2) -> None:
    print(f"probe failed: {msg}", file=sys.stderr)
    sys.exit(code)


try:
    import yaml  # PyYAML
except ImportError:
    die("PyYAML not installed (pip install pyyaml)")


BUILTIN_TIER_PRIORITY = {
    "strong":   ["opus-4.7", "opus-4.6", "sonnet-4.6", "gpt-5.4"],
    "balanced": ["sonnet-4.6", "sonnet-4.5", "gpt-5.4", "gpt-5.4-mini"],
    "cheap":    ["haiku-4.5", "gpt-5.4-mini", "gpt-4.1", "sonnet-4.5"],
}

BUILTIN_FALLBACK_MODELS = ["opus-4.7", "sonnet-4.5", "haiku-4.5"]

# Best-effort static metadata for known model ids.
MODEL_META: dict[str, dict[str, str]] = {
    "opus-4.7":      {"cost": "high", "provider": "anthropic"},
    "opus-4.6":      {"cost": "high", "provider": "anthropic"},
    "sonnet-4.6":    {"cost": "mid",  "provider": "anthropic"},
    "sonnet-4.5":    {"cost": "mid",  "provider": "anthropic"},
    "haiku-4.5":     {"cost": "low",  "provider": "anthropic"},
    "gpt-5.4":       {"cost": "mid",  "provider": "openai"},
    "gpt-5.4-mini":  {"cost": "low",  "provider": "openai"},
    "gpt-4.1":       {"cost": "low",  "provider": "openai"},
}

TIERS = ("strong", "balanced", "cheap")


def load_tier_priority(path: str) -> dict[str, list[str]]:
    if not path:
        return {k: list(v) for k, v in BUILTIN_TIER_PRIORITY.items()}
    p = Path(path)
    if not p.is_file():
        die(f"--tier-priority file not found: {path}")
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        die(f"--tier-priority YAML parse error: {e}")
    if not isinstance(data, dict):
        die("--tier-priority YAML must be a mapping at top level")
    out = {k: list(BUILTIN_TIER_PRIORITY[k]) for k in TIERS}
    for k in TIERS:
        if k in data:
            v = data[k]
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                die(f"--tier-priority.{k} must be a list of strings")
            out[k] = v
    return out


def detect_runtime_and_models() -> tuple[str, list[str]]:
    # Source 1: runtime API — not implemented in M1.

    # Source 2: env var
    env = os.environ.get("CODENOOK_AVAILABLE_MODELS", "").strip()
    if env:
        ids = [m.strip() for m in env.split(",") if m.strip()]
        return "env", ids

    # Source 3: builtin fallback
    return "builtin-fallback", list(BUILTIN_FALLBACK_MODELS)


def classify_tier(model_id: str, priority: dict[str, list[str]]) -> str:
    for tier in TIERS:
        if model_id in priority[tier]:
            return tier
    return "cheap"  # conservative default for unknown ids


def build_available(ids: list[str], priority: dict[str, list[str]]) -> list[dict]:
    out = []
    for mid in ids:
        meta = MODEL_META.get(mid, {"cost": "unknown", "provider": "unknown"})
        out.append({
            "id": mid,
            "tier": classify_tier(mid, priority),
            "cost": meta["cost"],
            "provider": meta["provider"],
        })
    return out


def resolve_tiers(available_ids: set[str], priority: dict[str, list[str]]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for tier in TIERS:
        chosen = None
        for cand in priority[tier]:
            if cand in available_ids:
                chosen = cand
                break
        out[tier] = chosen
    return out


def now_iso() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(ts: str) -> dt.datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    when = dt.datetime.fromisoformat(ts)
    if when.tzinfo is not None:
        when = when.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return when


def check_ttl(path: str, ttl_days: int) -> int:
    p = Path(path)
    if not p.is_file():
        die(f"--check-ttl file not found: {path}")
    try:
        with p.open("r", encoding="utf-8") as f:
            cat = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        die(f"catalog corrupt: {path} ({e})")
    ts = cat.get("refreshed_at")
    if not ts:
        die("catalog missing refreshed_at")
    try:
        when = parse_iso(ts)
    except ValueError as e:
        die(f"refreshed_at unparsable: {ts} ({e})")
    age_days = (dt.datetime.utcnow() - when).total_seconds() / 86400.0
    return 0 if age_days <= ttl_days else 1


def main() -> None:
    output = os.environ.get("CN_OUTPUT", "")
    output_state_json = os.environ.get("CN_OUTPUT_STATE_JSON", "")
    tier_priority_file = os.environ.get("CN_TIER_PRIORITY", "")
    check_ttl_file = os.environ.get("CN_CHECK_TTL", "")
    ttl_days_raw = os.environ.get("CN_TTL_DAYS", "30")

    if check_ttl_file:
        try:
            ttl_days = int(ttl_days_raw)
        except ValueError:
            die(f"--ttl-days must be integer: {ttl_days_raw}")
        sys.exit(check_ttl(check_ttl_file, ttl_days))

    priority = load_tier_priority(tier_priority_file)
    runtime, model_ids = detect_runtime_and_models()
    available = build_available(model_ids, priority)
    resolved = resolve_tiers({m["id"] for m in available}, priority)

    catalog = {
        "refreshed_at": now_iso(),
        "ttl_days": 30,
        "runtime": runtime,
        "available": available,
        "resolved_tiers": resolved,
        "tier_priority": priority,
    }

    if output_state_json:
        # M5: merge model_catalog into the workspace state.json atomically.
        # Preserves any prior keys (orchestrator, sessions, …) and tags
        # _source so consumers know whether tiers came from a real probe
        # or the builtin fallback.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
        from atomic import atomic_write_json  # noqa: E402

        catalog_with_source = dict(catalog)
        catalog_with_source["_source"] = "fallback" if runtime == "builtin-fallback" else "probe"

        target = Path(output_state_json)
        target.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if target.is_file():
            try:
                with target.open("r", encoding="utf-8") as f:
                    existing = json.load(f) or {}
                if not isinstance(existing, dict):
                    existing = {}
            except (json.JSONDecodeError, OSError):
                existing = {}
        existing["model_catalog"] = catalog_with_source
        atomic_write_json(str(target), existing)
        return

    text = json.dumps(catalog, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        die(f"unexpected: {e!r}")
