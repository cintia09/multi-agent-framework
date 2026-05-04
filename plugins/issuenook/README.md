# Issuenook — CodeNook plugin

Issuenook is a composable software runtime issue investigation plugin.
It replaces the former PR-focused plugin identity and is not backward
compatible with old `prnook` task state or `plugins.prnook.*`
configuration.

## Pipeline catalogue

| Phase | Role | Output | Gate |
|---|---|---|---|
| Information collection | `info-collector` | `outputs/phase-info-collect.md` | `info_collect_signoff` |
| Log analysis | `log-analyst` | `outputs/phase-log-analyse.md` | `log_analyse_signoff` |
| Code analysis | `code-analyst` | `outputs/phase-code-analyse.md` | `code_analyse_signoff` |
| Root-cause hypotheses | `hypothesizer` | `outputs/phase-hypothesise.md` | `hypothesis_signoff` |
| Hypothesis verification | `hypothesis-verifier` | `outputs/phase-verify-hypothesis.md` | `hypothesis_verification_signoff` |
| Conclusion | `concluder` | `outputs/phase-conclusion.md` | `conclusion_signoff` |

Every phase starts with guided user-input checks, performs the phase
work, and then opens a HITL gate before the workflow advances.

## Profiles

| Profile | Phase chain | Use case |
|---|---|---|
| `default` / `full` | info → log → code → hypothesis → verify → conclude | Full investigation |
| `log-only` | info → log → hypothesis → verify → conclude | Logs are the primary evidence |
| `code-only` | info → code → hypothesis → verify → conclude | Source review is the primary evidence |
| `analyse-only` | info → log → code → conclude | Open-ended analysis without root-cause closure |
| `hypothesis-only` | info → hypothesis → verify → conclude | User already has evidence or candidate hypotheses |

Advanced users can supply a custom phase chain when the kernel supports
it:

```bash
codenook task new --plugin issuenook \
  --phase-chain "info_collect,log_analyse,hypothesise,verify_hypothesis,conclude" \
  --title "调查运行异常" \
  --accept-defaults
```

## Installing

From a CodeNook-enabled workspace:

```bash
codenook plugin install <path-to-codenook-plugins>/plugins/issuenook
```

## HITL selection format

The `hypothesis_signoff` gate lets the human choose which hypotheses to
verify:

```text
SELECTED: H1, H3
EDITS: <optional changes to hypothesis wording or scope>
NOTES: <optional evidence or reviewer rationale>
```

If the selection is missing, the verifier falls back to the
hypothesizer's highest-priority recommendation and records that fallback.

## Deployment-specific integrations

Issuenook ships methodology only. Endpoint access, browser automation,
credentials, code-host adapters, log-system fetchers, and team maps
belong in workspace memory skills/knowledge.

Suggested workspace skill names:

- `issue-context-access`
- `runtime-log-access`
- `source-code-access`

## Knowledge and skills

- `knowledge/source-access-blocked-deliverable/` — methodology for
  producing useful medium-confidence analysis when source access is
  blocked.
- `knowledge/_template-case/` — template for completed investigation
  records.
- `skills/module-analysis/` — template for module/component analysis
  playbooks.
