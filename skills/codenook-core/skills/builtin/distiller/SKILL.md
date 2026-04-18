# distiller (builtin skill)

## Role

LLM-less router: given a `(plugin, topic, content_file)` triple, decide
whether the distilled artifact promotes to workspace-level
`.codenook/knowledge/` or stays in the plugin's
`.codenook/memory/<plugin>/`. Implements implementation-v6.md §M5.4.

The actual distillation (LLM compression of raw conversation chunks
into a topic note) is **out of scope** here — this skill assumes the
operator has already produced the `--content` file and only handles
*routing + history append*.

## CLI

```
distill.sh --plugin <name> --topic <topic> --content <file> --workspace <ws>
```

## Routing rules

Reads `<ws>/.codenook/plugins/<plugin>/plugin.yaml` and consults
`knowledge.produces.promote_to_workspace_when` (a list of boolean
expressions). Evaluation context:

| key            | type    | source                                   |
|----------------|---------|------------------------------------------|
| `topic`        | string  | `--topic`                                |
| `plugin`       | string  | `--plugin`                               |
| `byte_size`    | integer | `os.path.getsize(content)`               |
| `has_examples` | bool    | `` ``` `` is present in file content     |

Expressions are parsed by `_lib/expr_eval.py` — a hand-rolled grammar
that forbids Python's `eval` / `exec` / `__import__`. Anything
containing `__` or `import` is rejected with exit 1.

If **any** rule is true → `target_root = .codenook/knowledge`.
Otherwise → `.codenook/memory/<plugin>`.

## Output file

Atomically writes `<target_root>/by-topic/<topic>.md` (body =
`# <topic>\n\n<content>`).

## Audit log

Appends one JSON line to `<ws>/.codenook/history/distillation-log.jsonl`:

```json
{"ts": "...", "plugin": "...", "topic": "...",
 "target_root": "...", "rule_matched": true|false, "_content_bytes": N}
```

## Exit codes

- 0 success
- 1 expression rejected / IO error / bad plugin.yaml
- 2 usage error
