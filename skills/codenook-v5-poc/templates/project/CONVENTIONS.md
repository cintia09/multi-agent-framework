# Project Conventions

_Auto-generated placeholder. Replace with real conventions after init._

## Code Style

- **Formatter**: (e.g. black for Python, prettier for TS)
- **Linter**: (e.g. ruff, eslint)
- **Max line length**: (e.g. 100)
- **Naming**: snake_case functions / PascalCase classes (adjust per language)

## Git Conventions

- Commit messages in **English**
- Format: `<type>: <subject>` (feat, fix, docs, refactor, test, chore)
- Co-authored-by trailer for AI-assisted commits

## File Organization

- One public class/component per file (unless tightly coupled)
- Tests mirror source structure in `tests/`

## Error Handling

- Raise typed exceptions, don't return error codes (language-dependent)
- Log at boundaries, not internally
- User-facing errors must be actionable

## Documentation

- Public functions/classes require docstrings
- README must be kept current with install/usage
- Architecture decisions go to `docs/adr/`

## Testing

- Critical paths require tests
- Use descriptive test names (`test_<behavior>_<condition>`)
- Mock at I/O boundaries, not internal logic
