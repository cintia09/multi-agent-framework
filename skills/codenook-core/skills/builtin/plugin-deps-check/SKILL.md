# plugin-deps-check — Install gate G06

Verifies the plugin's declared `requires.core_version` constraint
against the running core VERSION.

## CLI

```
deps-check.sh --src <dir> [--core-version <v>] [--json]
```

If `--core-version` is omitted, the core VERSION file shipped with
this repo (`skills/codenook-core/VERSION`) is read.

## Constraint syntax

Comma-separated comparator list (logical AND):

```
>=0.2.0,<1.0.0
>=0.2.0
==0.2.0
```

Supported operators: `>=`, `<=`, `>`, `<`, `==`, `=`, `!=`. Operands
must be valid SemVer 2.0 strings.

## ⚠️ NOTE — SemVer pre-release precedence (M2 caveat)

Per [SemVer §11.4](https://semver.org/#spec-item-11), a version with a
pre-release identifier has *lower* precedence than the same version
without one:

```
0.2.0-m2.1  <  0.2.0-m2.2  <  0.2.0
```

While core is on `0.2.0-m2.x` (M2 milestone pre-release), plugin authors
who want to require "M2 or newer" must spell their constraint with an
explicit pre-release floor — **`>=0.2.0`** would reject every M2 build
because every M2 build sorts *before* `0.2.0`.

```yaml
# plugin.yaml — correct for M2-era plugins:
requires:
  core_version: '>=0.2.0-m2'    # ✅ accepts 0.2.0-m2.1, 0.2.0-m2.2, 0.2.0, ...

# plugin.yaml — WRONG during M2:
requires:
  core_version: '>=0.2.0'       # ❌ rejects every 0.2.0-m2.x build
```

Once core ships final `0.2.0`, plain `>=0.2.0` becomes correct.
