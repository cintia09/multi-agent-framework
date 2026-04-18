# install-orchestrator — runs the 12-gate plugin install pipeline

This skill is the heart of M2.  It takes a staged plugin source
(directory or tarball) and runs **12 gates in fixed order** before
atomically moving the plugin into
`<workspace>/.codenook/plugins/<id>/`.

## Gate order

| # | code | gate skill / inline | failure → exit |
|---|------|---------------------|----------------|
| 1 | G01 | plugin-format       | 1 |
| 2 | G02 | plugin-schema       | 1 |
| 3 | G03 | plugin-id-validate  | **3 if "already installed"**, else 1 |
| 4 | G04 | plugin-version-check| 1 |
| 5 | G05 | plugin-signature    | 1 |
| 6 | G06 | plugin-deps-check   | 1 |
| 7 | G07 | plugin-subsystem-claim | 1 |
| 8 | G08 | sec-audit (subprocess) | 1 |
| 9 | G09 | inline size check (≤10MB total, ≤1MB each) | 1 |
| 10 | G10 | plugin-shebang-scan | 1 |
| 11 | G11 | plugin-path-normalize | 1 |
| 12 | G12 | inline atomic commit + state.json append | 1 |

## CLI

```
orchestrator.sh --src <tarball|dir> --workspace <dir>
                [--upgrade] [--dry-run] [--json]
```

The top-level `install.sh` is just a thin wrapper that calls this.

## Stage / commit lifecycle

1. **Stage** — copy/extract `--src` into
   `<workspace>/.codenook/staging/<random>/` (created on demand).
2. **Run gates** — each gate skill is invoked as a subprocess with
   `--json`; the orchestrator collects `{ok, gate, reasons}` records.
3. **Decide** — on any failure: print reasons (`[Gxx] ...`), keep
   the staging dir (so the user can inspect it), and exit non-zero.
4. **Commit** — on full pass and not `--dry-run`: atomic
   `os.replace()` of the staging dir to
   `<workspace>/.codenook/plugins/<id>/`, then append a record to
   `<workspace>/.codenook/state.json` (`.installed_plugins[]`)
   using `_lib/atomic.atomic_write_json`.
5. **Cleanup** — after a successful commit, remove the staging
   parent if empty.
