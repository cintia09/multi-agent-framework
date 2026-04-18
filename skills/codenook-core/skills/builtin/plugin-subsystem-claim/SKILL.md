# plugin-subsystem-claim — Install gate G07

Each plugin declares a list of free-form subsystem-extension claims
in `plugin.yaml.declared_subsystems`. Two plugins may not claim the
same string (e.g. both registering `skills/test-runner`).

## CLI

```
subsystem-claim.sh --src <dir> [--workspace <dir>] [--upgrade] [--json]
```

## Behaviour

- If no `--workspace`, no peers exist → pass.
- Walk `<workspace>/.codenook/plugins/*/plugin.yaml`; collect each
  peer's `declared_subsystems` set.
- For every claim in the staged plugin: if any peer plugin (other
  than `--upgrade` self) already owns the same string → fail.
- Without `--upgrade`, the same-id peer is treated like any other
  peer (so re-installing a plugin is itself a collision; G03 will
  also catch this, but G07 makes the message specific).
