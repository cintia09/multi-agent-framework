# Commit Standards

- All commit messages MUST be in English
- Use conventional commit format: `type: description`
  - `feat:` — new feature
  - `fix:` — bug fix
  - `docs:` — documentation
  - `test:` — tests
  - `chore:` — maintenance
  - `refactor:` — code restructuring
  - `release:` — version release
  - `security:` — security fix
- Include task ID prefix when working on a task: `feat: T-NNN description`
- Keep commit messages concise but descriptive

## Trailers (mandatory, in this order)

```
Change-Id: I<40-hex>
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

- **Change-Id**: Same task = same Change-Id. Generate once per task, reuse for all related commits.
  - Format: `I` + 40 hex chars (Gerrit-compatible)
  - Generate: `echo "T-NNN-$(date +%s)" | shasum | cut -c1-40` prefixed with `I`
  - Store in `.agents/runtime/implementer/workspace/T-NNN-change-id.txt`
- **Co-authored-by**: Always include when AI-assisted
