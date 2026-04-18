#!/usr/bin/env python3
"""config-resolve core algorithm. Invoked by resolve.sh.

Reads its inputs from CN_* environment variables (set by resolve.sh):
  CN_PLUGIN     plugin name (or '__router__' sentinel)
  CN_TASK       optional task id (e.g. T-007), '' if absent
  CN_WORKSPACE  workspace root (the dir containing .codenook/)
  CN_CATALOG    path to model catalog JSON (full state.json or standalone)

Emits the merged config + _provenance to stdout as JSON; warnings + errors
to stderr; exit 1 only on catalog corruption (per SKILL.md).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    print("resolve.sh: PyYAML not installed (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


KNOWN_TOP_KEYS = {
    "models", "hitl", "knowledge", "concurrency", "skills", "memory",
    # config-only sub-keys we tolerate at the override-root:
    "router",
    # F-032 / decision #45 — additional top-level keys that may appear
    # in workspace config.yaml or task overrides:
    "plugins", "defaults", "secrets",
}
TIERS = ("strong", "balanced", "cheap")
HARDCODED_FALLBACK = "opus-4.7"
ROUTER_SENTINEL = "__router__"


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        warn(f"{path}: top-level not a mapping; ignoring")
        return {}
    return data


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_catalog(path: Path) -> dict:
    if not path.is_file():
        # Empty catalog — tier expansion will fall back to hardcoded.
        return {"available": [],
                "resolved_tiers": {t: None for t in TIERS}}
    try:
        with path.open("r", encoding="utf-8") as f:
            cat = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"resolve.sh: catalog corrupt: {path} ({e})", file=sys.stderr)
        sys.exit(1)
    # Some callers point at a full state.json; pull out model_catalog if present.
    if "model_catalog" in cat and "resolved_tiers" not in cat:
        cat = cat["model_catalog"]
    cat.setdefault("available", [])
    cat.setdefault("resolved_tiers", {t: None for t in TIERS})
    return cat


def deep_merge(base: dict, top: dict) -> dict:
    """Recursive map merge; arrays and scalars in `top` replace `base`."""
    out = dict(base)
    for k, v in top.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def collect_layers(plugin: str, task: str, ws: Path) -> list[dict]:
    # Layer 0 — builtin
    l0: dict = {"models": {"default": "tier_strong", "router": "tier_strong"}}

    # Layer 1 — plugin baseline (router exception: empty)
    if plugin == ROUTER_SENTINEL:
        l1: dict = {}
    else:
        l1 = read_yaml(ws / ".codenook/plugins" / plugin / "config-defaults.yaml")

    # Layer 2/3 — workspace config.yaml
    cfg = read_yaml(ws / ".codenook/config.yaml")
    l2 = (cfg.get("defaults") or {}) if isinstance(cfg, dict) else {}

    if plugin == ROUTER_SENTINEL:
        l3: dict = {}
    else:
        plugins_section = (cfg.get("plugins") or {}) if isinstance(cfg, dict) else {}
        l3 = ((plugins_section.get(plugin) or {}).get("overrides") or {})

    # Layer 4 — task overrides
    l4: dict = {}
    if task:
        ts = read_json(ws / ".codenook/tasks" / task / "state.json")
        l4 = (ts.get("config_overrides") or {}) if isinstance(ts, dict) else {}

    return [l0, l1, l2, l3, l4]


def warn_unknown_keys(layers: list[dict]) -> None:
    # Layers 2/3/4 are user-authored; warn (don't fail) on unknown top-level keys.
    for idx in (2, 3, 4):
        for k in layers[idx].keys():
            if k not in KNOWN_TOP_KEYS:
                warn(f"unknown config key: {k} (layer {idx})")


def find_from_layer(path: tuple[str, ...], layers: list[dict]) -> int:
    """Highest layer index that explicitly sets the leaf at `path`."""
    for i in range(len(layers) - 1, -1, -1):
        cur = layers[i]
        ok = True
        for seg in path:
            if not isinstance(cur, dict) or seg not in cur:
                ok = False
                break
            cur = cur[seg]
        if ok:
            return i
    return 0


def resolve_tier(symbol: str, catalog: dict) -> tuple[str, str, str | None]:
    """Return (literal_id, resolved_via, normalized_symbol_or_None)."""
    if not symbol.startswith("tier_"):
        return symbol, "literal", None
    tier_name = symbol[len("tier_"):]
    rt = catalog.get("resolved_tiers", {})

    if tier_name in TIERS:
        literal = rt.get(tier_name)
        if literal:
            return literal, f"model_catalog.resolved_tiers.{tier_name}", symbol
        # Fallback chain
        for fb in TIERS:
            if rt.get(fb):
                warn(f"tier {symbol} has no candidate; falling back to {fb}")
                return rt[fb], f"fallback:{fb}", symbol
        warn(f"tier {symbol} unresolvable; using hardcoded {HARDCODED_FALLBACK}")
        return HARDCODED_FALLBACK, "fallback:hardcoded", symbol

    # Unknown tier (tier_xxx) → fallback to tier_strong (per Unit-3 test 12).
    warn(f"unknown tier symbol {symbol}; falling back to tier_strong")
    literal = rt.get("strong")
    if literal:
        return literal, "fallback:tier_strong", symbol
    return HARDCODED_FALLBACK, "fallback:hardcoded", symbol


def main() -> None:
    plugin = os.environ["CN_PLUGIN"]
    task = os.environ.get("CN_TASK", "")
    ws = Path(os.environ["CN_WORKSPACE"]).resolve()
    catalog_path = Path(os.environ["CN_CATALOG"])

    catalog = load_catalog(catalog_path)
    layers = collect_layers(plugin, task, ws)
    warn_unknown_keys(layers)

    # Deep-merge L0..L4
    merged: dict = {}
    for layer in layers:
        merged = deep_merge(merged, layer)

    provenance: dict = {}

    # Tier expansion + provenance for models.*
    models = merged.get("models", {}) or {}
    for role, raw_value in list(models.items()):
        path = ("models", role)
        from_layer = find_from_layer(path, layers)
        if isinstance(raw_value, str):
            literal, via, symbol = resolve_tier(raw_value, catalog)
            models[role] = literal
            provenance[f"models.{role}"] = {
                "value": literal,
                "from_layer": from_layer,
                "symbol": symbol,
                "resolved_via": via,
            }
    merged["models"] = models

    # Minimal provenance for any other top-level scalar/list leaves so
    # consumers can introspect (best-effort; not exhaustive in M1).
    for top in ("hitl", "knowledge"):
        sub = merged.get(top)
        if isinstance(sub, dict):
            for k, v in sub.items():
                p = (top, k)
                provenance.setdefault(f"{top}.{k}", {
                    "value": v,
                    "from_layer": find_from_layer(p, layers),
                    "symbol": None,
                    "resolved_via": "literal",
                })

    merged["_provenance"] = provenance
    json.dump(merged, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
