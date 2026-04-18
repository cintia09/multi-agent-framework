# config-resolve (builtin skill)

## Role

Sub-agent self-bootstrap helper: produce the **effective** config tree for
`(plugin, task)` by deep-merging the 4 declared layers + Layer 0 builtin
defaults, then expanding `tier_*` model symbols against the workspace's
model catalog. Called by sub-agents — never by main session.

Implements architecture §3.2.4 (4-layer config) + §3.2.4.1 (5-layer model
chain + Router exception) + §3.2.4.2 (tier symbol expansion + provenance).

## CLI

```
resolve.sh --plugin <name> --task <T-NNN> --workspace <path> [--catalog <path>]
```

- `--plugin __router__` is the router sentinel: Layer 1 and Layer 3 are
  forced empty (Router exception per §3.2.4.1 / M-016).
- `--task` is optional. When omitted, Layer 4 is empty.
- `--catalog` defaults to `<workspace>/.codenook/state.json` (extracts
  `.model_catalog`). May point to a standalone JSON file with the same
  shape (used by tests).

## Layers

| Layer | Source                                                              |
|-------|---------------------------------------------------------------------|
| 0     | Builtin: `{"models": {"default": "tier_strong"}}`                   |
| 1     | `<ws>/.codenook/plugins/<plugin>/config-defaults.yaml`              |
| 2     | `<ws>/.codenook/config.yaml` → `.defaults`                          |
| 3     | `<ws>/.codenook/config.yaml` → `.plugins.<plugin>.overrides`        |
| 4     | `<ws>/.codenook/tasks/<task>/state.json` → `.config_overrides`      |

## Output

JSON to stdout. Top-level merged config + a `_provenance` map keyed by
flat dotted leaf paths (e.g. `"models.planner"`):

```json
{
  "models": { "planner": "opus-4.7", "default": "opus-4.7" },
  "_provenance": {
    "models.planner": {
      "value": "opus-4.7",
      "from_layer": 1,
      "symbol": "tier_strong",
      "resolved_via": "model_catalog.resolved_tiers.strong"
    }
  }
}
```

## Tier expansion (step 5)

After deep-merge, walk every `models.*` value:

- Starts with `tier_` and tier ∈ {strong, balanced, cheap}: look up in
  `catalog.resolved_tiers[tier]`. If null → fallback chain
  `strong → balanced → cheap`. If all null → hardcoded `opus-4.7`,
  `resolved_via = "fallback:hardcoded"`.
- Starts with `tier_<other>`: warn to stderr, fallback to `tier_strong`,
  `resolved_via = "fallback:tier_strong"`.
- Literal (no `tier_` prefix): passthrough; `resolved_via = "literal"`,
  `symbol = null`. (Catalog membership not enforced in M1.)

## Errors

- Catalog file unreadable / not valid JSON → stderr `catalog corrupt: <path>`,
  exit 1.
- Unknown top-level key in any user layer (L2/L3/L4) → stderr
  `warning: unknown config key: <k>`, do **not** fail.
