# plugin-format — Install gate G01

Verifies that a staged plugin source tree is **structurally well-formed**
before any other gate runs.

## CLI

```
format-check.sh --src <dir> [--json]
```

## Exit codes

- `0` — all structural checks pass
- `1` — at least one structural failure (reasons → stderr, or JSON envelope)
- `2` — usage error

## Checks

1. `<src>/plugin.yaml` exists at the root of the staged tree.
2. No symlink under `<src>` resolves outside the `<src>` subtree
   (absolute targets, parent-traversal targets, or anything pointing
   at a path outside the realpath of `<src>` is rejected).

Internal relative symlinks (target stays inside `<src>`) are allowed,
because `--scaffold-plugin` and a few legitimate skill bundles use
them; the path-normalize gate (G11) tightens this further later.

## JSON envelope (with `--json`)

```json
{ "ok": true, "gate": "plugin-format", "reasons": [] }
```
