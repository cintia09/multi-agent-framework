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
# Decision #45 — strict whitelist for top-level keys of .codenook/config.yaml.
# Same set; named for clarity at the strict check site.
CONFIG_YAML_TOP_KEYS = KNOWN_TOP_KEYS
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


def load_catalog(path: Path) -> dict | None:
    """Return parsed catalog, or None to signal "catalog file missing entirely"
    (per M5: tier symbols are then left unresolved, with a warning)."""
    if not path.is_file():
        return None
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

    # Layer 1 — plugin baseline. For the __router__ sentinel we still
    # READ the file so the router-invariant check below can detect (and
    # strip) any attempt to override models.router.
    l1 = read_yaml(ws / ".codenook/plugins" / plugin / "config-defaults.yaml")

    # Layer 2/3 — workspace config.yaml
    cfg = read_yaml(ws / ".codenook/config.yaml")

    # Decision #45: strict whitelist on the top-level keys of config.yaml.
    if isinstance(cfg, dict):
        for k in cfg.keys():
            if k not in CONFIG_YAML_TOP_KEYS:
                print(f"resolve.sh: unknown_top_key: {k}", file=sys.stderr)
                sys.exit(1)

    l2 = (cfg.get("defaults") or {}) if isinstance(cfg, dict) else {}

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


def resolve_tier(symbol: str, catalog: dict | None) -> tuple[str, str, str | None]:
    """Return (literal_id, resolved_via, normalized_symbol_or_None).

    `catalog is None` means the catalog file was missing entirely —
    leave tier_* symbols unresolved (caller will mark deferred).
    """
    if not symbol.startswith("tier_"):
        return symbol, "literal", None
    if catalog is None:
        warn(f"catalog missing; {symbol} → {HARDCODED_FALLBACK}")
        return HARDCODED_FALLBACK, "fallback:catalog_missing", symbol
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
    if catalog is None:
        warn(f"catalog file missing: {catalog_path}; tier_* symbols will be left unresolved")

    layers = collect_layers(plugin, task, ws)
    warn_unknown_keys(layers)

    # Router invariant (#44): if plugin == __router__, an explicit
    # models.router from L1/L3/L4 must be reverted to the L0/L2 view.
    router_attempts = False
    if plugin == ROUTER_SENTINEL:
        for idx in (1, 3, 4):
            try:
                if "router" in layers[idx].get("models", {}):
                    router_attempts = True
                    del layers[idx]["models"]["router"]
            except (AttributeError, TypeError):
                pass

    # Deep-merge L0..L4
    merged: dict = {}
    for layer in layers:
        merged = deep_merge(merged, layer)

    provenance: dict = {}
    catalog_for_resolve = catalog if catalog is not None else None

    # Tier expansion + provenance for models.*
    models = merged.get("models", {}) or {}
    for role, raw_value in list(models.items()):
        path = ("models", role)
        from_layer = find_from_layer(path, layers)
        if isinstance(raw_value, str):
            literal, via, symbol = resolve_tier(raw_value, catalog_for_resolve)
            models[role] = literal
            entry = {
                "value": literal,
                "from_layer": from_layer,
                "symbol": symbol,
                "resolved_via": via,
            }
            if plugin == ROUTER_SENTINEL and role == "router" and router_attempts:
                entry["router_invariant_enforced"] = True
            provenance[f"models.{role}"] = entry
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
