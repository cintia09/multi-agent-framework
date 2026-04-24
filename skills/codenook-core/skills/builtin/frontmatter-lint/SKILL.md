# frontmatter-lint (builtin skill)

## Role

Validate frontmatter contracts across `.codenook/memory/` and
`.codenook/plugins/<id>/` per the T-006 unified-layout design (§2.4):

| File pattern                         | Required fields                              | Forbidden |
|--------------------------------------|----------------------------------------------|-----------|
| `knowledge/<slug>/index.md`          | `id`, `title`, `type`, `tags`, `summary`     | `keywords` |
| `skills/<slug>/SKILL.md`             | `id`, `title`, `tags`, `summary`             | `type`, `keywords` |

Additional checks:

* `type` (knowledge/index.md) must be one of `case|playbook|error|knowledge`
* `summary` length ≤ 400 chars (warn)
* `id` unique workspace-wide (fail on duplicate)

## CLI

```
python lint.py --workspace <dir> [--json]
```

## Exit codes

| code | meaning                                      |
|------|----------------------------------------------|
| 0    | no fail-level findings (warns may be present) |
| 1    | at least one fail-level finding              |
| 2    | usage / IO error                             |

## JSON output

```json
{
  "ok": true,
  "scanned": 12,
  "findings": [
    {"path": "...", "level": "fail|warn", "code": "...", "message": "..."}
  ]
}
```
