# Issuenook plugin changelog

## 0.1.0 — rename and composable issue-investigation workflow

Breaking change: this plugin replaces the former PR-focused plugin
identity. It is now `issuenook`; old task state and
`plugins.prnook.*` configuration are not supported.

Changed:

- Renamed plugin metadata, docs, roles, templates, knowledge, skills,
  and examples to the Issuenook identity.
- Replaced the old fixed three-phase pipeline with six reusable phases:
  information collection, log analysis, code analysis, root-cause
  hypotheses, hypothesis verification, and conclusion.
- Added multiple workflow profiles: `full`, `log-only`, `code-only`,
  `analyse-only`, and `hypothesis-only`.
- Added one HITL gate per phase.
- Reworked log/code stages as open-ended analysis phases that must not
  declare root cause before the hypothesis stage.
- Added explicit guided-input checks to each role contract.

Migration:

- Install from `plugins/issuenook`.
- Replace workspace config keys under `plugins.prnook` with
  `plugins.issuenook`.
- Recreate old tasks if they need to use the new workflow.
