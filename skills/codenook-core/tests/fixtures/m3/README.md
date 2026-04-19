# M3 Router fixtures

Static plugin manifests and pre-built workspace skeletons used by the
M3 router-* bats suites.

## Plugin stubs (`plugins/`)

Each fixture contains a single `plugin.yaml` (M2 schema) plus an
`intent_patterns:` field that was consumed by the historical
`router-triage` skill (removed in M8.7). The fixtures are kept for the
remaining M3 router-bootstrap / context-scan / dispatch-build bats.

| stub             | intent regexes                           | notes                              |
|------------------|------------------------------------------|------------------------------------|
| writing-stub     | `新建小说.*`, `写章节`                   | high-confidence regex              |
| coding-stub      | `debug`, `fix bug.*`                     | distinct domain                    |
| ambiguous-stub   | `help`                                   | collides with builtin `help` skill |

## Workspaces (`workspaces/`)

Pre-baked `.codenook/` skeletons. Tests `cp -R` them into the per-test
scratch dir before running.

| workspace   | plugins installed             | active tasks | HITL queue |
|-------------|-------------------------------|--------------|------------|
| empty       | none                          | 0            | 0          |
| one-plugin  | writing-stub                  | 0            | 0          |
| full        | writing/coding/ambiguous      | 2            | 1          |
