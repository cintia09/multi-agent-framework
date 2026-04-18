#!/usr/bin/env python3
"""task-config-set/_set.py — Layer-4 override writer"""
import json
import os
import sys

ALLOWED_KEYS = [
    "models.default",
    "models.router",
    "models.planner",
    "models.executor",
    "models.reviewer",
    "models.distiller",
    "hitl.mode"
]

TIER_SYMBOLS = ["tier_strong", "tier_balanced", "tier_cheap"]

def main():
    task = os.environ["CN_TASK"]
    key = os.environ["CN_KEY"]
    value = os.environ.get("CN_VALUE", "")
    unset = os.environ.get("CN_UNSET", "0") == "1"
    state_file = os.environ["CN_STATE_FILE"]
    
    # Check key is in allow-list
    if key not in ALLOWED_KEYS:
        print(f"set.sh: key '{key}' not in allow-list", file=sys.stderr)
        sys.exit(1)
    
    # Load state
    with open(state_file, 'r') as f:
        state = json.load(f)
    
    if "config_overrides" not in state:
        state["config_overrides"] = {}

    parts = key.split('.')

    if unset:
        # Walk to the leaf; pop it; clean up empty parent dicts.
        stack = [state["config_overrides"]]
        node = state["config_overrides"]
        for p in parts[:-1]:
            if not isinstance(node, dict) or p not in node:
                node = None
                break
            node = node[p]
            stack.append(node)
        if isinstance(node, dict) and parts[-1] in node:
            del node[parts[-1]]
            # Walk back up; remove empty intermediate dicts (but not the root)
            for i in range(len(stack) - 1, 0, -1):
                child = stack[i]
                parent = stack[i - 1]
                seg = parts[i - 1]
                if isinstance(child, dict) and not child and isinstance(parent, dict) and seg in parent:
                    del parent[seg]
                else:
                    break
    else:
        # Warn if value is not a known tier symbol or common model
        if value not in TIER_SYMBOLS and not is_known_model(value):
            print(f"set.sh: warning: unknown model value '{value}'", file=sys.stderr)

        # Write the value as a nested dict path under config_overrides.
        node = state["config_overrides"]
        for p in parts[:-1]:
            existing = node.get(p)
            if not isinstance(existing, dict):
                existing = {}
                node[p] = existing
            node = existing
        node[parts[-1]] = value

    # Write back
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write('\n')
    
    sys.exit(0)

def is_known_model(value):
    """Check if value looks like a known model ID (very permissive)"""
    # Just check if it contains common patterns - we warn anyway
    common_prefixes = ["gpt-", "claude-", "gemini-", "o1-", "o3-"]
    return any(value.startswith(p) for p in common_prefixes)

if __name__ == "__main__":
    main()
